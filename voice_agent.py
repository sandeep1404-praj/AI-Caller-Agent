"""Conversation generation and response interpretation helpers."""
from __future__ import annotations

from pathlib import Path

from llm import ResponseInterpreter
from models import CallDecision, LectureRecord
from utils import read_text_file


class VoiceAgent:
    """Build prompts, greetings, and response decisions for the call flow."""

    def __init__(self, interpreter: ResponseInterpreter, prompts_dir: Path) -> None:
        self.interpreter = interpreter
        self.prompts_dir = prompts_dir

    def greeting_for(self, lecture: LectureRecord) -> str:
        """Create the opening script for the outbound call."""

        return (
            f"Good evening Professor {lecture.teacher_name}. This is the College Lecture Confirmation Assistant. "
            f"You are scheduled to conduct {lecture.subject} tomorrow at {lecture.lecture_time.strftime('%I:%M %p')}. "
            "Will you be available to take the lecture?"
        )

    def reminder_for_late_response(self, lecture: LectureRecord) -> str:
        """Create a follow-up question after a partial answer."""

        return (
            f"Thank you Professor {lecture.teacher_name}. Please confirm whether you can attend the {lecture.subject} lecture tomorrow."
        )

    def system_prompt(self) -> str:
        """Load the voice agent prompt template from disk."""

        prompt_file = self.prompts_dir / "teacher_prompt.txt"
        if prompt_file.exists():
            return read_text_file(prompt_file)
        return self._fallback_prompt()

    def interpret_transcript(self, transcript: str, lecture: LectureRecord) -> CallDecision:
        """Parse a transcript into a structured call decision."""

        return self.interpreter.interpret(transcript, lecture)

    def _fallback_prompt(self) -> str:
        return (
            "You are a polite and professional college lecture confirmation assistant. "
            "Classify the teacher response into a structured JSON object with status, delay_minutes, reason, confidence, "
            "and normalized_text."
        )
