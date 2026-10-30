"""Startup safety checks for non-local environments."""

from app.core.config import Settings

_DEFAULT_KEYS = {"change-me-in-env", "change-me-in-production", "changeme", ""}
MIN_SECRET_LENGTH = 32


def unsafe_settings(settings: Settings) -> list[str]:
    """Problems that make staging/production unsafe. Empty for local/test (where they are only warnings)."""
    problems: list[str] = []
    if settings.SECRET_KEY in _DEFAULT_KEYS or len(settings.SECRET_KEY) < MIN_SECRET_LENGTH:
        problems.append(f"SECRET_KEY must be set to a random value of at least {MIN_SECRET_LENGTH} characters")
    if not settings.AUTH_REQUIRED:
        problems.append("AUTH_REQUIRED must be true")
    if settings.DEBUG:
        problems.append("DEBUG must be false")
    return problems


def validate_settings(settings: Settings) -> list[str]:
    """Raise for unsafe staging/production settings; return warnings for local/test."""
    problems = unsafe_settings(settings)
    if settings.ENVIRONMENT in ("staging", "production"):
        if problems:
            raise RuntimeError("Unsafe configuration for " + settings.ENVIRONMENT + ": " + "; ".join(problems))
        return []
    return [p for p in problems if not p.startswith("DEBUG")]  # DEBUG=true is the normal local default
