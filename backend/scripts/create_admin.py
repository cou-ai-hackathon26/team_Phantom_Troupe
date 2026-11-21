"""Create an admin account, or reset its password (stored as a scrypt hash in admin_users).

Usage (from backend/):
    python scripts/create_admin.py admin@example.com            # asks for the password (not echoed)
    python scripts/create_admin.py admin@example.com --password '…'
Never commit passwords; change weak ones after setup.
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import Base  # noqa: E402
from app.db.session import get_engine  # noqa: E402
from app.services.admin_users import upsert_admin  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("email")
    ap.add_argument("--password", default=None)
    args = ap.parse_args()
    password = args.password or getpass.getpass("Password: ")
    if len(password) < 8:
        print("FAIL  password must have at least 8 characters")
        return 1
    async with get_engine().begin() as conn:  # make sure admin_users exists
        await conn.run_sync(Base.metadata.create_all)
    created = await upsert_admin(args.email, password)
    print(f"OK    admin {args.email.strip().lower()} {'created' if created else 'password updated'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
