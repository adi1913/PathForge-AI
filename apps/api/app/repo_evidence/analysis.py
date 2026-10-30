"""Deterministic evidence extraction from a RepoSnapshot. No network, no DB writes, no LLM.
Everything produced is an *observation* with explicit limitations — never proficiency."""

import re
from dataclasses import dataclass

from app.models.enums import RepoEvidenceType as T
from app.repo_evidence.collector import RepoSnapshot
from app.repo_evidence.manifests import PARSERS, ManifestError
from app.skill_vocabulary import TECH_VOCABULARY

MAX_CONFIDENCE = 0.7
CONF = {T.DEPENDENCY_MANIFEST: 0.50, T.INFRASTRUCTURE_FILE: 0.50, T.README_MENTION: 0.20}
LANGUAGE_CONF_MIN, LANGUAGE_CONF_HIGH = 0.35, 0.45
LANGUAGE_MIN_PERCENT, LANGUAGE_HIGH_PERCENT = 10.0, 40.0

LIMITATION = {
    T.DEPENDENCY_MANIFEST: "A declared dependency shows the project lists the library; it does not show it is "
    "used well, or at all, in the code.",
    T.LANGUAGE_SHARE: "Byte share of the repository's languages is not proficiency and says nothing about code "
    "quality.",
    T.INFRASTRUCTURE_FILE: "The presence of a config file shows exposure to the tool; it does not show the "
    "configuration is correct or production-ready.",
    T.README_MENTION: "A README mention is a claim by the repository's author, not evidence from code.",
}
GLOBAL_LIMITATIONS = (
    "This shows what the repository uses, not that this user wrote it or understands it.",
    "Only repository metadata, the README, the root directory listing and a few allow-listed manifest/CI files "
    "were inspected. Code quality, architecture, security and test coverage were NOT analyzed.",
)

# Well-known package -> technology name; the name is then resolved against the skill catalog.
PACKAGE_TECH = {
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "torch": "PyTorch",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "transformers": "Transformers",
    "qdrant-client": "Qdrant",
    "chromadb": "ChromaDB",
    "pgvector": "pgvector",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "openai": "OpenAI",
    "mcp": "MCP",
    "sqlalchemy": "SQLAlchemy",
    "pytest": "pytest",
    "pydantic": "Pydantic",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "boto3": "AWS",
    "redis": "Redis",
    "psycopg": "PostgreSQL",
    "psycopg2": "PostgreSQL",
    "asyncpg": "PostgreSQL",
    "react": "React",
    "next": "Next.js",
    "vue": "Vue",
    "@angular/core": "Angular",
    "express": "Express",
    "typescript": "TypeScript",
    "tailwindcss": "Tailwind CSS",
}
_AMBIGUOUS_README_TERMS = {"go"}
_TESTS_DIRS = {"tests", "test", "__tests__", "spec"}
_TEST_FILE = re.compile(r"(^|/)(test_[^/]+|[^/]+\.test\.[^/]+|[^/]+_test\.[^/]+)$")


@dataclass(frozen=True)
class Candidate:
    technology: str
    evidence_type: T
    excerpt: str
    confidence: float


def compute_signals(snap: RepoSnapshot) -> dict:
    names = snap.root_entries
    return {
        "has_readme": snap.readme is not None and bool(snap.readme.content.strip()),
        "readme_chars": len(snap.readme.content) if snap.readme else 0,
        "readme_truncated": bool(snap.readme and snap.readme.truncated),
        "has_license": bool(snap.details.license and snap.details.license != "NOASSERTION")
        or any(n.upper().startswith("LICENSE") for n in names),
        "has_tests": bool(snap.root_dirs & _TESTS_DIRS) or any(_TEST_FILE.search(n) for n in names),
        "has_ci": bool(snap.workflows),
        "has_dockerfile": "Dockerfile" in snap.manifests or "Dockerfile" in names,
        "manifests_found": sorted(snap.manifests),
        "is_fork": snap.details.is_fork,
        "is_archived": snap.details.is_archived,
        "empty_repository": snap.empty,
        "stars": snap.details.repository.stars,
        "scope": "metadata + README + root listing + allow-listed manifest/CI files",
    }


def language_percent(languages_bytes: dict[str, int]) -> dict[str, float]:
    total = sum(languages_bytes.values())
    if not total:
        return {}
    return {k: round(v / total * 100, 1) for k, v in sorted(languages_bytes.items(), key=lambda kv: (-kv[1], kv[0]))}


def _snippet(text: str, start: int, end: int, radius: int = 60) -> str:
    return " ".join(text[max(0, start - radius) : end + radius].split())[:300]


def extract_candidates(snap: RepoSnapshot) -> tuple[list[Candidate], list[str]]:
    """Returns (candidates, limitations raised while parsing)."""
    out: list[Candidate] = []
    limits: list[str] = []

    for name, content in snap.manifests.items():
        parser = PARSERS.get(name)
        if parser is None:
            continue
        try:
            deps = parser(content)
        except ManifestError as exc:
            limits.append(f"{name} could not be parsed ({exc}); its dependencies were ignored.")
            continue
        for dep in dict.fromkeys(deps):
            tech = PACKAGE_TECH.get(dep)
            if tech:
                out.append(
                    Candidate(tech, T.DEPENDENCY_MANIFEST, f"{name} declares '{dep}'", CONF[T.DEPENDENCY_MANIFEST])
                )

    for language, percent in language_percent(snap.languages_bytes).items():
        if percent >= LANGUAGE_MIN_PERCENT:
            conf = LANGUAGE_CONF_HIGH if percent >= LANGUAGE_HIGH_PERCENT else LANGUAGE_CONF_MIN
            out.append(
                Candidate(language, T.LANGUAGE_SHARE, f"{language} is {percent}% of the repository's bytes", conf)
            )

    if "Dockerfile" in snap.manifests or "Dockerfile" in snap.root_entries:
        out.append(
            Candidate(
                "Docker", T.INFRASTRUCTURE_FILE, "Dockerfile present at repository root", CONF[T.INFRASTRUCTURE_FILE]
            )
        )
    elif any(n in snap.manifests for n in ("docker-compose.yml", "docker-compose.yaml")):
        out.append(
            Candidate("Docker", T.INFRASTRUCTURE_FILE, "docker-compose file present", CONF[T.INFRASTRUCTURE_FILE])
        )
    if snap.workflows:
        first = sorted(snap.workflows)[0]
        out.append(Candidate("CI/CD", T.INFRASTRUCTURE_FILE, f"CI workflow file {first}", CONF[T.INFRASTRUCTURE_FILE]))

    if snap.readme and snap.readme.content:
        text = snap.readme.content
        for term in TECH_VOCABULARY:
            if term in _AMBIGUOUS_README_TERMS:
                continue
            match = re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE)
            if match:
                out.append(
                    Candidate(
                        term, T.README_MENTION, _snippet(text, match.start(), match.end()), CONF[T.README_MENTION]
                    )
                )
    return out, limits


def aggregate_confidence(confidences_by_type: dict[T, float]) -> float:
    if not confidences_by_type:
        return 0.0
    value = max(confidences_by_type.values()) + 0.05 * (len(confidences_by_type) - 1)
    return round(min(MAX_CONFIDENCE, value), 2)
