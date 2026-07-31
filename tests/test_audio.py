"""Unit tests for the audio layer."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from speech.audio_manager import AudioManager
from speech.voice_activity import VoiceActivityDetector


class TestVoiceActivityDetector:
    def test_silence_array(self):
        vad = VoiceActivityDetector(energy_threshold=0.01)
        silence = np.zeros(1600, dtype=np.float32)
        assert vad.is_speech_array(silence) is False

    def test_speech_array(self):
        vad = VoiceActivityDetector(energy_threshold=0.01)
        speech = np.random.uniform(-0.5, 0.5, 1600).astype(np.float32)
        assert vad.is_speech_array(speech) is True


class TestAudioManager:
    def test_is_microphone_available(self):
        with patch("speech.audio_manager.sd.query_devices") as mock_devices:
            mock_devices.return_value = [
                {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0},
            ]
            assert AudioManager.is_microphone_available() is True

    def test_record_timeout_returns_none(self):
        manager = AudioManager()
        with patch("speech.audio_manager.sd.InputStream") as mock_stream:
            mock_stream.return_value.__enter__.return_value.read.return_value = (
                np.zeros((1600, 1), dtype=np.float32),
                False,
            )
            with patch("speech.audio_manager.time.time") as mock_time:
                mock_time.side_effect = [0, 0, 20]
                result = manager.record(timeout=1, phrase_limit=5)
        assert result is None

    @pytest.mark.asyncio
    async def test_speak_generates_and_plays(self):
        manager = AudioManager()
        with patch.object(manager, "_generate_speech", new_callable=AsyncMock) as mock_gen:
            mock_path = Path("/tmp/test.mp3")
            mock_gen.return_value = mock_path
            with patch.object(manager.player, "play") as mock_play:
                await manager.speak("Hello Professor")
                mock_gen.assert_called_once_with("Hello Professor")
                mock_play.assert_called_once_with(mock_path, True)

    def test_cleanup_removes_temp_files(self, tmp_path):
        manager = AudioManager()
        temp_file = tmp_path / "test.wav"
        temp_file.write_bytes(b"RIFF")
        manager._temp_files.append(temp_file)
        manager.cleanup()
        assert not temp_file.exists()
        assert manager._temp_files == []


class TestSpeechToTextInterface:
    def test_listen_uses_audio_manager(self):
        from speech.speech_to_text import SpeechToText

        mock_manager = MagicMock()
        wav = Path("/tmp/recording.wav")
        mock_manager.record.return_value = wav

        with patch("speech.speech_to_text.sr") as mock_sr:
            mock_sr.AudioFile.return_value.__enter__ = MagicMock()
            mock_sr.AudioFile.return_value.__exit__ = MagicMock(return_value=False)
            stt = SpeechToText(audio_manager=mock_manager)
            stt.recognizer = MagicMock()
            stt.recognizer.record.return_value = MagicMock()
            stt.recognizer.recognize_google.return_value = "Yes I am available"

            with patch.object(stt, "_recognize", return_value="Yes I am available"):
                with patch("speech.speech_to_text.sr.AudioFile"):
                    result = stt.listen(timeout=5, phrase_limit=10)

        mock_manager.record.assert_called_once()
        assert result == "Yes I am available"
