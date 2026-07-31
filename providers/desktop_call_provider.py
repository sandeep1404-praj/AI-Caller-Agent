"""Desktop call simulator using microphone and speakers."""

import asyncio
import logging
import time
from datetime import datetime

from ai.conversation_manager import ConversationManager
from ai.gemini_client import GeminiClient
from config import get_settings
from models import CallState
from providers.call_provider import (
    CallContext,
    CallProvider,
    CallResult,
    CallResultStatus,
    ConversationTurn,
)
from speech.speech_to_text import SpeechToText
from speech.text_to_speech import TextToSpeech

logger = logging.getLogger(__name__)


class DesktopCallProvider(CallProvider):
    """
    Desktop call simulator that behaves like a real phone call.

    Uses system microphone/speakers with STT/TTS and Gemini AI.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.stt = SpeechToText()
        self.tts = TextToSpeech()
        self._active = False
        self._conversation: ConversationManager | None = None

    def is_available(self) -> bool:
        return self.stt.is_microphone_available()

    async def initiate_call(self, context: CallContext) -> CallResult:
        """Conduct a full simulated call conversation."""
        start_time = datetime.now()
        self._active = True
        turns: list[ConversationTurn] = []
        gemini_responses: list[str] = []

        print(f"\n{'='*50}")
        print(f"  Calling {context.teacher_name}...")
        print(f"  Subject: {context.subject}")
        print(f"  Time: {context.lecture_time} | Room: {context.room}")
        print(f"{'='*50}\n")

        try:
            gemini = GeminiClient()
            self._conversation = ConversationManager(gemini)

            call_context = {
                "teacher_name": context.teacher_name,
                "department": context.department,
                "subject": context.subject,
                "lecture_date": context.lecture_date,
                "lecture_time": context.lecture_time,
                "room": context.room,
            }

            # Opening greeting
            self._conversation.set_state(CallState.CALLING)
            opening = self._conversation.generate_opening(call_context)
            gemini_responses.append(str(opening))
            reply = opening.get("reply", "")
            turns.append(ConversationTurn(role="assistant", content=reply))
            await self._speak_async(reply)

            if opening.get("conversation_finished"):
                return self._build_result(
                    opening, turns, gemini_responses, start_time, CallResultStatus.SUCCESS
                )

            # Conversation loop
            elapsed = 0
            max_duration = self.settings.call_timeout_seconds
            no_response_count = 0
            max_no_response = 2

            while self._active and not self._conversation.is_finished:
                if elapsed >= max_duration:
                    logger.warning("Call timeout reached")
                    return self._build_result(
                        self._conversation.final_result or {},
                        turns,
                        gemini_responses,
                        start_time,
                        CallResultStatus.TIMEOUT,
                        error="Call timed out after 2 minutes",
                    )

                self._conversation.set_state(CallState.LISTENING)
                teacher_text = await self._listen_async()

                if teacher_text is None:
                    no_response_count += 1
                    if no_response_count >= max_no_response:
                        return self._build_result(
                            {},
                            turns,
                            gemini_responses,
                            start_time,
                            CallResultStatus.NO_RESPONSE,
                            error="No response from teacher",
                        )
                    prompt = "I didn't hear you. Could you please respond?"
                    turns.append(ConversationTurn(role="assistant", content=prompt))
                    await self._speak_async(prompt)
                    elapsed = (datetime.now() - start_time).total_seconds()
                    continue

                no_response_count = 0
                turns.append(ConversationTurn(role="teacher", content=teacher_text))

                try:
                    result = self._conversation.process_teacher_input(teacher_text)
                    gemini_responses.extend(self._conversation.gemini_responses[-1:])
                    reply = result.get("reply", "")
                    turns.append(ConversationTurn(role="assistant", content=reply))
                    await self._speak_async(reply)
                except Exception as exc:
                    logger.error("Conversation error: %s", exc)
                    return self._build_result(
                        {},
                        turns,
                        gemini_responses,
                        start_time,
                        CallResultStatus.FAILED,
                        error=str(exc),
                    )

                elapsed = (datetime.now() - start_time).total_seconds()

            final = self._conversation.final_result if self._conversation else {}
            return self._build_result(
                final, turns, gemini_responses, start_time, CallResultStatus.SUCCESS
            )

        except Exception as exc:
            logger.exception("Call failed: %s", exc)
            return self._build_result(
                {},
                turns,
                gemini_responses,
                start_time,
                CallResultStatus.FAILED,
                error=str(exc),
            )
        finally:
            self._active = False
            self._conversation = None

    async def hang_up(self) -> None:
        """End the current call."""
        self._active = False
        self.tts.stop()
        logger.info("Call hung up")

    async def _speak_async(self, text: str) -> None:
        """Speak text without blocking the event loop."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.tts.speak, text)

    async def _listen_async(self) -> str | None:
        """Listen from microphone without blocking the event loop."""
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self.stt.listen)
        except OSError as exc:
            logger.error("Microphone error: %s", exc)
            raise
        except Exception as exc:
            logger.error("STT error: %s", exc)
            return None

    def _build_result(
        self,
        gemini_result: dict,
        turns: list[ConversationTurn],
        gemini_responses: list[str],
        start_time: datetime,
        status: CallResultStatus,
        error: str | None = None,
    ) -> CallResult:
        duration = int((datetime.now() - start_time).total_seconds())
        transcript = "\n".join(
            f"{'Assistant' if t.role == 'assistant' else 'Teacher'}: {t.content}"
            for t in turns
        )

        return CallResult(
            status=status,
            confirmation_status=gemini_result.get("status", "Pending"),
            delay_minutes=int(gemini_result.get("delay_minutes", 0)),
            reason=gemini_result.get("reason", ""),
            transcript=transcript,
            conversation_finished=gemini_result.get("conversation_finished", False)
            or status == CallResultStatus.SUCCESS,
            turns=turns,
            gemini_responses=gemini_responses,
            error_message=error,
            duration_seconds=duration,
        )
