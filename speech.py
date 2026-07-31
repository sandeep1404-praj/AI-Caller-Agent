"""Speech-to-text and text-to-speech adapters."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class SpeechToTextProvider(ABC):
    """Convert audio into text."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        """Transcribe audio to text."""


class TextToSpeechProvider(ABC):
    """Convert text into audio bytes."""

    @abstractmethod
    def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        """Synthesize text into audio."""


@dataclass(slots=True)
class OpenAISpeechToTextProvider(SpeechToTextProvider):
    """OpenAI Whisper/STT implementation."""

    api_key: str
    model: str = "whisper-1"

    def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        if not self.api_key:
            return ""
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        transcript = client.audio.transcriptions.create(
            model=self.model,
            file=("audio.wav", audio_bytes),
            language=language,
        )
        return getattr(transcript, "text", "")


@dataclass(slots=True)
class DeepgramSpeechToTextProvider(SpeechToTextProvider):
    """Deepgram speech recognition adapter."""

    api_key: str
    model: str = "nova-2"

    def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        if not self.api_key:
            return ""
        from deepgram import DeepgramClient, PrerecordedOptions, FileSource

        client = DeepgramClient(self.api_key)
        payload: FileSource = {"buffer": audio_bytes}
        options = PrerecordedOptions(model=self.model, language=language, smart_format=True)
        response = client.listen.prerecorded.v("1").transcribe_file(payload, options)
        return response.results.channels[0].alternatives[0].transcript


@dataclass(slots=True)
class OpenAITTSProvider(TextToSpeechProvider):
    """OpenAI text-to-speech adapter."""

    api_key: str
    model: str = "gpt-4o-mini-tts"

    def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        if not self.api_key:
            return b""
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.audio.speech.create(model=self.model, voice=voice, input=text)
        return response.read()


@dataclass(slots=True)
class ElevenLabsTTSProvider(TextToSpeechProvider):
    """ElevenLabs text-to-speech adapter."""

    api_key: str
    voice_id: str = ""

    def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        if not self.api_key:
            return b""
        import requests

        headers = {
            "xi-api-key": self.api_key,
            "content-type": "application/json",
        }
        payload = {"text": text, "model_id": "eleven_multilingual_v2"}
        endpoint = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id or voice}"
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content


class NullSpeechToTextProvider(SpeechToTextProvider):
    """Safe fallback used when an API key is not configured."""

    def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        return ""


class NullTextToSpeechProvider(TextToSpeechProvider):
    """Safe fallback used when TTS is disabled."""

    def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        return b""


def build_speech_to_text_provider(config) -> SpeechToTextProvider:
    """Create the configured STT provider with a safe fallback."""

    provider_name = (config.stt_provider or "").strip().lower()
    if provider_name == "openai" and config.openai_api_key:
        return OpenAISpeechToTextProvider(config.openai_api_key, model=config.openai_stt_model)
    if provider_name == "deepgram" and config.deepgram_api_key:
        return DeepgramSpeechToTextProvider(config.deepgram_api_key)
    return NullSpeechToTextProvider()


def build_text_to_speech_provider(config) -> TextToSpeechProvider:
    """Create the configured TTS provider with a safe fallback."""

    provider_name = (config.tts_provider or "").strip().lower()
    if provider_name == "openai" and config.openai_api_key:
        return OpenAITTSProvider(config.openai_api_key, model=config.openai_tts_model)
    if provider_name == "elevenlabs" and config.elevenlabs_api_key:
        return ElevenLabsTTSProvider(config.elevenlabs_api_key)
    return NullTextToSpeechProvider()
