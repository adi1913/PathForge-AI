"""Request authentication and identity binding.

Identity comes ONLY from the verified bearer token. A ``user_id`` in a query/body/form is just an assertion that must
match; it is never proof of identity. With ``AUTH_REQUIRED=false`` (local/test only) the old trusted-caller behaviour
is restored and ``bind`` returns the supplied value unchanged.
"""

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.observability.metrics import metrics
from app.security.tokens import InvalidTokenError, decode_access_token

logger = logging.getLogger("pathforge.security")
_bearer = HTTPBearer(auto_error=False, description="Access token from POST /api/auth/login")


@dataclass(frozen=True)
class AuthUser:
    id: str | None
    email: str | None
    authenticated: bool  # False only in the AUTH_REQUIRED=false trusted-caller mode

    def bind(self, user_id: str | None) -> str | None:
        """The effective user id for this request: the token's user. A supplied id must equal it (else 403)."""
        if not self.authenticated:
            return user_id
        if user_id is None or user_id == self.id:
            return self.id
        metrics.auth_event("user_id_mismatch")
        raise HTTPException(status_code=403, detail="user_id does not match the authenticated user")


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> AuthUser:
    settings = get_settings()
    if not settings.AUTH_REQUIRED:
        return AuthUser(id=None, email=None, authenticated=False)
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        metrics.auth_event("missing_token")
        raise _unauthorized()
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as exc:
        metrics.auth_event("invalid_token")
        logger.info("Rejected access token: %s", exc)  # reason class only, never the token
        raise _unauthorized("Invalid or expired token") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        metrics.auth_event("inactive_or_unknown_user")
        raise _unauthorized("Invalid or expired token")
    return AuthUser(id=user.id, email=user.email, authenticated=True)


def require_admin(auth: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not auth.authenticated:  # trusted-caller (local/test) mode
        return auth
    admins = {e.strip().lower() for e in get_settings().ADMIN_EMAILS}
    if not auth.email or auth.email.lower() not in admins:
        metrics.auth_event("admin_denied")
        raise HTTPException(status_code=403, detail="Administrator access required")
    return auth


async def enforce_user_binding(request: Request, auth: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Router-level guard: any ``user_id`` the caller supplies (query, JSON body or form field) must be the token's
    user. This is the one place that stops a caller from acting as someone else, so no handler can forget it.
    (FastAPI has already read and cached the body by the time dependencies run.)"""
    if not auth.authenticated:
        return auth
    claimed: list[object] = [request.query_params.get("user_id")]
    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            body = await request.json()
        except ValueError:
            body = None  # FastAPI reports malformed JSON as a 422
        if isinstance(body, dict):
            claimed.append(body.get("user_id"))
    elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        claimed.append(form.get("user_id"))
    for value in claimed:
        if value is not None:
            auth.bind(str(value))
    return auth
