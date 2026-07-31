"""LLM-backed response classification for teacher conversations."""
from __future__ import annotations

from dataclasses import asdict
import json
import re
from typing import Any

from models import CallDecision, LectureRecord
from utils import read_text_file


class ResponseInterpreter:
    """Convert free-form teacher replies into structured JSON."""

    def __init__(self, api_key: str, model: str, prompts_dir) -> None:
        self.api_key = api_key
        self.model = model
        self.prompts_dir = prompts_dir

    def interpret(self, transcript: str, lecture: LectureRecord) -> CallDecision:
        """Classify the response using OpenAI when available, otherwise fall back to heuristics."""

        cleaned_transcript = (transcript or "").strip()
        if not cleaned_transcript:
            return CallDecision(status="No Response", confidence=0.0, raw_text=transcript)

        if self.api_key:
            parsed = self._interpret_with_openai(cleaned_transcript, lecture)
            if parsed is not None:
                return parsed

        return self._heuristic_interpret(cleaned_transcript)

    def _interpret_with_openai(self, transcript: str, lecture: LectureRecord) -> CallDecision | None:
        """Ask the LLM for a schema-constrained classification."""

        try:
            from openai import OpenAI
        except Exception:
            return None

        prompt_path = self.prompts_dir / "teacher_prompt.txt"
        system_prompt = read_text_file(prompt_path) if prompt_path.exists() else self._fallback_prompt()
        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "teacher_name": lecture.teacher_name,
                            "subject": lecture.subject,
                            "lecture_date": lecture.lecture_date.isoformat(),
                            "lecture_time": lecture.lecture_time.strftime("%H:%M"),
                            "transcript": transcript,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        return self._parse_json_response(content, transcript)

    def _parse_json_response(self, content: str, transcript: str) -> CallDecision:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return self._heuristic_interpret(transcript)

        return CallDecision(
            status=str(payload.get("status", "No Response")),
            delay_minutes=int(payload.get("delay_minutes", 0) or 0),
            reason=str(payload.get("reason", "")),
            confidence=float(payload.get("confidence", 0.0) or 0.0),
            normalized_text=str(payload.get("normalized_text", transcript)),
            raw_text=transcript,
            metadata={key: value for key, value in payload.items() if key not in {"status", "delay_minutes", "reason", "confidence", "normalized_text"}},
        )

    def _heuristic_interpret(self, transcript: str) -> CallDecision:
        text = transcript.lower().strip()
        normalized_text = re.sub(r"\s+", " ", text)

        if any(keyword in normalized_text for keyword in ["voicemail", "leave a message"]):
            return CallDecision(status="Voicemail", reason="Voicemail detected", confidence=0.94, normalized_text=normalized_text, raw_text=transcript)
        if any(keyword in normalized_text for keyword in ["busy", "line busy", "engaged"]):
            return CallDecision(status="Busy", reason="Busy line detected", confidence=0.92, normalized_text=normalized_text, raw_text=transcript)
        if any(keyword in normalized_text for keyword in ["on leave", "leave", "casual leave", "sick leave"]):
            return CallDecision(status="Leave", reason="Teacher reported leave", confidence=0.96, normalized_text=normalized_text, raw_text=transcript)
        if any(keyword in normalized_text for keyword in ["emergency", "hospital", "medical", "accident"]):
            return CallDecision(status="Emergency", reason="Teacher reported an emergency", confidence=0.96, normalized_text=normalized_text, raw_text=transcript)
        if any(keyword in normalized_text for keyword in ["cannot", "can't", "unable", "not available", "won't be able", "no, i cannot", "no i cannot"]):
            return CallDecision(status="Unavailable", reason="Teacher declined the lecture", confidence=0.95, normalized_text=normalized_text, raw_text=transcript)

        late_match = re.search(r"(late|delay|after|join after)\s*(?:for\s*)?(\d+)?\s*(minute|minutes|mins|hr|hour|hours)?", normalized_text)
        if late_match or any(keyword in normalized_text for keyword in ["will be late", "join after", "come after"]):
            delay_minutes = self._extract_delay_minutes(normalized_text, late_match)
            return CallDecision(
                status="Late",
                delay_minutes=delay_minutes,
                reason=f"Teacher plans to join after {delay_minutes} minutes" if delay_minutes else "Teacher will be late",
                confidence=0.93,
                normalized_text=normalized_text,
                raw_text=transcript,
            )

        if any(keyword in normalized_text for keyword in ["yes", "available", "will attend", "confirm", "sure", "okay"]):
            return CallDecision(status="Available", reason="Teacher confirmed availability", confidence=0.98, normalized_text=normalized_text, raw_text=transcript)

        if any(keyword in normalized_text for keyword in ["reschedule", "another faculty", "assign another", "please assign"]):
            return CallDecision(status="Unavailable", reason="Teacher requested alternate faculty", confidence=0.94, normalized_text=normalized_text, raw_text=transcript)

        return CallDecision(status="No Response", reason="Could not classify the response confidently", confidence=0.5, normalized_text=normalized_text, raw_text=transcript)

    def _extract_delay_minutes(self, normalized_text: str, match: re.Match[str] | None) -> int:
        if match and match.group(2):
            value = int(match.group(2))
            unit = (match.group(3) or "minutes").lower()
            if unit.startswith("hour") or unit == "hr":
                return value * 60
            return value

        number_match = re.search(r"(\d+)\s*(minute|minutes|mins|hr|hour|hours)", normalized_text)
        if number_match:
            value = int(number_match.group(1))
            unit = number_match.group(2)
            if unit.startswith("hour") or unit == "hr":
                return value * 60
            return value
        return 30

    def _fallback_prompt(self) -> str:
        return (
            "You are a college lecture confirmation assistant. Classify the teacher's response into one of the "
            "following statuses: Available, Unavailable, Late, Leave, Emergency, No Response, Voicemail, Busy, Cancelled. "
            "Return a JSON object with keys status, delay_minutes, reason, confidence, normalized_text."
        )
