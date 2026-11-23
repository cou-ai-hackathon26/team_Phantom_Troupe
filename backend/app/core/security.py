"""Admin authentication.

- Admins log in with email + password (table `admin_users`). Passwords are stored as salted scrypt hashes.
- A successful login returns a signed session token (HMAC-SHA256 with APP_SECRET_KEY, expires after
  ADMIN_SESSION_HOURS), sent back as `Authorization: Bearer …`.
- ADMIN_TOKEN, if set, is also accepted as a static key (for scripts/curl).
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from functools import lru_cache

from fastapi import Header, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

# scrypt parameters (n=2^14, r=8, p=1: ~16 MB, fast enough for a login, slow for brute force)
_N, _R, _P, _DKLEN = 2**14, 8, 1, 64


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@lru_cache
def _secret() -> bytes:
    if settings.app_secret_key is not None:
        return settings.app_secret_key.get_secret_value().encode()
    logger.warning("APP_SECRET_KEY not set: using a random key, admin sessions end when the API restarts")
    return secrets.token_bytes(32)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_text(purpose: str, text: str) -> str:
    """HMAC tag proving the API produced `text` (e.g. an answer the 🔊 button may send to TTS)."""
    return _b64(hmac.new(_secret(), f"{purpose}\0{text}".encode(), hashlib.sha256).digest())


def verify_text(purpose: str, text: str, tag: str) -> bool:
    return hmac.compare_digest(sign_text(purpose, text), tag)


def create_session_token(email: str, hours: int | None = None) -> tuple[str, int]:
    exp = int(time.time()) + 3600 * (hours or settings.admin_session_hours)
    payload = _b64(json.dumps({"sub": email, "exp": exp}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}", exp


def verify_session_token(token: str) -> str | None:
    """Returns the admin email, or None if the token is invalid or expired."""
    try:
        payload, sig = token.split(".")
        expected = _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(payload))
        if int(data["exp"]) < time.time():
            return None
        return str(data["sub"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


UNAUTHORIZED = HTTPException(401, detail={"code": "unauthorized", "message": "আবার লগইন করুন।"})


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: returns the admin's email (or "token" for the static ADMIN_TOKEN)."""
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token:
        raise UNAUTHORIZED
    if settings.admin_token is not None and hmac.compare_digest(
        token.encode(), settings.admin_token.get_secret_value().encode()
    ):
        return "token"
    email = verify_session_token(token)
    if email is None:
        raise UNAUTHORIZED
    return email
