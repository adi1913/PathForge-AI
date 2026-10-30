import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.profile import Profile
from app.models.user import User
from app.observability.metrics import metrics
from app.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.security.deps import AuthUser, get_current_user
from app.security.passwords import hash_password, verify_against_dummy, verify_password
from app.security.throttle import LoginThrottle
from app.security.tokens import create_access_token

router = APIRouter()
logger = logging.getLogger("pathforge.auth")

_login_throttle: LoginThrottle | None = None
_register_throttle: LoginThrottle | None = None
REGISTER_MAX_PER_WINDOW = 20


def _throttles(settings: Settings) -> tuple[LoginThrottle, LoginThrottle]:
    global _login_throttle, _register_throttle
    if _login_throttle is None:
        _login_throttle = LoginThrottle(settings.LOGIN_MAX_FAILURES, settings.LOGIN_WINDOW_SECONDS)
        _register_throttle = LoginThrottle(REGISTER_MAX_PER_WINDOW, settings.LOGIN_WINDOW_SECONDS)
    assert _register_throttle is not None
    return _login_throttle, _register_throttle


def reset_throttles() -> None:
    """Test hook: forget all counters and re-read settings on next use."""
    global _login_throttle, _register_throttle
    _login_throttle = _register_throttle = None


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _user_out(user: User, settings: Settings) -> UserOut:
    admins = {e.strip().lower() for e in settings.ADMIN_EMAILS}
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.profile.display_name if user.profile else None,
        is_admin=user.email.lower() in admins,
    )


def _token_response(user: User, settings: Settings) -> TokenOut:
    issued = create_access_token(user.id, settings)
    return TokenOut(access_token=issued.token, expires_in=issued.expires_in, user=_user_out(user, settings))


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429, detail="Too many attempts. Try again later.", headers={"Retry-After": str(retry_after)}
    )


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    settings = get_settings()
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    _, register_throttle = _throttles(settings)
    key = _client(request)
    wait = register_throttle.retry_after(key)
    if wait:
        metrics.auth_event("register_throttled")
        raise _too_many(wait)
    register_throttle.record_failure(key)  # every attempt counts toward the per-address registration budget

    if not settings.PASSWORD_MIN_LENGTH <= len(payload.password) <= settings.PASSWORD_MAX_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be {settings.PASSWORD_MIN_LENGTH}-{settings.PASSWORD_MAX_LENGTH} characters",
        )
    if payload.password.strip().lower() == payload.email:
        raise HTTPException(status_code=422, detail="Password must not be your email address")
    if db.query(User).filter(User.email == payload.email).first() is not None:
        metrics.auth_event("register_duplicate")
        raise HTTPException(status_code=409, detail="That email is already registered")
    user = User(email=payload.email, password_hash=hash_password(payload.password), is_active=True)
    user.profile = Profile(display_name=payload.display_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent registration of the same email
        db.rollback()
        raise HTTPException(status_code=409, detail="That email is already registered") from exc
    db.refresh(user)
    metrics.auth_event("register_success")
    logger.info("User registered")
    return _token_response(user, settings)


@router.post("/auth/login", response_model=TokenOut)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    settings = get_settings()
    login_throttle, _ = _throttles(settings)
    key = f"{_client(request)}|{payload.email}"
    wait = login_throttle.retry_after(key)
    if wait:
        metrics.auth_event("login_throttled")
        raise _too_many(wait)

    user = db.query(User).filter(User.email == payload.email).first()
    if user is None:
        verify_against_dummy(payload.password)  # same work as a real check: no timing difference for unknown emails
        ok = False
    else:
        ok = verify_password(payload.password, user.password_hash) and user.is_active
    if not ok or user is None:
        login_throttle.record_failure(key)
        metrics.auth_event("login_failure")
        logger.info("Login failed")
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    login_throttle.clear(key)
    metrics.auth_event("login_success")
    logger.info("Login succeeded")
    return _token_response(user, settings)


@router.get("/auth/me", response_model=UserOut)
def me(auth: AuthUser = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    if not auth.authenticated or auth.id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = db.get(User, auth.id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return _user_out(user, get_settings())
