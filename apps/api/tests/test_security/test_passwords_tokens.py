import base64
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import Settings
from app.security.passwords import hash_password, verify_against_dummy, verify_password
from app.security.tokens import AUDIENCE, ISSUER, InvalidTokenError, create_access_token, decode_access_token

SETTINGS = Settings(SECRET_KEY="k" * 64)


def test_hash_is_scrypt_salted_and_not_plaintext():
    h1, h2 = hash_password("s3cret-password"), hash_password("s3cret-password")
    assert h1.startswith("scrypt$") and "s3cret-password" not in h1
    assert h1 != h2  # per-user random salt


def test_verify_accepts_correct_and_rejects_wrong():
    h = hash_password("s3cret-password")
    assert verify_password("s3cret-password", h)
    assert not verify_password("s3cret-passwor", h)
    assert not verify_password("", h)


@pytest.mark.parametrize(
    "bad", ["", "not-a-real-hash-demo-only", "scrypt$", "scrypt$x$y$z$a$b", "scrypt$16384$8$1$!!$!!", "plaintext", "h"]
)
def test_malformed_hashes_are_rejected_without_raising(bad):
    assert verify_password("anything", bad) is False


def test_tampered_hash_fails():
    parts = hash_password("s3cret-password").split("$")
    raw = bytearray(base64.b64decode(parts[-1] + "=="))
    raw[0] ^= 1
    parts[-1] = base64.b64encode(bytes(raw)).decode().rstrip("=")
    assert not verify_password("s3cret-password", "$".join(parts))


def test_dummy_verification_does_not_raise():
    verify_against_dummy("whatever")


def _encode(claims, key=SETTINGS.SECRET_KEY, alg="HS256"):
    return jwt.encode(claims, key, algorithm=alg)


def _claims(**over):
    now = datetime.now(timezone.utc)
    base = {
        "sub": "u1",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": ISSUER,
        "aud": AUDIENCE,
    }
    return {**base, **over}


def test_token_round_trip_and_expiry_metadata():
    issued = create_access_token("user-1", SETTINGS)
    assert decode_access_token(issued.token, SETTINGS) == "user-1"
    assert issued.expires_in == SETTINGS.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def test_expired_token_rejected():
    past = datetime.now(timezone.utc) - timedelta(days=2)
    issued = create_access_token("user-1", SETTINGS, now=past)
    with pytest.raises(InvalidTokenError):
        decode_access_token(issued.token, SETTINGS)


@pytest.mark.parametrize(
    "token",
    [
        "",
        "garbage",
        "a.b.c",
        _encode(_claims(aud="someone-else")),
        _encode(_claims(iss="someone-else")),
        _encode(_claims(), key="x" * 40),
        _encode({k: v for k, v in _claims().items() if k != "exp"}),
        _encode({k: v for k, v in _claims().items() if k != "sub"}),
        _encode(_claims(sub="")),
        _encode(_claims(), key=SETTINGS.SECRET_KEY * 2, alg="HS512"),
    ],
)
def test_untrustworthy_tokens_rejected(token):
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)


def test_alg_none_rejected():
    token = jwt.encode(_claims(), None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)


def test_tampered_payload_rejected():
    head, _, sig = create_access_token("user-1", SETTINGS).token.split(".")
    forged = base64.urlsafe_b64encode(b'{"sub":"user-2"}').decode().rstrip("=")
    with pytest.raises(InvalidTokenError):
        decode_access_token(f"{head}.{forged}.{sig}", SETTINGS)
