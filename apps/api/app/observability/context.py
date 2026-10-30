"""Per-request correlation id carried through log records via a context variable."""

import re
import uuid
from contextvars import ContextVar

_request_id: ContextVar[str] = ContextVar("request_id", default="-")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def resolve_request_id(inbound: str | None) -> str:
    """Accept a caller-supplied id only when it is a short, safe token (no log injection); otherwise mint one."""
    if inbound and _SAFE_ID.match(inbound):
        return inbound
    return uuid.uuid4().hex
