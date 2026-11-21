"""Admin login (email + password from the admin_users table) -> signed session token."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import log_event
from app.core.security import create_session_token
from app.services import admin_users

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("adhikarai.admin")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    token: str
    email: str
    expires_at: int  # unix seconds


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    if settings.database_url is None:
        raise HTTPException(503, detail={"code": "db_unavailable", "message": "ডাটাবেস সংযোগ নেই, লগইন করা যাচ্ছে না।"})
    try:
        ok = await admin_users.authenticate(body.email, body.password)
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin login db error", extra={"data": {"error": type(exc).__name__}})
        raise HTTPException(
            503, detail={"code": "db_unavailable", "message": "ডাটাবেস সংযোগে সমস্যা। আবার চেষ্টা করুন।"}
        ) from exc
    email = admin_users.normalize_email(body.email)
    log_event(logger, "admin login", email=email, ok=ok)
    if not ok:
        await asyncio.sleep(0.5)  # slow down guessing
        raise HTTPException(401, detail={"code": "bad_credentials", "message": "ইমেইল বা পাসওয়ার্ড সঠিক নয়।"})
    token, exp = create_session_token(email)
    return LoginResponse(token=token, email=email, expires_at=exp)
