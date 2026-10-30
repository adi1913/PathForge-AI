"""A scripted stand-in for MCPClientManager so service tests exercise the real collector/service
code with deterministic 'GitHub' answers (no network, no subprocess)."""

from types import SimpleNamespace

from app.agent.errors import ToolExecutionError, ToolNotFoundError
from app.models.skill import Skill
from app.models.user import User


class FakeManager:
    def __init__(self, handlers: dict | None = None):
        self.calls: list[tuple[str, dict]] = []
        self._handlers = {**default_handlers(), **(handlers or {})}

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise ToolNotFoundError(tool_name)
        outcome = handler(arguments) if callable(handler) else handler
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(structured_content=outcome, is_error=False)


def details(full_name="octocat/rag-demo", **kw):
    owner, name = full_name.split("/")
    base = {
        "source": "live",
        "repository": {"name": name, "full_name": full_name, "description": "d", "stars": 5},
        "default_branch": "main",
        "license": "MIT",
        "is_fork": False,
        "is_archived": False,
    }
    base.update(kw)
    return base


ROOT = {
    "entries": [
        {"path": "README.md", "entry_type": "file"},
        {"path": "pyproject.toml", "entry_type": "file"},
        {"path": "Dockerfile", "entry_type": "file"},
        {"path": "tests", "entry_type": "dir"},
        {"path": ".github", "entry_type": "dir"},
    ],
    "truncated": False,
}
PYPROJECT = '[project]\nname="x"\ndependencies=["fastapi>=0.1","qdrant-client","somethingexotic"]\n'


def _structure(args):
    if args.get("path") == ".github/workflows":
        return {"entries": [{"path": ".github/workflows/ci.yml", "entry_type": "file"}], "truncated": False}
    return ROOT


def _file(args):
    path = args["path"]
    if path == "pyproject.toml":
        return {"path": path, "content": PYPROJECT, "truncated": False}
    if path == "Dockerfile":
        return {"path": path, "content": "FROM python:3.12\n", "truncated": False}
    if path.startswith(".github/workflows/"):
        return {"path": path, "content": "name: ci\n", "truncated": False}
    return ToolExecutionError("GitHub resource not found: " + path)


def default_handlers():
    return {
        "get_github_repository": lambda a: details(f"{a['owner']}/{a['repo']}"),
        "get_repository_languages": {"languages_bytes": {"Python": 9000, "TypeScript": 1000}},
        "get_repository_readme": {"content": "Built with FastAPI and Kubernetes for RAG.", "truncated": False},
        "get_repository_structure": _structure,
        "get_repository_file": _file,
    }


def seed(db):
    skills = {
        slug: Skill(slug=slug, name=name)
        for slug, name in [
            ("python", "Python"),
            ("fastapi", "FastAPI"),
            ("docker", "Docker"),
            ("qdrant", "Qdrant"),
            ("ci-cd", "CI/CD"),
            ("rag", "RAG"),
        ]
    }
    db.add_all(skills.values())
    user = User(email="gh@example.com", password_hash="h")
    other = User(email="gh2@example.com", password_hash="h")
    db.add_all([user, other])
    db.commit()
    return user, other, skills
