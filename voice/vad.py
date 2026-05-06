"""
VAD — Voice Activity Detection.

Uses webrtcvad to detect when the user starts and stops speaking.
This is used to trim silence and trigger STT only when speech is detected.
"""

import logging
import collections
from typing import Any, Optional

logger = logging.getLogger("presence.voice.vad")


class VoiceActivityDetector:
    """
    Simple voice activity detector using webrtcvad.

    Buffers audio frames and detects speech start/end transitions.
    """

    def __init__(self, sample_rate: int = 16000, frame_ms: int = 30, aggressiveness: int = 2):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_size = int(sample_rate * frame_ms / 1000)  # samples per frame
        self._vad: Any = None
        self._ring_buffer: collections.deque[bool] = collections.deque(maxlen=10)
        self._triggered = False
        self._aggressiveness = aggressiveness

        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(aggressiveness)
            logger.info(f"VAD initialized (aggressiveness={aggressiveness})")
        except ImportError:
            logger.warning("webrtcvad not installed — VAD disabled")

    def is_speech(self, audio_chunk: bytes) -> bool:
        """Check if an audio chunk contains speech."""
        if self._vad is None:
            return True  # If no VAD, assume always speech

        try:
            return self._vad.is_speech(audio_chunk, self.sample_rate)
        except Exception:
            return False

    def process_frame(self, audio_chunk: bytes) -> Optional[str]:
        """
        Process a single audio frame.

        Returns:
            'speech_start' — when speech begins
            'speech_end' — when speech stops
            None — no transition
        """
        if self._vad is None:
            return None

        is_speech = self.is_speech(audio_chunk)
        self._ring_buffer.append(is_speech)

        speech_ratio = sum(self._ring_buffer) / len(self._ring_buffer)

        if not self._triggered:
            if speech_ratio > 0.6:
                self._triggered = True
                return "speech_start"
        else:
            if speech_ratio < 0.2:
                self._triggered = False
                return "speech_end"

        return None