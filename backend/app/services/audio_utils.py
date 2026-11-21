"""Audio conversion with ffmpeg: any browser recording (webm/ogg/mp4/wav) -> 16 kHz mono WAV.

Files live in a private temp dir that is deleted as soon as the caller is done (no recordings kept).
"""

import asyncio
import json
import re
import shutil
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 30.0
SILENCE_MAX_DB = -45.0  # loudest sample quieter than this = nothing was said
FFMPEG_TIMEOUT_S = 20.0


class AudioError(ValueError):
    """Bad/unsupported/too-long audio. The message is user-facing Bangla."""


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


async def _run(*args: str) -> tuple[int, bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=FFMPEG_TIMEOUT_S)
    except TimeoutError:
        proc.kill()
        raise AudioError("অডিও প্রক্রিয়া করতে বেশি সময় লাগছে। ছোট করে আবার বলুন।") from None
    return proc.returncode or 0, out, err


async def probe_duration(path: Path) -> float:
    code, out, _ = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path))
    if code != 0:
        raise AudioError("অডিও ফাইলটি পড়া যায়নি। আবার রেকর্ড করুন।")
    try:
        return float(json.loads(out)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


async def max_volume_db(path: Path) -> float:
    """Peak level in dBFS via ffmpeg volumedetect (-inf for digital silence)."""
    _, _, err = await _run(
        "ffmpeg", "-nostdin", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"
    )
    m = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", err.decode("utf-8", "replace"))
    if not m:
        return 0.0
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


@asynccontextmanager
async def wav_16k_mono(data: bytes, suffix: str = ".webm") -> AsyncIterator[Path]:
    """Write the upload to a temp dir, convert to 16 kHz mono WAV, yield its path, then delete everything."""
    if not data:
        raise AudioError("কোনো অডিও পাওয়া যায়নি। আবার বলুন।")
    if len(data) > MAX_AUDIO_BYTES:
        raise AudioError("রেকর্ডিংটি অনেক বড়। ৩০ সেকেন্ডের মধ্যে প্রশ্ন বলুন।")
    tmp = Path(tempfile.mkdtemp(prefix="adhikarai-audio-"))
    try:
        src = tmp / f"input{suffix if suffix.startswith('.') else '.' + suffix}"
        src.write_bytes(data)
        duration = await probe_duration(src)
        if duration > MAX_AUDIO_SECONDS + 0.5:
            raise AudioError("রেকর্ডিংটি ৩০ সেকেন্ডের বেশি। ছোট করে আবার বলুন।")
        dst = tmp / "audio.wav"
        code, _, _ = await _run(
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src),
            "-ac", "1", "-ar", "16000", "-t", str(MAX_AUDIO_SECONDS), "-f", "wav", str(dst),
        )  # fmt: skip
        if code != 0 or not dst.exists():
            raise AudioError("অডিও রূপান্তর করা যায়নি। আবার রেকর্ড করুন।")
        if await max_volume_db(dst) < SILENCE_MAX_DB:
            raise AudioError("কোনো কথা শোনা যায়নি। মাইক্রোফোনের কাছে গিয়ে আবার বলুন।")
        yield dst
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
