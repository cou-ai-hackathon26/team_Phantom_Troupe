"""Tests never touch real services: no database (query logs, cache, feedback stay in-process)."""

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _no_external_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_url", None)
