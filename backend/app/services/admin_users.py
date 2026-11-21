"""Admin accounts in Postgres (`admin_users`). Passwords are only ever stored as scrypt hashes."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.security import hash_password, verify_password
from app.db.models import AdminUser
from app.db.session import get_sessionmaker

# Verified against when the email is unknown, so timing does not reveal which emails exist.
_DUMMY_HASH = hash_password("timing-equaliser")


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def upsert_admin(email: str, password: str) -> bool:
    """Create the admin, or reset the password if the email exists. Returns True if newly created."""
    email = normalize_email(email)
    async with get_sessionmaker()() as session:
        existed = (await session.execute(select(AdminUser.id).where(AdminUser.email == email))).first() is not None
        stmt = insert(AdminUser).values(email=email, password_hash=hash_password(password))
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[AdminUser.email], set_={"password_hash": stmt.excluded.password_hash}
            )
        )
        await session.commit()
    return not existed


async def authenticate(email: str, password: str) -> bool:
    email = normalize_email(email)
    async with get_sessionmaker()() as session:
        user = (await session.execute(select(AdminUser).where(AdminUser.email == email))).scalar_one_or_none()
        if user is None:
            verify_password(password, _DUMMY_HASH)
            return False
        if not verify_password(password, user.password_hash):
            return False
        user.last_login_at = datetime.now(UTC)
        await session.commit()
        return True


async def admin_count() -> int:
    async with get_sessionmaker()() as session:
        return int((await session.execute(select(func.count()).select_from(AdminUser))).scalar_one())
