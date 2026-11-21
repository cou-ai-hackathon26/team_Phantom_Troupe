"""Admin authentication: a single shared token from .env (ADMIN_TOKEN), sent as `Authorization: Bearer …`."""

import hmac

from fastapi import Header, HTTPException

from app.core.config import settings


def require_admin(authorization: str | None = Header(default=None)) -> None:
    if settings.admin_token is None:
        raise HTTPException(
            503, detail={"code": "admin_disabled", "message": "অ্যাডমিন প্যানেল চালু নেই (.env-এ ADMIN_TOKEN দিন)।"}
        )
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token.encode(), settings.admin_token.get_secret_value().encode()):
        raise HTTPException(401, detail={"code": "unauthorized", "message": "অ্যাডমিন টোকেন সঠিক নয়।"})
