"""Print OK/FAIL for Postgres, Qdrant and Groq. Never prints keys.

Usage (from backend/):  python scripts/check_connections.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.health_service import check_groq, check_postgres, check_qdrant, run_health_checks  # noqa: E402


async def main() -> int:
    report = await run_health_checks({"postgres": check_postgres, "qdrant": check_qdrant, "groq": check_groq})
    for name, status in report.services.items():
        print(f"{'OK  ' if status.ok else 'FAIL'}  {name:<9} {status.detail}")
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
