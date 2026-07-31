"""Unit tests for GeminiClient."""

from unittest.mock import MagicMock, patch

import pytest

from ai.gemini_client import GeminiClient
from ai.prompt_manager import FALLBACK_RESPONSE


class TestParseJson:
    def test_parse_json_clean(self):
        result = GeminiClient._parse_json('{"reply": "Hello", "status": "Pending"}')
        assert result is not None
        assert result["reply"] == "Hello"

    def test_parse_json_with_markdown(self):
        text = '```json\n{"reply": "Hello", "status": "Available"}\n```'
        result = GeminiClient._parse_json(text)
        assert result is not None
        assert result["status"] == "Available"

    def test_parse_json_with_surrounding_text(self):
        text = 'Here is the response: {"reply": "Hi", "status": "Pending"} end.'
        result = GeminiClient._parse_json(text)
        assert result is not None
        assert result["reply"] == "Hi"

    def test_parse_json_invalid_returns_none(self):
        result = GeminiClient._parse_json("not json at all")
        assert result is None

    def test_parse_json_truncated_repair(self):
        text = '{"reply": "Hello", "status": "Pending", "reason": "", "delay_minutes": 0'
        result = GeminiClient._parse_json(text)
        assert result is not None
        assert result["reply"] == "Hello"


class TestValidateResponse:
    def test_fills_missing_keys(self):
        result = GeminiClient._validate_response({"reply": "Hello"})
        assert result["reply"] == "Hello"
        assert result["status"] == "Unknown"
        assert result["confidence"] == 0.0
        assert result["conversation_finished"] is False

    def test_summary_validation(self):
        from ai.prompt_manager import FALLBACK_SUMMARY

        result = GeminiClient._validate_response({}, fallback=FALLBACK_SUMMARY)
        assert "summary" in result


class TestGenerateFallback:
    def test_generate_returns_fallback_on_api_failure(self):
        with patch("ai.gemini_client.get_settings") as mock_settings:
            mock_settings.return_value.gemini_api_key = "test-key"
            mock_settings.return_value.gemini_model = "gemini-2.5-flash"
            mock_settings.return_value.gemini_temperature = 0.3
            mock_settings.return_value.gemini_max_tokens = 1024

            client = GeminiClient.__new__(GeminiClient)
            client.settings = mock_settings.return_value
            client.client = MagicMock()
            client.client.models.generate_content.side_effect = Exception("503 unavailable")

            result = client._generate("test prompt")
            assert result["reply"] == FALLBACK_RESPONSE["reply"]
            assert result["status"] == "Unknown"

    def test_generate_retries_on_empty_response(self):
        with patch("ai.gemini_client.get_settings") as mock_settings:
            mock_settings.return_value.gemini_api_key = "test-key"
            mock_settings.return_value.gemini_model = "gemini-2.5-flash"
            mock_settings.return_value.gemini_temperature = 0.3
            mock_settings.return_value.gemini_max_tokens = 1024

            client = GeminiClient.__new__(GeminiClient)
            client.settings = mock_settings.return_value
            client.client = MagicMock()

            empty_response = MagicMock()
            empty_response.text = ""
            empty_response.parsed = None
            empty_response.usage_metadata = None

            good_response = MagicMock()
            good_response.text = '{"reply":"OK","status":"Available","reason":"","delay_minutes":0,"conversation_finished":true,"confidence":0.9}'
            good_response.parsed = None
            good_response.usage_metadata = None

            client.client.models.generate_content.side_effect = [
                empty_response,
                good_response,
            ]

            with patch("ai.gemini_client.time.sleep"):
                result = client._generate("test")

            assert result["reply"] == "OK"
            assert client.client.models.generate_content.call_count == 2
