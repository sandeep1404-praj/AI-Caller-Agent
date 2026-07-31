"""Google Gemini API client using the official google-genai SDK."""

import json
import logging
import re
import time
from typing import Any

from google import genai
from google.genai import types

from ai.prompt_manager import (
    CONVERSATION_JSON_SCHEMA,
    FALLBACK_RESPONSE,
    FALLBACK_SUMMARY,
    OPENING_PROMPT_TEMPLATE,
    SUMMARY_JSON_SCHEMA,
    SUMMARY_PROMPT,
    SYSTEM_PROMPT,
)
from config import get_settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1, 2)
RETRYABLE_HINTS = (
    "429",
    "rate",
    "quota",
    "timeout",
    "timed out",
    "503",
    "500",
    "502",
    "504",
    "overloaded",
    "unavailable",
    "internal",
    "resource_exhausted",
)

REQUIRED_RESPONSE_DEFAULTS: dict[str, Any] = {
    "reply": "I'm sorry, I couldn't understand that.",
    "status": "Unknown",
    "reason": "",
    "delay_minutes": 0,
    "conversation_finished": False,
    "confidence": 0.0,
    "needs_delay_clarification": False,
}


class GeminiClient:
    """Wrapper around Google Gemini for conversation and classification."""

    def __init__(self) -> None:
        self.settings = get_settings()
        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment")
        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    def generate_opening(self, context: dict[str, str]) -> dict[str, Any]:
        """Generate the opening greeting for a call."""
        prompt = OPENING_PROMPT_TEMPLATE.format(**context)
        return self._generate(prompt, schema=CONVERSATION_JSON_SCHEMA)

    def generate_response(
        self,
        conversation_history: list[dict[str, str]],
        teacher_message: str,
    ) -> dict[str, Any]:
        """Process teacher message and return structured response."""
        history_text = self._format_history(conversation_history)
        prompt = (
            f"Conversation so far:\n{history_text}\n\n"
            f"Teacher just said: \"{teacher_message}\"\n\n"
            "Return valid JSON only with all required fields. Never use markdown."
        )
        return self._generate(prompt, schema=CONVERSATION_JSON_SCHEMA)

    def generate_summary(self, transcript: str) -> str:
        """Generate a conversation summary."""
        prompt = SUMMARY_PROMPT.format(transcript=transcript)
        result = self._generate(
            prompt,
            schema=SUMMARY_JSON_SCHEMA,
            fallback=FALLBACK_SUMMARY,
            use_conversation_config=False,
        )
        return str(result.get("summary", "No summary available."))

    def _generate(
        self,
        prompt: str,
        *,
        schema: dict | None = None,
        fallback: dict[str, Any] | None = None,
        use_conversation_config: bool = True,
    ) -> dict[str, Any]:
        """Send prompt to Gemini with retries; never raises."""
        fallback = fallback or dict(FALLBACK_RESPONSE)
        schema = schema or (CONVERSATION_JSON_SCHEMA if use_conversation_config else SUMMARY_JSON_SCHEMA)

        config_kwargs: dict[str, Any] = {
            "temperature": self.settings.gemini_temperature,
            "max_output_tokens": self.settings.gemini_max_tokens,
            "response_mime_type": "application/json",
            "response_json_schema": schema,
        }
        if use_conversation_config:
            config_kwargs["system_instruction"] = SYSTEM_PROMPT
        config = types.GenerateContentConfig(**config_kwargs)

        last_error: str | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            start = time.perf_counter()
            try:
                response = self.client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=config,
                )
                latency_ms = (time.perf_counter() - start) * 1000

                raw_text = self._extract_text(response)
                logger.info(
                    "Gemini response attempt=%d latency_ms=%.0f raw=%s",
                    attempt,
                    latency_ms,
                    (raw_text or "")[:500],
                )
                self._log_usage(response, latency_ms)

                if not raw_text or not raw_text.strip():
                    last_error = "Empty response from Gemini"
                    logger.warning("Attempt %d: %s", attempt, last_error)
                    if attempt < MAX_ATTEMPTS:
                        self._sleep_backoff(attempt)
                    continue

                parsed = self._parse_json(raw_text)
                if parsed is None:
                    last_error = "JSON parse failed"
                    logger.warning("Attempt %d: parse failure for raw response", attempt)
                    if attempt < MAX_ATTEMPTS:
                        self._sleep_backoff(attempt)
                    continue

                validated = self._validate_response(parsed, fallback)
                logger.info("Gemini parsed JSON attempt=%d: %s", attempt, validated)
                return validated

            except Exception as exc:
                latency_ms = (time.perf_counter() - start) * 1000
                last_error = str(exc)
                logger.error(
                    "Gemini API error attempt=%d latency_ms=%.0f error=%s",
                    attempt,
                    latency_ms,
                    last_error,
                )
                if attempt < MAX_ATTEMPTS and self._is_retryable(exc):
                    self._sleep_backoff(attempt)
                    continue
                if attempt >= MAX_ATTEMPTS or not self._is_retryable(exc):
                    break

        logger.error(
            "Gemini request failed after %d attempts, returning fallback. Last error: %s",
            MAX_ATTEMPTS,
            last_error,
        )
        return dict(fallback)

    @staticmethod
    def _extract_text(response: Any) -> str | None:
        """Extract text from a GenerateContentResponse."""
        if response is None:
            return None
        if getattr(response, "parsed", None) is not None:
            parsed = response.parsed
            if isinstance(parsed, dict):
                return json.dumps(parsed)
        text = getattr(response, "text", None)
        if text:
            return text.strip()
        return None

    @staticmethod
    def _log_usage(response: Any, latency_ms: float) -> None:
        usage = getattr(response, "usage_metadata", None)
        if usage:
            logger.debug(
                "Gemini token usage latency_ms=%.0f prompt=%s candidates=%s total=%s",
                latency_ms,
                getattr(usage, "prompt_token_count", None),
                getattr(usage, "candidates_token_count", None),
                getattr(usage, "total_token_count", None),
            )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(hint in message for hint in RETRYABLE_HINTS)

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        idx = min(attempt - 1, len(BACKOFF_SECONDS) - 1)
        delay = BACKOFF_SECONDS[idx]
        logger.info("Retrying Gemini request in %ds (attempt %d)", delay, attempt + 1)
        time.sleep(delay)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        """
        Parse JSON from Gemini response robustly.

        Returns None if parsing fails (caller may retry).
        Never raises.
        """
        if not text or not text.strip():
            return None

        candidates = GeminiClient._json_candidates(text)
        for candidate in candidates:
            try:
                result = json.loads(candidate)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

            repaired = GeminiClient._repair_truncated_json(candidate)
            if repaired:
                try:
                    result = json.loads(repaired)
                    if isinstance(result, dict):
                        logger.info("Repaired truncated JSON successfully")
                        return result
                except json.JSONDecodeError:
                    pass

        logger.warning("All JSON parse attempts failed for text: %s", text[:200])
        return None

    @staticmethod
    def _json_candidates(text: str) -> list[str]:
        """Produce ordered candidate strings to attempt JSON parsing."""
        cleaned = text.strip()
        candidates: list[str] = [cleaned]

        if cleaned.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```\s*$", "", stripped)
            candidates.append(stripped.strip())

        for match in re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL):
            candidates.append(match.group())

        brace_match = re.search(r"\{.*", cleaned, re.DOTALL)
        if brace_match:
            candidates.append(brace_match.group())

        seen: set[str] = set()
        unique: list[str] = []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    @staticmethod
    def _repair_truncated_json(text: str) -> str | None:
        """Attempt to close truncated JSON objects."""
        stripped = text.strip()
        if not stripped.startswith("{"):
            return None
        if stripped.endswith("}"):
            return None

        open_braces = stripped.count("{") - stripped.count("}")
        open_brackets = stripped.count("[") - stripped.count("]")
        if open_braces <= 0 and open_brackets <= 0:
            return None

        repaired = stripped.rstrip(", \n\r\t")
        repaired += "]" * max(0, open_brackets)
        repaired += "}" * max(0, open_braces)
        return repaired

    @staticmethod
    def _validate_response(
        data: dict[str, Any],
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ensure all required keys exist with sensible defaults."""
        base = dict(fallback or FALLBACK_RESPONSE)
        result = {**base, **data}

        if "summary" in base and "reply" not in base:
            if not result.get("summary"):
                result["summary"] = base.get("summary", "Summary unavailable.")
            return result

        for key, default in REQUIRED_RESPONSE_DEFAULTS.items():
            if key not in result or result[key] is None:
                result[key] = default

        try:
            result["delay_minutes"] = int(result.get("delay_minutes", 0))
        except (TypeError, ValueError):
            result["delay_minutes"] = 0

        try:
            result["confidence"] = float(result.get("confidence", 0.0))
        except (TypeError, ValueError):
            result["confidence"] = 0.0

        result["conversation_finished"] = bool(result.get("conversation_finished", False))
        result.setdefault("needs_delay_clarification", False)
        return result

    @staticmethod
    def _format_history(history: list[dict[str, str]]) -> str:
        lines = []
        for turn in history:
            role = turn.get("role", "unknown").capitalize()
            content = turn.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines) if lines else "(No prior conversation)"
