"""
STT — Speech-to-text using faster-whisper (local).

Transcribes audio from a file or from a numpy audio buffer.
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("presence.voice.stt")

_model = None


def _load_model():
    """Lazy-load the Whisper model."""
    global _model
    if _model is None:
        try:
            from faster_whisper import WhisperModel
            from core.config import config
            _model = WhisperModel(
                config.WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )
            logger.info(f"Whisper model loaded: {config.WHISPER_MODEL}")
        except ImportError:
            logger.warning("faster-whisper not installed — STT disabled")
        except Exception as e:
            logger.error(f"Failed to load Whisper: {e}")
    return _model


def transcribe_file(audio_path: str | Path) -> str:
    """Transcribe an audio file to text."""
    model = _load_model()
    if model is None:
        return ""

    segments, info = model.transcribe(str(audio_path), beam_size=5)
    text = " ".join(segment.text.strip() for segment in segments)
    logger.debug(f"Transcribed ({info.language}, {info.duration:.1f}s): {text[:80]}")
    return text


def transcribe_buffer(audio_data, sample_rate: int = 16000) -> str:
    """Transcribe a numpy audio buffer."""
    import soundfile as sf

    model = _load_model()
    if model is None:
        return ""

    # Write to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, audio_data, sample_rate)
        return transcribe_file(f.name)