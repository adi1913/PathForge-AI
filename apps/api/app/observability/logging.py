"""Central logging: request-id correlation, optional JSON output, and redaction of secrets in every emitted line."""

import json
import logging
import re
import sys

from app.core.config import Settings
from app.observability.context import get_request_id

REDACTED = "[REDACTED]"
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"), "[REDACTED_JWT]"),
    (re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{10,}"), "[REDACTED_KEY]"),
    (
        re.compile(
            r"(?i)([\"']?[\w-]*(?:password|passwd|pwd|secret|token|api[_-]?key|authorization)[\w-]*[\"']?\s*[:=]\s*)"
            r"(\"[^\"]*\"|'[^']*'|[^\s,;&}]+)"
        ),
        r"\1" + REDACTED,
    ),
]


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFormatter(logging.Formatter):
    """Redacts the final line, which includes exception tracebacks."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str))


_HANDLER_FLAG = "_pathforge_handler"
_factory_installed = False


def _install_record_factory() -> None:
    global _factory_installed
    if _factory_installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.request_id = get_request_id()
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


def configure_logging(settings: Settings) -> None:
    """Idempotent. Replaces only the handler this function installed earlier; leaves foreign handlers alone."""
    _install_record_factory()
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _HANDLER_FLAG, False)]:
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    setattr(handler, _HANDLER_FLAG, True)
    if settings.LOG_FORMAT == "json":
        handler.setFormatter(RedactingJsonFormatter())
    else:
        handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL)
    # Our access log replaces uvicorn's (which prints raw paths with query strings).
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
