"""Dependency-manifest parsing. Pure functions; malformed input raises ManifestError so the
caller records a limitation instead of guessing."""

import json
import re
import tomllib


class ManifestError(ValueError):
    pass


_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _req_name(spec: str) -> str | None:
    match = _REQ_NAME.match(spec)
    return match.group(1).lower().replace("_", "-") if match else None


def parse_requirements_txt(text: str) -> list[str]:
    names = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "git+", "http")):
            continue
        name = _req_name(line)
        if name:
            names.append(name)
    return names


def _load_toml(text: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError("invalid TOML") from exc


def parse_pyproject(text: str) -> list[str]:
    data = _load_toml(text)
    names: list[str] = []
    project = data.get("project", {})
    deps = project.get("dependencies", [])
    if not isinstance(deps, list):
        raise ManifestError("project.dependencies is not a list")
    names += [n for spec in deps if isinstance(spec, str) and (n := _req_name(spec))]
    for group in (project.get("optional-dependencies") or {}).values():
        if isinstance(group, list):
            names += [n for spec in group if isinstance(spec, str) and (n := _req_name(spec))]
    poetry = (data.get("tool") or {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry, dict):
        names += [k.lower().replace("_", "-") for k in poetry if k.lower() != "python"]
    return names


def parse_pipfile(text: str) -> list[str]:
    data = _load_toml(text)
    names: list[str] = []
    for section in ("packages", "dev-packages"):
        block = data.get(section, {})
        if isinstance(block, dict):
            names += [k.lower().replace("_", "-") for k in block]
    return names


def parse_package_json(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestError("invalid JSON") from exc
    if not isinstance(data, dict):
        raise ManifestError("package.json is not an object")
    names: list[str] = []
    for section in ("dependencies", "devDependencies"):
        block = data.get(section, {})
        if isinstance(block, dict):
            names += [k.lower() for k in block]
    return names


PARSERS = {
    "requirements.txt": parse_requirements_txt,
    "pyproject.toml": parse_pyproject,
    "Pipfile": parse_pipfile,
    "package.json": parse_package_json,
}
# Present-and-noted but not parsed (no parser written); reported as a limitation, never guessed.
UNPARSED = ("go.mod", "Cargo.toml", "pom.xml")
