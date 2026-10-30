"""Signed access tokens (JWT, HS256). Stateless: a token stays valid until it expires (documented limitation)."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import Settings

ISSUER = "pathforge-api"
AUDIENCE = "pathforge-web"
ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    """Any reason a token cannot be trusted (missing parts, bad signature, expired, wrong audience...)."""


@dataclass(frozen=True)
class IssuedToken:
    token: str
    expires_at: datetime
    expires_in: int


def create_access_token(user_id: str, settings: Settings, now: datetime | None = None) -> IssuedToken:
    issued = now or datetime.now(timezone.utc)
    expires = issued + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    claims = {
        "sub": user_id,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": ISSUER,
        "aud": AUDIENCE,
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)
    return IssuedToken(token=token, expires_at=expires, expires_in=int((expires - issued).total_seconds()))


def decode_access_token(token: str, settings: Settings) -> str:
    """Return the user id (``sub``) or raise InvalidTokenError. The algorithm is pinned, never read from the token."""
    try:
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(type(exc).__name__) from exc
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise InvalidTokenError("bad subject")
    return sub
