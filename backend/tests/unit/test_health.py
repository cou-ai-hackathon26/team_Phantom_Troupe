import asyncio

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app
from app.services import health_service
from app.services.health_service import redact, run_health_checks


async def _ok() -> str:
    return "fine"


async def _boom() -> str:
    raise RuntimeError("connection refused")


async def _slow() -> str:
    await asyncio.sleep(10)
    return "never"


def test_all_ok() -> None:
    report = asyncio.run(run_health_checks({"a": _ok, "b": _ok}))
    assert report.status == "ok"
    assert report.services["a"].detail == "fine"


def test_failure_marks_degraded() -> None:
    report = asyncio.run(run_health_checks({"a": _ok, "b": _boom}))
    assert report.status == "degraded"
    assert not report.services["b"].ok
    assert "connection refused" in report.services["b"].detail


def test_timeout(monkeypatch) -> None:
    monkeypatch.setattr(health_service.settings, "health_check_timeout_s", 0.05)
    report = asyncio.run(run_health_checks({"slow": _slow}))
    assert report.services["slow"].detail.startswith("timeout")


def test_redact_hides_secrets() -> None:
    cfg = Settings(groq_api_key="gsk_supersecret", _env_file=None)
    assert "gsk_supersecret" not in redact("bad key gsk_supersecret here", cfg)


def test_health_route(monkeypatch) -> None:
    monkeypatch.setattr(health_service, "CHECKS", {"postgres": _ok, "groq": _boom})
    resp = TestClient(app).get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["services"]["postgres"]["ok"] is True


def test_async_url_forces_asyncpg() -> None:
    from app.db.session import async_url

    assert async_url("postgresql://u:p@h:5432/db") == "postgresql+asyncpg://u:p@h:5432/db"
    assert async_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert async_url("postgresql+asyncpg://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    # unescaped '@' in the password is encoded; an already-encoded one is left alone
    assert async_url("postgresql://user.ref:pa@ss1@host.example:5432/postgres") == (
        "postgresql+asyncpg://user.ref:pa%40ss1@host.example:5432/postgres"
    )
    assert async_url("postgresql://u:pa%40ss@h/db") == "postgresql+asyncpg://u:pa%40ss@h/db"
