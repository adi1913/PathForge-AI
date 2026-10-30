"""
Structured error types for MCP tool implementations.

The rule enforced everywhere these are used: an exception's *message* is
the only thing that may ever reach the model/user, and that message must
never contain a token, an Authorization header value, or a raw stack
trace. Provider code catches the real (potentially sensitive) exception,
logs it safely via `safe_log_exception`, and re-raises one of these with
a clean message instead.
"""
import logging
import re

from mcp.server.mcpserver.exceptions import ToolError as MCPToolError

logger = logging.getLogger("pathforge.mcp")

# Matches common ways a secret could leak into a log/exception message:
# "Bearer <token>", "token=<value>", "Authorization: <value>".
_SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(authorization[:=]\s*)\S+"),
    re.compile(r"(?i)(token[:=]\s*)\S+"),
    re.compile(r"(?i)(api[_-]?key[:=]\s*)\S+"),
]


def redact(text: str) -> str:
    """Best-effort redaction for anything logged. Defense in depth on
    top of "never put secrets in messages in the first place" — not a
    substitute for that discipline."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def safe_log_exception(context: str, exc: Exception) -> None:
    logger.warning("%s: %s: %s", context, type(exc).__name__, redact(str(exc)))


class ToolError(MCPToolError):
    """Base class for all user/agent-facing MCP tool errors.

    Subclasses the SDK's own ToolError deliberately: the SDK only sends a
    raised exception's message to the client when it recognizes the
    exception as an intentional ToolError — any other exception is
    treated as an internal bug and its message is suppressed from the
    client by default (logged server-side only). Raising one of these
    (rather than a raw httpx/library exception) is what makes an
    intended, safe error message actually reach the caller, while
    genuine bugs stay hidden."""

    def __init__(self, message: str, *, code: str = "tool_error"):
        super().__init__(message)
        self.code = code
        self.message = message


class InvalidArgumentsError(ToolError):
    def __init__(self, message: str):
        super().__init__(message, code="invalid_arguments")


class ProviderUnavailableError(ToolError):
    """Raised when DEMO_MODE=false and the required provider credentials
    are missing — this must be a clear, actionable error, never a silent
    fallback to fake data."""

    def __init__(self, message: str):
        super().__init__(message, code="provider_unavailable")


class UpstreamError(ToolError):
    """Wraps a failure from an external API (HTTP error, malformed
    response, timeout) with a message safe to show the caller."""

    def __init__(self, message: str):
        super().__init__(message, code="upstream_error")


class RateLimitedError(ToolError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None):
        super().__init__(message, code="rate_limited")
        self.retry_after_seconds = retry_after_seconds
