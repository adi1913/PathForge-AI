"""Password hashing with scrypt (stdlib, memory-hard). Stored format: ``scrypt$N$r$p$salt_b64$hash_b64``.

Parameters live in the stored string so they can be raised later without breaking existing hashes.
"""

import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1
_DKLEN = 32
_MAXMEM = 64 * 1024 * 1024


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=_DKLEN, maxmem=_MAXMEM)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(_derive(password, salt, _N, _R, _P))}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check. Any malformed/unknown stored value (e.g. the old seed placeholder) is simply False."""
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        actual = _derive(password, base64.b64decode(salt_b64), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# A real hash of a random value, used so that logging in as an unknown email costs the same as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def verify_against_dummy(password: str) -> None:
    verify_password(password, _DUMMY_HASH)
