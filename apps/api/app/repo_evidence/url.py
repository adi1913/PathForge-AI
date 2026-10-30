import re

from app.repo_evidence.errors import InvalidRepositoryUrlError

_NAME = r"[A-Za-z0-9._-]{1,100}"
_URL_RE = re.compile(rf"^https://(?:www\.)?github\.com/({_NAME})/({_NAME})/?$")
_SHORT_RE = re.compile(rf"^({_NAME})/({_NAME})$")


def parse_repository_ref(value: str) -> tuple[str, str]:
    """Only github.com repository URLs or owner/repo are accepted — the API never fetches the URL;
    just the owner/repo pair is passed on to the GitHub MCP server."""
    text = (value or "").strip()
    match = _URL_RE.match(text) or _SHORT_RE.match(text)
    if match is None:
        raise InvalidRepositoryUrlError()
    owner, repo = match.group(1), match.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    if owner in {".", ".."} or repo in {".", "..", ""}:
        raise InvalidRepositoryUrlError()
    return owner, repo
