import asyncio
import os
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

import certifi

# On macOS, Python from python.org ships without system root certificates,
# which causes SSL verification failures for any HTTPS library (aiohttp, httpx, etc.).
# Patching ssl.create_default_context here makes certifi's bundle the global default,
# fixing the issue for the Speechmatics SDK and every other library in the process.
_original_create_default_context = ssl.create_default_context


def _certifi_default_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
    if cafile is None and capath is None and cadata is None:
        cafile = certifi.where()
    return _original_create_default_context(purpose, cafile=cafile, capath=capath, cadata=cadata)


ssl.create_default_context = _certifi_default_context


def check() -> list[str]:
    """
    Run a quick pre-flight check and return a list of problem strings.
    An empty list means everything looks OK.
    """
    problems = []

    api_key = os.getenv("SPEECHMATICS_API_KEY", "").strip()
    if not api_key:
        problems.append("SPEECHMATICS_API_KEY is not set in .env")

    try:
        import certifi  # noqa: F401
    except ImportError:
        problems.append("certifi is not installed — run: pip install certifi")

    try:
        from speechmatics.tts import AsyncClient, Voice, OutputFormat  # noqa: F401
    except ImportError as e:
        problems.append(f"speechmatics-tts SDK not importable: {e}")

    if not Path("/usr/bin/afplay").exists():
        problems.append("afplay not found — audio playback unavailable on this system")

    return problems


def is_configured() -> bool:
    """Return True if a Speechmatics API key is present in the environment."""
    return bool(os.getenv("SPEECHMATICS_API_KEY", "").strip())


def speak(text: str) -> None:
    """
    Convert text to speech via Speechmatics TTS and play it through the system speaker.
    Errors are printed to stderr so they are always visible in the terminal.
    The session is never interrupted by a TTS failure.
    """
    api_key = os.getenv("SPEECHMATICS_API_KEY", "").strip()
    if not api_key:
        return

    try:
        asyncio.run(_speak_async(text, api_key))
    except Exception as e:
        print(f"\n[TTS error: {type(e).__name__}: {e}]", file=sys.stderr)


async def _speak_async(text: str, api_key: str) -> None:
    from speechmatics.tts import AsyncClient, Voice, OutputFormat

    client = AsyncClient(api_key=api_key)
    try:
        response = await client.generate(
            text=text,
            voice=Voice.SARAH,      # clearest, most natural female voice for a healthcare context
            output_format=OutputFormat.WAV_16000,
        )
        audio_data = await response.read()
    finally:
        await client.close()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    try:
        subprocess.run(["afplay", tmp_path], check=True)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
