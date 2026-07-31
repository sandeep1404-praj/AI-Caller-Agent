"""Speech-to-text module using SpeechRecognition + sounddevice recording."""

import logging

from config import get_settings
from speech.audio_manager import AudioManager

logger = logging.getLogger(__name__)

try:
    import speech_recognition as sr

    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    sr = None  # type: ignore[assignment]


class SpeechToText:
    """Convert microphone audio to text via AudioManager recording."""

    def __init__(self, audio_manager: AudioManager | None = None) -> None:
        if not SR_AVAILABLE:
            raise RuntimeError(
                "SpeechRecognition is not installed. Run: pip install SpeechRecognition"
            )
        self.settings = get_settings()
        self.audio_manager = audio_manager or AudioManager()
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = self.settings.silence_duration_seconds

    def listen(self, timeout: float | None = None, phrase_limit: float | None = None) -> str | None:
        """
        Record from microphone via AudioManager and return transcribed text.

        Returns None if no speech detected or recognition fails.
        """
        timeout = timeout or self.settings.speech_listen_timeout_seconds
        phrase_limit = phrase_limit or self.settings.speech_phrase_limit_seconds

        wav_path = None
        try:
            wav_path = self.audio_manager.record(timeout=timeout, phrase_limit=phrase_limit)
            if wav_path is None:
                return None

            with sr.AudioFile(str(wav_path)) as source:
                audio = self.recognizer.record(source)
            return self._recognize(audio)
        except OSError:
            raise
        except sr.RequestError as exc:
            logger.error("Speech recognition service error: %s", exc)
            raise
        finally:
            if wav_path is not None:
                self.audio_manager.cleanup_file(wav_path)

    def _recognize(self, audio: sr.AudioData) -> str | None:
        """Try Google Web Speech API (free tier), fall back to Sphinx."""
        try:
            text = self.recognizer.recognize_google(audio)
            logger.info("Recognized (Google): %s", text)
            return text
        except sr.UnknownValueError:
            logger.warning("Could not understand audio")
            return None
        except sr.RequestError:
            logger.warning("Google STT unavailable, trying offline Sphinx")
            try:
                text = self.recognizer.recognize_sphinx(audio)
                logger.info("Recognized (Sphinx): %s", text)
                return text
            except sr.UnknownValueError:
                return None

    def is_microphone_available(self) -> bool:
        """Check if a microphone is connected."""
        if not SR_AVAILABLE:
            return False
        return AudioManager.is_microphone_available()
