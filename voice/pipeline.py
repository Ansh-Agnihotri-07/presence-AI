"""
Voice Pipeline — Orchestrates recording, VAD, STT, and dispatch.

Manages the microphone stream, detects speech, transcribes it,
and publishes the result to the event bus.
"""

import asyncio
import logging
from typing import Any, Optional

from core.event_bus import event_bus
from voice.vad import VoiceActivityDetector
from voice.stt import transcribe_buffer
from voice.tts import speak

logger = logging.getLogger("presence.voice.pipeline")


class VoicePipeline:
    """Full voice I/O pipeline: mic → VAD → STT → event bus, and TTS output."""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.vad = VoiceActivityDetector(sample_rate=sample_rate)
        self._recording = False
        self._audio_buffer: list[Any] = []
        self._stream: Any = None
        self._running = False

    async def start(self):
        """Start the voice pipeline (mic input + TTS output handler)."""
        self._running = True

        # Subscribe to TTS requests
        event_bus.subscribe("tts_request", self._handle_tts)

        # Start mic listening in a background thread
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, self._listen_mic)
        logger.info("Voice pipeline started")

    async def stop(self):
        """Stop the voice pipeline."""
        self._running = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        logger.info("Voice pipeline stopped")

    def _listen_mic(self) -> None:
        """Background thread: read mic, run VAD, collect speech segments."""
        try:
            import sounddevice as sd
        except ImportError:
            logger.warning("sounddevice not installed — voice input disabled")
            return

        frame_samples = self.vad.frame_size
        block_size = frame_samples

        def audio_callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            if status:
                logger.warning(f"Audio status: {status}")
            if not self._running:
                return

            import numpy as np

            # Convert to 16-bit PCM for VAD
            audio_int16 = (indata[:, 0] * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()

            transition = self.vad.process_frame(audio_bytes)

            if transition == "speech_start":
                self._recording = True
                self._audio_buffer = []
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    event_bus.publish("stt_active", {}),
                )

            if self._recording:
                self._audio_buffer.append(indata[:, 0].copy())

            if transition == "speech_end" and self._recording:
                self._recording = False
                import numpy as np
                full_audio = np.concatenate(self._audio_buffer)
                self._audio_buffer = []
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(
                    asyncio.ensure_future,
                    self._process_speech(full_audio),
                )

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=block_size,
                callback=audio_callback,
            )
            self._stream.start()
            logger.info("Microphone stream started")

            # Keep the thread alive
            import time
            while self._running:
                time.sleep(0.1)
        except Exception as e:
            logger.error(f"Microphone error: {e}")

    async def _process_speech(self, audio_data: Any) -> None:
        """Transcribe speech and publish as user input."""
        logger.debug(f"Processing speech segment")

        text = transcribe_buffer(audio_data, self.sample_rate)
        text = text.strip()

        if text and len(text) > 1:
            logger.info(f"Transcribed: {text[:80]}")
            await event_bus.publish("user_input", {"text": text, "mode": "voice"})
        else:
            await event_bus.publish("idle", {})

    async def _handle_tts(self, data: dict[str, Any]) -> None:
        """Handle TTS request events."""
        text = data.get("text", "")
        if text:
            await speak(text)


# Global singleton
voice_pipeline = VoicePipeline()