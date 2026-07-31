"""Text-to-speech module using edge-tts via AudioManager."""

import asyncio
import logging

from speech.audio_manager import AudioManager

logger = logging.getLogger(__name__)


class TextToSpeech:
    """Convert text to spoken audio via AudioManager (edge-tts + pygame)."""

    def __init__(self, audio_manager: AudioManager | None = None) -> None:
        self._audio_manager = audio_manager or AudioManager()

    def speak(self, text: str, block: bool = True) -> None:
        """Speak the given text aloud."""
        if not text.strip():
            return

        if block:
            asyncio.run(self._audio_manager.speak(text))
        else:
            asyncio.create_task(self._audio_manager.speak(text))

    def stop(self) -> None:
        """Stop any ongoing speech."""
        self._audio_manager.stop_playback()
