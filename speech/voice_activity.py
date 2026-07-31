"""Voice activity detection utilities."""

import logging
import struct
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)


class VoiceActivityDetector:
    """Energy-based voice activity detection for PCM bytes and numpy arrays."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        energy_threshold: float = 0.01,
        silence_duration_seconds: float = 1.5,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)
        self.energy_threshold = energy_threshold
        self.silence_frames_required = int(
            silence_duration_seconds * 1000 / frame_duration_ms
        )
        self._recent_energies: deque[float] = deque(maxlen=10)

    def compute_energy(self, audio_chunk: bytes) -> float:
        """Compute RMS energy of a PCM int16 audio chunk."""
        if not audio_chunk:
            return 0.0
        count = len(audio_chunk) // 2
        if count == 0:
            return 0.0
        samples = struct.unpack(f"{count}h", audio_chunk[: count * 2])
        sum_squares = sum(s * s for s in samples)
        rms = (sum_squares / count) ** 0.5
        normalized = rms / 32768.0
        self._recent_energies.append(normalized)
        return normalized

    def compute_energy_array(self, samples: np.ndarray) -> float:
        """Compute RMS energy of a float32 numpy audio array."""
        if samples.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
        self._recent_energies.append(rms)
        return rms

    def is_speech(self, audio_chunk: bytes) -> bool:
        """Return True if the chunk likely contains speech."""
        return self.compute_energy(audio_chunk) > self.energy_threshold

    def is_speech_array(self, samples: np.ndarray) -> bool:
        """Return True if the numpy array likely contains speech."""
        return self.compute_energy_array(samples) > self.energy_threshold

    def is_silence_after_speech(self, speech_detected: bool, consecutive_silence: int) -> bool:
        """Return True when silence follows detected speech."""
        if not speech_detected:
            return False
        return consecutive_silence >= self.silence_frames_required

    @property
    def average_energy(self) -> float:
        if not self._recent_energies:
            return 0.0
        return sum(self._recent_energies) / len(self._recent_energies)
