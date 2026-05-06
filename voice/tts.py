"""
TTS — Text-to-speech output using edge-tts (async, high quality).

Falls back to pyttsx3 if edge-tts is unavailable.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger("presence.voice.tts")


async def speak(text: str, voice: str | None = None):
    """
    Speak the given text aloud.

    Uses edge-tts (async, high quality) as primary engine.
    Falls back to pyttsx3 (offline) if edge-tts fails.
    """
    from core.config import config
    voice = voice or config.TTS_VOICE

    try:
        await _speak_edge_tts(text, voice)
    except Exception as e:
        logger.warning(f"edge-tts failed ({e}), trying pyttsx3 fallback")
        _speak_pyttsx3(text)


async def _speak_edge_tts(text: str, voice: str):
    """Speak using edge-tts (Microsoft Edge online TTS)."""
    import edge_tts

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(tmp_path)

    # Play the audio
    _play_audio(tmp_path)

    # Cleanup
    try:
        Path(tmp_path).unlink()
    except OSError:
        pass


def _speak_pyttsx3(text: str):
    """Offline TTS fallback using pyttsx3."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 170)
        engine.setProperty("volume", 0.9)
        engine.say(text)
        engine.runAndWait()
    except ImportError:
        logger.error("pyttsx3 not installed — TTS unavailable")
    except Exception as e:
        logger.error(f"pyttsx3 failed: {e}")


def _play_audio(path: str):
    """Play an audio file using sounddevice + soundfile."""
    try:
        import sounddevice as sd
        import soundfile as sf
        data, samplerate = sf.read(path)
        sd.play(data, samplerate)
        sd.wait()
    except ImportError:
        logger.warning("sounddevice/soundfile not available — using playsound")
        try:
            import subprocess
            subprocess.Popen(
                ["powershell", "-c", f'(New-Object Media.SoundPlayer "{path}").PlaySync()'],
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            ).wait()
        except Exception as e:
            logger.error(f"Audio playback failed: {e}")