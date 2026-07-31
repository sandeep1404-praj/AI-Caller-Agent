"""Conversation state manager for call sessions."""

import logging
from datetime import datetime
from typing import Any

from ai.gemini_client import GeminiClient
from models import CallState

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation flow, state transitions, and Gemini interactions."""

    def __init__(self, gemini_client: GeminiClient | None = None) -> None:
        self.gemini = gemini_client or GeminiClient()
        self.history: list[dict[str, str]] = []
        self.gemini_responses: list[str] = []
        self.current_state: CallState = CallState.PENDING
        self.final_result: dict[str, Any] = {}

    def set_state(self, state: CallState) -> None:
        logger.debug("State transition: %s -> %s", self.current_state.value, state.value)
        self.current_state = state

    def generate_opening(self, context: dict[str, str]) -> dict[str, Any]:
        """Generate and record the opening message."""
        self.set_state(CallState.THINKING)
        result = self.gemini.generate_opening(context)
        self.gemini_responses.append(str(result))
        reply = result.get("reply", "")
        self._add_turn("assistant", reply)
        self.set_state(CallState.SPEAKING)
        return result

    def process_teacher_input(self, teacher_text: str) -> dict[str, Any]:
        """Process teacher speech and return AI response."""
        if not teacher_text or not teacher_text.strip():
            return self._no_response_result()

        self._add_turn("teacher", teacher_text.strip())
        self.set_state(CallState.THINKING)

        try:
            result = self.gemini.generate_response(self.history, teacher_text.strip())
            self.gemini_responses.append(str(result))
            reply = result.get("reply", "I did not catch that. Could you please repeat?")
            self._add_turn("assistant", reply)

            if result.get("conversation_finished"):
                self.set_state(CallState.FINISHED)
                self.final_result = result
            else:
                self.set_state(CallState.WAITING)

            return result
        except Exception as exc:
            logger.error("Gemini processing error: %s", exc)
            self.set_state(CallState.FAILED)
            raise

    def get_transcript(self) -> str:
        """Return full conversation transcript."""
        lines = []
        for turn in self.history:
            role = "Assistant" if turn["role"] == "assistant" else "Teacher"
            lines.append(f"{role}: {turn['content']}")
        return "\n".join(lines)

    def get_summary(self) -> str:
        return self.gemini.generate_summary(self.get_transcript())

    def _add_turn(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})

    def _no_response_result(self) -> dict[str, Any]:
        return {
            "reply": "I didn't hear a response. Are you still there?",
            "status": "Pending",
            "delay_minutes": 0,
            "reason": "",
            "conversation_finished": False,
            "needs_delay_clarification": False,
        }

    @property
    def is_finished(self) -> bool:
        return self.current_state == CallState.FINISHED

    @property
    def turn_count(self) -> int:
        return len(self.history)
