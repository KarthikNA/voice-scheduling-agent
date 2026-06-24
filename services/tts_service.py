import asyncio
import os
import subprocess
import tempfile
from pathlib import Path


def is_configured() -> bool:
    """Return True if a Speechmatics API key is present in the environment."""
    return bool(os.getenv("SPEECHMATICS_API_KEY", "").strip())


def speak(text: str) -> None:
    """
    Convert text to speech via Speechmatics TTS and play it through the system speaker.
    Silently skips if SPEECHMATICS_API_KEY is not set, the SDK is not installed,
    or any runtime error occurs — the caller always continues normally.
    """
    api_key = os.getenv("SPEECHMATICS_API_KEY", "").strip()
    if not api_key:
        return

    try:
        asyncio.run(_speak_async(text, api_key))
    except Exception:
        pass  # TTS failure is non-fatal; text is already shown in the terminal


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
        # afplay is available on macOS; swap for 'aplay' on Linux
        subprocess.run(["afplay", tmp_path], check=True)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
