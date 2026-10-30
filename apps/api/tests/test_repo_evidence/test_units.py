import pytest

from app.models.enums import RepoEvidenceType as T
from app.repo_evidence.analysis import aggregate_confidence, compute_signals, extract_candidates, language_percent
from app.repo_evidence.collector import RepoSnapshot
from app.repo_evidence.errors import InvalidRepositoryUrlError
from app.repo_evidence.manifests import (
    ManifestError,
    parse_package_json,
    parse_pipfile,
    parse_pyproject,
    parse_requirements_txt,
)
from app.repo_evidence.mcp_models import ReadmeResult, RepoDetailsResult
from app.repo_evidence.url import parse_repository_ref


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://github.com/octocat/hello", ("octocat", "hello")),
        ("https://www.github.com/octocat/hello/", ("octocat", "hello")),
        ("octocat/hello.git", ("octocat", "hello")),
        ("  octocat/hello  ", ("octocat", "hello")),
    ],
)
def test_url_parsing_accepts(value, expected):
    assert parse_repository_ref(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://github.com/a/b",
        "https://evil.com/a/b",
        "https://github.com/a",
        "https://github.com/a/b/tree/main",
        "https://github.com.evil.com/a/b",
        "a/../b",
        "../etc",
        "a/b/c",
        "https://github.com/a/b?x=1",
        "file:///etc/passwd",
    ],
)
def test_url_parsing_rejects(value):
    with pytest.raises(InvalidRepositoryUrlError):
        parse_repository_ref(value)


def test_manifest_parsers():
    assert parse_requirements_txt("# c\nFastAPI>=0.1\n-r other.txt\ngit+https://x\nPyTorch==2 # x\n") == [
        "fastapi",
        "pytorch",
    ]
    assert parse_pyproject(
        '[project]\ndependencies=["Fast_API>=1"]\n[project.optional-dependencies]\nd=["pytest"]'
    ) == [
        "fast-api",
        "pytest",
    ]
    assert parse_pipfile('[packages]\nflask="*"\n[dev-packages]\npytest="*"') == ["flask", "pytest"]
    assert parse_package_json('{"dependencies":{"React":"1"},"devDependencies":{"typescript":"5"}}') == [
        "react",
        "typescript",
    ]


@pytest.mark.parametrize(
    ("parser", "text"),
    [
        (parse_pyproject, "not = [toml"),
        (parse_pipfile, "[[["),
        (parse_package_json, "{nope"),
        (parse_package_json, "[1,2]"),
        (parse_pyproject, "[project]\ndependencies = 'oops'"),
    ],
)
def test_malformed_manifests_raise(parser, text):
    with pytest.raises(ManifestError):
        parser(text)


def _snap(**kw):
    details = RepoDetailsResult(
        source="live", repository={"name": "r", "full_name": "o/r"}, license=kw.pop("license", None)
    )
    return RepoSnapshot(details=details, **kw)


def test_evidence_rules_and_confidence_caps():
    snap = _snap(
        languages_bytes={"Python": 7000, "Shell": 100, "TypeScript": 2900},
        readme=ReadmeResult(content="We use FastAPI everywhere."),
        manifests={"requirements.txt": "fastapi\n", "Dockerfile": "FROM x"},
        workflows={".github/workflows/ci.yml": "name: ci"},
        root_entries=["Dockerfile"],
    )
    cands, limits = extract_candidates(snap)
    by = {(c.technology, c.evidence_type): c.confidence for c in cands}
    assert by[("FastAPI", T.DEPENDENCY_MANIFEST)] == 0.5
    assert by[("fastapi", T.README_MENTION)] == 0.2
    assert by[("Python", T.LANGUAGE_SHARE)] == 0.45  # 70%
    assert by[("TypeScript", T.LANGUAGE_SHARE)] == 0.35  # 29%
    assert ("Shell", T.LANGUAGE_SHARE) not in by  # 1% is below the 10% floor
    assert by[("Docker", T.INFRASTRUCTURE_FILE)] == 0.5
    assert by[("CI/CD", T.INFRASTRUCTURE_FILE)] == 0.5
    assert limits == []
    assert all(c.confidence <= 0.7 for c in cands)


def test_malformed_manifest_becomes_limitation_not_evidence():
    snap = _snap(manifests={"package.json": "{bad"})
    cands, limits = extract_candidates(snap)
    assert cands == [] and "package.json could not be parsed" in limits[0]


def test_readme_matches_whole_words_only():
    snap = _snap(readme=ReadmeResult(content="pythonic reactor goes"))
    assert extract_candidates(snap)[0] == []


def test_aggregate_confidence():
    assert aggregate_confidence({}) == 0.0
    assert aggregate_confidence({T.README_MENTION: 0.2}) == 0.2
    assert aggregate_confidence({T.DEPENDENCY_MANIFEST: 0.5, T.README_MENTION: 0.2}) == 0.55
    assert (
        aggregate_confidence(
            {T.DEPENDENCY_MANIFEST: 0.5, T.LANGUAGE_SHARE: 0.45, T.INFRASTRUCTURE_FILE: 0.5, T.README_MENTION: 0.2}
        )
        == 0.65
    )
    assert aggregate_confidence({t: 0.7 for t in T}) == 0.7  # capped


def test_signals_and_language_percent():
    snap = _snap(
        license="MIT",
        root_entries=["README.md", "test_app.py", "LICENSE"],
        root_dirs={"tests"},
        readme=ReadmeResult(content="hi"),
    )
    sig = compute_signals(snap)
    assert sig["has_readme"] and sig["has_tests"] and sig["has_license"] and not sig["has_ci"]
    assert sig["scope"].startswith("metadata")
    assert language_percent({}) == {}
    assert language_percent({"A": 3, "B": 1}) == {"A": 75.0, "B": 25.0}
    assert compute_signals(_snap(root_entries=["src"]))["has_tests"] is False
