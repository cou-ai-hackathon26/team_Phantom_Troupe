"""Text-to-speech (ElevenLabs) with the network mocked. All text is synthetic placeholder text."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.main import app
from app.models.tts_client import ElevenLabsClient, TTSError, TTSQuotaExceeded
from app.services import tts_service

AUDIO = b"ID3fake-mp3-bytes" * 50
ANSWER = "এটি একটি নমুনা উত্তর [১]। দ্বিতীয় নমুনা বাক্য [২]।"


@pytest.fixture(autouse=True)
def _tts_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "elevenlabs_api_key", SecretStr("test-key"))
    monkeypatch.setattr(settings, "tts_enabled", True)
    monkeypatch.setattr(settings, "tts_cache_dir", tmp_path / "tts")
    tts_service._pending.clear()
    tts_service._inflight.clear()


def _client(handler, calls: list[httpx.Request] | None = None) -> ElevenLabsClient:  # noqa: ANN001
    def record(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return handler(request)

    return ElevenLabsClient("test-key", client=httpx.AsyncClient(transport=httpx.MockTransport(record)), backoff_s=0)


def ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=AUDIO, headers={"content-type": "audio/mpeg"})


# --- text cleaning -------------------------------------------------------------------------------


def test_clean_removes_markers_links_and_markdown() -> None:
    text = "**নমুনা শিরোনাম**\n\n- প্রথম নমুনা বিষয় [১]\n- দ্বিতীয় বিষয় [C2] দেখুন https://example.gov.bd/x ।"
    out = tts_service.clean_for_speech(text)
    assert "[" not in out and "*" not in out and "http" not in out
    assert out == "নমুনা শিরোনাম\nপ্রথম নমুনা বিষয়\nদ্বিতীয় বিষয় দেখুন।"  # no stray spaces left


def test_clean_cuts_long_text_at_a_sentence_end() -> None:
    sentence = "এটি একটি দীর্ঘ নমুনা বাক্য। "
    out = tts_service.clean_for_speech(sentence * 40, max_chars=100)
    assert len(out) <= 100
    assert out.endswith("।")


# --- token ---------------------------------------------------------------------------------------


def test_token_only_for_official_answers_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    assert tts_service.speech_token(ANSWER)
    assert tts_service.speech_token(ANSWER, user_doc_id="doc-1") is None  # personal docs never leave the server
    monkeypatch.setattr(settings, "elevenlabs_api_key", None)
    assert tts_service.speech_token(ANSWER) is None


def test_prepare_rejects_text_that_was_not_signed() -> None:
    token = tts_service.speech_token(ANSWER)
    assert token
    with pytest.raises(tts_service.InvalidSpeechToken):
        tts_service.prepare("অন্য কোনো নমুনা লেখা", token)
    prepared = tts_service.prepare(ANSWER, token)
    assert tts_service.KEY_RE.match(prepared.key) and not prepared.cached


# --- streaming + cache ---------------------------------------------------------------------------


async def test_stream_sends_bangla_model_and_caches_audio() -> None:
    calls: list[httpx.Request] = []
    key = tts_service.prepare(ANSWER, tts_service.speech_token(ANSWER) or "").key
    stream = await tts_service.open_audio(key, _client(ok, calls))
    assert b"".join([chunk async for chunk in stream]) == AUDIO

    body = json.loads(calls[0].content)
    assert body["model_id"] == settings.tts_model_id and body["language_code"] == "bn"
    assert "[" not in body["text"]
    assert calls[0].headers["xi-api-key"] == "test-key"
    path = tts_service.cached_path(key)
    assert path is not None and path.read_bytes() == AUDIO
    assert not list(settings.tts_cache_dir.glob("*.part"))
    assert not tts_service.is_generating(key)


async def test_retries_rate_limit_then_succeeds() -> None:
    replies = iter([httpx.Response(429, json={"detail": {"status": "too_many_concurrent_requests"}})])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(replies, None) or ok(request)

    calls: list[httpx.Request] = []
    response = await _client(handler, calls).open_stream("নমুনা")
    await response.aclose()
    assert len(calls) == 2


async def test_quota_error_is_reported_and_nothing_cached() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": {"status": "quota_exceeded", "message": "x"}})

    key = tts_service.prepare(ANSWER, tts_service.speech_token(ANSWER) or "").key
    with pytest.raises(TTSQuotaExceeded):
        await tts_service.open_audio(key, _client(handler))
    assert tts_service.cached_path(key) is None
    assert not tts_service.is_generating(key)


async def test_server_errors_give_up_after_three_retries() -> None:
    calls: list[httpx.Request] = []
    with pytest.raises(TTSError):
        await _client(lambda _: httpx.Response(503, json={"detail": "down"}), calls).open_stream("নমুনা")
    assert len(calls) == 4


async def test_synthesize_to_cache_pays_only_once() -> None:
    calls: list[httpx.Request] = []
    client = _client(ok, calls)
    first = await tts_service.synthesize_to_cache(ANSWER, client)
    second = await tts_service.synthesize_to_cache(ANSWER, client)
    assert first is not None and first == second
    assert len(calls) == 1


# --- routes --------------------------------------------------------------------------------------


def test_routes_reject_bad_token_and_unknown_audio() -> None:
    api = TestClient(app)
    bad = api.post("/api/v1/tts", json={"text": ANSWER, "token": "x" * 43})
    assert bad.status_code == 403
    assert api.get(f"/api/v1/tts/{'0' * 64}.mp3").status_code == 404
    assert api.get("/api/v1/tts/..%2Fsecret.mp3").status_code == 404


def test_routes_serve_cached_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    api = TestClient(app)
    token = tts_service.speech_token(ANSWER)
    reply = api.post("/api/v1/tts", json={"text": ANSWER, "token": token})
    assert reply.status_code == 200
    url = reply.json()["audio_url"]
    key = url.rsplit("/", 1)[-1].removesuffix(".mp3")
    settings.tts_cache_dir.mkdir(parents=True, exist_ok=True)
    (settings.tts_cache_dir / f"{key}.mp3").write_bytes(AUDIO)
    audio = api.get(url)
    assert audio.status_code == 200 and audio.content == AUDIO
    assert audio.headers["content-type"] == "audio/mpeg"


def test_disabled_tts_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tts_enabled", False)
    reply = TestClient(app).post("/api/v1/tts", json={"text": ANSWER, "token": "x" * 43})
    assert reply.status_code == 503 and reply.json()["detail"]["code"] == "tts_disabled"
