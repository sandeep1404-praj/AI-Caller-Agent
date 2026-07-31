"""Central audio abstraction — all mic/speaker access goes through here."""

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from config import get_settings
from speech.audio_player import AudioPlayer
from speech.voice_activity import VoiceActivityDetector

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1


class AudioManager:
    """
    Unified audio layer for recording and playback.

    Provides record(), play(), speak(), and cleanup().
    No other module should access microphones or speakers directly.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.sample_rate = SAMPLE_RATE
        self.channels = CHANNELS
        self.player = AudioPlayer()
        self.vad = VoiceActivityDetector(
            sample_rate=self.sample_rate,
            energy_threshold=self.settings.silence_threshold,
            silence_duration_seconds=self.settings.silence_duration_seconds,
        )
        self._temp_files: list[Path] = []

    def record(
        self,
        timeout: float | None = None,
        phrase_limit: float | None = None,
    ) -> Path | None:
        """
        Record microphone audio to a temporary WAV file.

        Uses silence detection to stop after the speaker finishes.
        Returns None on timeout with no speech detected.
        """
        timeout = timeout or self.settings.speech_listen_timeout_seconds
        phrase_limit = phrase_limit or self.settings.speech_phrase_limit_seconds

        chunk_duration = 0.1
        chunk_samples = int(self.sample_rate * chunk_duration)
        silence_chunks_needed = max(
            1, int(self.settings.silence_duration_seconds / chunk_duration)
        )

        recorded_chunks: list[np.ndarray] = []
        speech_started = False
        speech_start_time: float | None = None
        consecutive_silence = 0
        record_start = time.time()

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
            ) as stream:
                while True:
                    elapsed = time.time() - record_start

                    if not speech_started and elapsed >= timeout:
                        logger.warning("Recording timeout — no speech detected")
                        return None

                    if speech_started and speech_start_time is not None:
                        if (time.time() - speech_start_time) >= phrase_limit:
                            logger.debug("Phrase limit reached")
                            break
                        if consecutive_silence >= silence_chunks_needed:
                            logger.debug("Silence detected after speech")
                            break

                    chunk, overflowed = stream.read(chunk_samples)
                    if overflowed:
                        logger.warning("Audio input buffer overflow")

                    samples = chunk.flatten()
                    recorded_chunks.append(samples.copy())

                    if self.vad.is_speech_array(samples):
                        if not speech_started:
                            logger.debug("Speech detected, recording...")
                            speech_start_time = time.time()
                        speech_started = True
                        consecutive_silence = 0
                    elif speech_started:
                        consecutive_silence += 1

        except sd.PortAudioError as exc:
            logger.error("Microphone error: %s", exc)
            raise OSError(f"Microphone not available: {exc}") from exc
        except Exception as exc:
            logger.error("Recording error: %s", exc)
            raise

        if not speech_started or not recorded_chunks:
            return None

        audio_data = np.concatenate(recorded_chunks)
        wav_path = self._create_temp_path(".wav")
        sf.write(wav_path, audio_data, self.sample_rate)
        self._temp_files.append(wav_path)
        logger.info("Recorded %.1fs of audio", len(audio_data) / self.sample_rate)
        return wav_path

    def play(self, file_path: Path, block: bool = True) -> None:
        """Play an audio file through speakers."""
        self.player.play(Path(file_path), block=block)

    async def speak(self, text: str) -> None:
        """Generate speech with edge-tts and play it."""
        if not text.strip():
            return

        logger.info("Speaking: %s", text[:80])
        mp3_path = await self._generate_speech(text)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.player.play, mp3_path, True)
        finally:
            self._remove_temp(mp3_path)

    def stop_playback(self) -> None:
        """Stop any ongoing audio playback."""
        self.player.stop()

    def cleanup(self) -> None:
        """Remove all tracked temporary files and stop playback."""
        self.stop_playback()
        for path in self._temp_files:
            self._remove_temp(path)
        self._temp_files.clear()

    def cleanup_file(self, path: Path) -> None:
        """Remove a single temporary file."""
        self._remove_temp(path)
        if path in self._temp_files:
            self._temp_files.remove(path)

    @staticmethod
    def is_microphone_available() -> bool:
        """Check if an input audio device is available."""
        try:
            devices = sd.query_devices()
            if isinstance(devices, dict):
                return devices.get("max_input_channels", 0) > 0
            return any(d.get("max_input_channels", 0) > 0 for d in devices)
        except Exception:
            return False

    async def _generate_speech(self, text: str) -> Path:
        import edge_tts

        voice = self.settings.tts_voice
        mp3_path = self._create_temp_path(".mp3")
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(mp3_path))
        self._temp_files.append(mp3_path)
        return mp3_path

    def _create_temp_path(self, suffix: str) -> Path:
        fd, raw_path = tempfile.mkstemp(suffix=suffix, prefix="caller_agent_")
        os.close(fd)
        return Path(raw_path)

    @staticmethod
    def _remove_temp(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
                logger.debug("Removed temp file: %s", path.name)
        except OSError as exc:
            logger.warning("Failed to remove temp file %s: %s", path, exc)
