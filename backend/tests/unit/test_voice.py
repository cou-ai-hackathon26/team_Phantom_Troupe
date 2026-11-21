"""Voice endpoint tests: real ffmpeg on a tiny generated WAV, Groq Whisper mocked."""

import io
import math
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import audio_utils, stt_service
from app.services.audio_utils import AudioError, ffmpeg_available, wav_16k_mono

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")


def tone_wav(seconds: float = 0.5, rate: int = 44100, amplitude: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<hh", s, s)
            for s in (int(amplitude * math.sin(2 * math.pi * 440 * i / rate)) for i in range(int(seconds * rate)))
        )
        w.writeframes(frames)
    return buf.getvalue()


async def test_converts_to_16k_mono_and_deletes_temp_files() -> None:
    async with wav_16k_mono(tone_wav(), ".wav") as path:
        kept: Path = path
        with wave.open(str(path)) as w:
            assert w.getnchannels() == 1
            assert w.getframerate() == 16000
    assert not kept.exists() and not kept.parent.exists()


async def test_rejects_empty_and_too_long(monkeypatch) -> None:
    with pytest.raises(AudioError):
        async with wav_16k_mono(b"", ".wav"):
            pass
    monkeypatch.setattr(audio_utils, "MAX_AUDIO_SECONDS", 0.2)
    with pytest.raises(AudioError, match="৩০ সেকেন্ডের"):
        async with wav_16k_mono(tone_wav(1.0), ".wav"):
            pass


async def test_rejects_garbage_audio() -> None:
    with pytest.raises(AudioError):
        async with wav_16k_mono(b"not really audio at all", ".webm"):
            pass


def test_suffix_detection() -> None:
    assert stt_service.suffix_for("audio/webm;codecs=opus", None) == ".webm"
    assert stt_service.suffix_for("audio/mp4", None) == ".mp4"
    assert stt_service.suffix_for(None, "rec.ogg") == ".ogg"


def test_transcribe_endpoint_with_mocked_whisper(monkeypatch) -> None:
    seen: dict[str, int] = {}

    async def fake_whisper(wav_bytes: bytes) -> str:
        seen["bytes"] = len(wav_bytes)
        return "  লে-অফ হলে কী পাব?  "

    monkeypatch.setattr(stt_service, "_whisper", fake_whisper)
    resp = TestClient(app).post("/api/v1/chat/voice/transcribe", files={"audio": ("rec.wav", tone_wav(), "audio/wav")})
    assert resp.status_code == 200
    assert resp.json() == {"transcript": "লে-অফ হলে কী পাব?"}
    assert seen["bytes"] > 1000


def test_empty_transcript_is_422_in_bangla(monkeypatch) -> None:
    async def fake_whisper(wav_bytes: bytes) -> str:
        return ""

    monkeypatch.setattr(stt_service, "_whisper", fake_whisper)
    resp = TestClient(app).post("/api/v1/chat/voice/transcribe", files={"audio": ("rec.wav", tone_wav(), "audio/wav")})
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "empty_transcript"


def test_bad_audio_is_422(monkeypatch) -> None:
    resp = TestClient(app).post(
        "/api/v1/chat/voice/transcribe", files={"audio": ("rec.webm", b"garbage", "audio/webm")}
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "bad_audio"


async def test_silence_is_rejected_before_whisper() -> None:
    with pytest.raises(AudioError, match="কোনো কথা শোনা যায়নি"):
        async with wav_16k_mono(tone_wav(0.5, amplitude=0), ".wav"):
            pass


def test_prompt_echo_detection() -> None:
    assert stt_service.is_prompt_echo("প্রতিবন্ধী ভাতা")
    assert stt_service.is_prompt_echo("নামজারি, খতিয়ান।")
    assert not stt_service.is_prompt_echo("প্রতিবন্ধী ভাতা কত টাকা?")
    assert not stt_service.is_prompt_echo("")


def test_prompt_echo_becomes_empty_transcript(monkeypatch) -> None:
    async def fake_whisper(wav_bytes: bytes) -> str:
        return "প্রতিবন্ধী ভাতা"

    monkeypatch.setattr(stt_service, "_whisper", fake_whisper)
    resp = TestClient(app).post("/api/v1/chat/voice/transcribe", files={"audio": ("r.wav", tone_wav(), "audio/wav")})
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "empty_transcript"
