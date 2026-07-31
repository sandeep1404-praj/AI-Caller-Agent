"""Lightweight audio playback — pygame primary, miniaudio fallback."""

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import pygame

    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    pygame = None  # type: ignore[assignment]

try:
    import miniaudio

    MINIAUDIO_AVAILABLE = True
except ImportError:
    MINIAUDIO_AVAILABLE = False
    miniaudio = None  # type: ignore[assignment]


class AudioPlayer:
    """Play audio files and block until playback completes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pygame_initialized = False
        self._stop_requested = False

        if not PYGAME_AVAILABLE and not MINIAUDIO_AVAILABLE:
            raise RuntimeError(
                "No audio playback backend found. Install pygame or miniaudio: "
                "pip install pygame  OR  pip install miniaudio"
            )

    def _ensure_pygame(self) -> None:
        if not self._pygame_initialized and PYGAME_AVAILABLE:
            pygame.mixer.init()
            self._pygame_initialized = True

    def play(self, file_path: Path, block: bool = True) -> None:
        """Play an audio file. Blocks until finished when block=True."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        with self._lock:
            self._stop_requested = False
            logger.debug("Playing audio: %s", path.name)

            if PYGAME_AVAILABLE:
                try:
                    self._play_pygame(path, block)
                    return
                except RuntimeError:
                    if not MINIAUDIO_AVAILABLE:
                        raise

            if MINIAUDIO_AVAILABLE:
                self._play_miniaudio(path, block)
            else:
                raise RuntimeError("No audio playback backend available")

    def _play_pygame(self, path: Path, block: bool) -> None:
        self._ensure_pygame()
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
        except pygame.error as exc:
            logger.warning("pygame playback failed: %s", exc)
            raise RuntimeError(f"pygame playback failed: {exc}") from exc

        if block:
            while pygame.mixer.music.get_busy() and not self._stop_requested:
                pygame.time.wait(50)

    def _play_miniaudio(self, path: Path, block: bool) -> None:
        stream = miniaudio.stream_file(str(path))
        with miniaudio.PlaybackDevice() as device:
            device.start(stream)
            if block:
                while device.running and not self._stop_requested:
                    time.sleep(0.05)

    def stop(self) -> None:
        """Stop any ongoing playback."""
        with self._lock:
            self._stop_requested = True
            if PYGAME_AVAILABLE and self._pygame_initialized:
                try:
                    pygame.mixer.music.stop()
                except pygame.error as exc:
                    logger.debug("Stop playback error: %s", exc)

    def is_playing(self) -> bool:
        with self._lock:
            if PYGAME_AVAILABLE and self._pygame_initialized:
                return pygame.mixer.music.get_busy()
            return False
