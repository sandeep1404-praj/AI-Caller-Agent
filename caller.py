"""Outbound call orchestration for Class Call Agent."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from urllib.parse import urlencode
from xml.sax.saxutils import escape

from config import AppConfig
from database import SQLiteRepository
from excel_reader import ExcelReader
from excel_writer import ExcelWriter
from llm import ResponseInterpreter
from models import CallAttempt, CallDecision, CallStatus, LectureRecord, NotificationMessage, RetryRequest
from notification import NotificationService
from retry_manager import RetryManager
from speech import build_speech_to_text_provider, build_text_to_speech_provider
from utils import now_local, safe_json_dumps
from voice_agent import VoiceAgent


FINAL_STATUSES = {
    CallStatus.CONFIRMED.value,
    CallStatus.AVAILABLE.value,
    CallStatus.LATE.value,
    CallStatus.LEAVE.value,
    CallStatus.EMERGENCY.value,
    CallStatus.UNAVAILABLE.value,
    CallStatus.CANCELLED.value,
    CallStatus.NO_RESPONSE.value,
}

RETRYABLE_STATUSES = {
    CallStatus.NO_RESPONSE.value,
    CallStatus.VOICEMAIL.value,
    CallStatus.BUSY.value,
    CallStatus.FAILED.value,
}

SUCCESS_STATUSES = {
    CallStatus.AVAILABLE.value,
    CallStatus.LATE.value,
}


class TwilioVoiceClient:
    """Thin wrapper over the Twilio REST client."""

    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger

    def is_configured(self) -> bool:
        return bool(self.config.twilio_account_sid and self.config.twilio_auth_token and self.config.twilio_from_number)

    def place_call(self, lecture: LectureRecord, greeting_text: str) -> str:
        """Place an outbound call or return a deterministic dry-run SID."""

        if self.config.dry_run or not self.is_configured():
            call_sid = f"SIM-{lecture.lecture_id or lecture.teacher_id}-{int(datetime.now().timestamp())}"
            self.logger.info("Dry-run call SID generated: %s", call_sid)
            return call_sid

        from twilio.rest import Client

        client = Client(self.config.twilio_account_sid, self.config.twilio_auth_token)
        attempt_number = max(lecture.call_attempts, lecture.retry_count) + 1
        twiml = self._build_twiml(lecture, greeting_text, attempt_number)
        call = client.calls.create(
            to=lecture.phone_number,
            from_=self.config.twilio_from_number,
            twiml=twiml,
            status_callback=self.config.twilio_status_callback_url or None,
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
        self.logger.info("Twilio call initiated sid=%s teacher=%s", call.sid, lecture.teacher_name)
        return call.sid

    def _build_twiml(self, lecture: LectureRecord, greeting_text: str, attempt_number: int) -> str:
        """Generate a minimal TwiML document for the first greeting."""

        action_url = self.config.voice_webhook_url or self.config.twilio_status_callback_url or ""
        escaped_text = escape(greeting_text)
        if action_url:
            query_string = urlencode({"lecture_id": lecture.lecture_id, "attempt_number": attempt_number})
            separator = "&" if "?" in action_url else "?"
            action_with_params = f"{action_url}{separator}{query_string}"
            return (
                f'<Response><Gather input="speech" action="{escape(action_with_params)}" method="POST" '
                f'speechTimeout="auto" timeout="6"><Say voice="alice">{escaped_text}</Say></Gather>'
                f'<Say voice="alice">We did not receive a response. Goodbye.</Say></Response>'
            )
        return f'<Response><Say voice="alice">{escaped_text}</Say></Response>'


class ClassCallAgentService:
    """Coordinate workbook sync, outbound calls, retries, and notifications."""

    def __init__(
        self,
        config: AppConfig,
        repository: SQLiteRepository,
        excel_reader: ExcelReader,
        excel_writer: ExcelWriter,
        voice_agent: VoiceAgent,
        retry_manager: RetryManager,
        notification_service: NotificationService,
        telephony_client: TwilioVoiceClient,
        logger,
    ) -> None:
        self.config = config
        self.repository = repository
        self.excel_reader = excel_reader
        self.excel_writer = excel_writer
        self.voice_agent = voice_agent
        self.retry_manager = retry_manager
        self.notification_service = notification_service
        self.telephony_client = telephony_client
        self.logger = logger
        self.speech_to_text = build_speech_to_text_provider(config)
        self.text_to_speech = build_text_to_speech_provider(config)

    def sync_workbook(self) -> int:
        """Load lecture rows from Excel and persist them to SQLite."""

        records = self.excel_reader.read_lectures()
        for record in records:
            self.repository.upsert_lecture(record)
        self.logger.info("Workbook synchronized rows=%s", len(records))
        return len(records)

    def run_daily_campaign(self, current_time: datetime | None = None) -> int:
        """Call all tomorrow lectures that still need confirmation."""

        current_time = current_time or now_local(self.config.timezone)
        self.sync_workbook()
        tomorrow_lectures = self.repository.fetch_tomorrow_lectures(current_time.date())
        scheduled = 0
        for lecture in sorted(tomorrow_lectures, key=lambda item: (item.lecture_time, item.teacher_name)):
            if lecture.call_status not in {CallStatus.PENDING.value, CallStatus.RETRY_PENDING.value}:
                self.logger.info("Skipping lecture already handled lecture_id=%s status=%s", lecture.lecture_id, lecture.call_status)
                continue
            attempt_number = max(lecture.call_attempts, lecture.retry_count) + 1
            self.execute_call(lecture, attempt_number, campaign="daily", current_time=current_time)
            scheduled += 1
        return scheduled

    def run_retry_campaign(self, current_time: datetime | None = None) -> int:
        """Process retries that are due at or before the current time."""

        current_time = current_time or now_local(self.config.timezone)
        return self.retry_manager.process_due_retries(self.handle_retry_request, current_time=current_time)

    def process_voice_response(
        self,
        lecture_id: str,
        transcript: str,
        call_sid: str = "",
        attempt_number: int | None = None,
        current_time: datetime | None = None,
    ) -> CallDecision:
        """Process an inbound Twilio webhook transcript for a specific lecture."""

        lecture = self.repository.fetch_lecture_by_id(lecture_id)
        if lecture is None:
            self.logger.warning("Voice webhook received unknown lecture_id=%s", lecture_id)
            return CallDecision(status=CallStatus.NO_RESPONSE.value, reason="Unknown lecture", confidence=0.0, raw_text=transcript)

        attempt_number = attempt_number or max(lecture.call_attempts, lecture.retry_count) + 1
        started_at = current_time or now_local(self.config.timezone)
        decision = self.voice_agent.interpret_transcript(transcript, lecture)
        ended_at = now_local(self.config.timezone)
        duration_seconds = max(0, int((ended_at - started_at).total_seconds()))
        return self._finalize_voice_attempt(
            lecture=lecture,
            decision=decision,
            call_sid=call_sid,
            transcript=transcript,
            attempt_number=attempt_number,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
        )

    def handle_retry_request(self, request: RetryRequest) -> None:
        """Convert a retry queue row back into a lecture record and execute the retry."""

        lecture = LectureRecord(
            teacher_id=request.teacher_id,
            teacher_name=request.teacher_name,
            phone_number=request.phone_number,
            department=request.department,
            subject=request.subject,
            lecture_date=request.lecture_date,
            lecture_time=request.lecture_time,
            room=request.room,
            call_status=CallStatus.RETRY_PENDING.value,
            retry_count=request.retry_count,
            next_call_time=request.next_call_time,
            call_attempts=request.attempt_number - 1,
            lecture_id=request.lecture_id,
        )
        self.execute_call(lecture, request.attempt_number, campaign="retry", current_time=request.next_call_time)

    def execute_call(self, lecture: LectureRecord, attempt_number: int, campaign: str, current_time: datetime | None = None) -> CallDecision:
        """Place a call, classify the response, and persist the result."""

        started_at = current_time or now_local(self.config.timezone)
        greeting = self.voice_agent.greeting_for(lecture)
        self.logger.info(
            "Call started teacher=%s subject=%s attempt=%s campaign=%s",
            lecture.teacher_name,
            lecture.subject,
            attempt_number,
            campaign,
        )

        try:
            call_sid = self.telephony_client.place_call(lecture, greeting)
            transcript = self._obtain_transcript(lecture)
            decision = self.voice_agent.interpret_transcript(transcript, lecture)
            ended_at = now_local(self.config.timezone)
            duration_seconds = max(0, int((ended_at - started_at).total_seconds()))
            return self._apply_decision(
                lecture=lecture,
                decision=decision,
                call_sid=call_sid,
                transcript=transcript,
                attempt_number=attempt_number,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
            )
        except Exception as exc:
            ended_at = now_local(self.config.timezone)
            duration_seconds = max(0, int((ended_at - started_at).total_seconds()))
            self.logger.exception("Call failed teacher=%s attempt=%s", lecture.teacher_name, attempt_number)
            decision = CallDecision(status=CallStatus.FAILED.value, reason=str(exc), confidence=1.0, raw_text="")
            return self._apply_failure(
                lecture=lecture,
                decision=decision,
                call_sid="",
                transcript="",
                attempt_number=attempt_number,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
            )

    def _obtain_transcript(self, lecture: LectureRecord) -> str:
        """Return the transcript for a call attempt.

        In dry-run mode or when the live speech pipeline is not wired, a simulated
        transcript can be supplied via SIMULATED_TEACHER_RESPONSE.
        """

        if self.config.dry_run:
            return self.config.simulated_teacher_response.strip()
        return self.config.simulated_teacher_response.strip()

    def _apply_decision(
        self,
        lecture: LectureRecord,
        decision: CallDecision,
        call_sid: str,
        transcript: str,
        attempt_number: int,
        started_at: datetime,
        ended_at: datetime,
        duration_seconds: int,
    ) -> CallDecision:
        lecture.call_attempts = attempt_number
        lecture.last_call_time = ended_at
        lecture.conversation_transcript = transcript
        lecture.reason = decision.reason
        lecture.delay_minutes = decision.delay_minutes
        lecture.teacher_response = decision.status
        lecture.call_duration_seconds = duration_seconds

        if decision.status in SUCCESS_STATUSES:
            lecture.call_status = decision.status
            lecture.next_call_time = None
            self.repository.update_call_state(
                lecture,
                attempt_number,
                decision,
                call_sid,
                transcript,
                started_at,
                ended_at,
                duration_seconds,
                None,
            )
            self.repository.mark_confirmed(lecture, decision)
        elif decision.status in {CallStatus.UNAVAILABLE.value, CallStatus.LEAVE.value, CallStatus.EMERGENCY.value, CallStatus.CANCELLED.value}:
            lecture.call_status = decision.status
            lecture.next_call_time = None
            self.repository.update_call_state(
                lecture,
                attempt_number,
                decision,
                call_sid,
                transcript,
                started_at,
                ended_at,
                duration_seconds,
                None,
            )
            self._notify_unavailable(lecture, decision)
        else:
            return self._handle_retryable_outcome(
                lecture=lecture,
                decision=decision,
                call_sid=call_sid,
                transcript=transcript,
                attempt_number=attempt_number,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
            )

        attempt = self._build_attempt(lecture, decision, call_sid, transcript, attempt_number, started_at, ended_at, duration_seconds)
        self.repository.insert_call_log(attempt)
        self.excel_writer.update_lecture_row(lecture)
        self.excel_writer.append_call_log(self._build_excel_log_row(lecture, decision, attempt, started_at, ended_at))
        self.logger.info(
            "Call ended teacher=%s status=%s duration=%ss call_sid=%s",
            lecture.teacher_name,
            decision.status,
            duration_seconds,
            call_sid,
        )
        return decision

    def _finalize_voice_attempt(
        self,
        lecture: LectureRecord,
        decision: CallDecision,
        call_sid: str,
        transcript: str,
        attempt_number: int,
        started_at: datetime,
        ended_at: datetime,
        duration_seconds: int,
    ) -> CallDecision:
        """Shared finalization path for live webhook responses."""

        lecture.call_attempts = attempt_number
        lecture.last_call_time = ended_at
        lecture.conversation_transcript = transcript
        lecture.reason = decision.reason
        lecture.delay_minutes = decision.delay_minutes
        lecture.teacher_response = decision.status
        lecture.call_duration_seconds = duration_seconds

        if decision.status in SUCCESS_STATUSES:
            lecture.call_status = decision.status
            lecture.next_call_time = None
            self.repository.update_call_state(
                lecture,
                attempt_number,
                decision,
                call_sid,
                transcript,
                started_at,
                ended_at,
                duration_seconds,
                None,
            )
            self.repository.mark_confirmed(lecture, decision)
        elif decision.status in {CallStatus.UNAVAILABLE.value, CallStatus.LEAVE.value, CallStatus.EMERGENCY.value, CallStatus.CANCELLED.value}:
            lecture.call_status = decision.status
            lecture.next_call_time = None
            self.repository.update_call_state(
                lecture,
                attempt_number,
                decision,
                call_sid,
                transcript,
                started_at,
                ended_at,
                duration_seconds,
                None,
            )
            self._notify_unavailable(lecture, decision)
        else:
            if attempt_number >= self.config.max_retry_attempts:
                lecture.call_status = CallStatus.NO_RESPONSE.value
                lecture.retry_count = attempt_number
                lecture.next_call_time = None
                self.repository.update_call_state(
                    lecture,
                    attempt_number,
                    CallDecision(status=CallStatus.NO_RESPONSE.value, reason=decision.reason, confidence=decision.confidence),
                    call_sid,
                    transcript,
                    started_at,
                    ended_at,
                    duration_seconds,
                    None,
                )
                self.retry_manager.mark_failed_permanently(lecture, decision.reason or "Maximum retry attempts reached")
                decision = CallDecision(status=CallStatus.NO_RESPONSE.value, reason=decision.reason, confidence=decision.confidence, raw_text=transcript)
            else:
                self.retry_manager.schedule_retry(lecture, decision.reason or "No answer received", attempt_number, current_time=ended_at)
                decision = CallDecision(
                    status=CallStatus.RETRY_PENDING.value,
                    reason=decision.reason or "Retry scheduled",
                    confidence=decision.confidence,
                    normalized_text=decision.normalized_text,
                    raw_text=transcript,
                    metadata=decision.metadata,
                )
                self.repository.update_call_state(
                    lecture,
                    attempt_number,
                    decision,
                    call_sid,
                    transcript,
                    started_at,
                    ended_at,
                    duration_seconds,
                    lecture.next_call_time,
                )

        attempt = self._build_attempt(lecture, decision, call_sid, transcript, attempt_number, started_at, ended_at, duration_seconds)
        self.repository.insert_call_log(attempt)
        self.excel_writer.update_lecture_row(lecture)
        self.excel_writer.append_call_log(self._build_excel_log_row(lecture, decision, attempt, started_at, ended_at))
        self.logger.info(
            "Voice response processed teacher=%s status=%s duration=%ss call_sid=%s",
            lecture.teacher_name,
            decision.status,
            duration_seconds,
            call_sid,
        )
        return decision

    def _apply_failure(
        self,
        lecture: LectureRecord,
        decision: CallDecision,
        call_sid: str,
        transcript: str,
        attempt_number: int,
        started_at: datetime,
        ended_at: datetime,
        duration_seconds: int,
    ) -> CallDecision:
        if attempt_number >= self.config.max_retry_attempts:
            lecture.call_status = CallStatus.NO_RESPONSE.value
            lecture.retry_count = attempt_number
            lecture.next_call_time = None
            self.repository.update_call_state(
                lecture,
                attempt_number,
                CallDecision(status=CallStatus.NO_RESPONSE.value, reason=decision.reason, confidence=decision.confidence),
                call_sid,
                transcript,
                started_at,
                ended_at,
                duration_seconds,
                None,
            )
            self.retry_manager.mark_failed_permanently(lecture, decision.reason or "Maximum retry attempts reached")
            final_decision = CallDecision(status=CallStatus.NO_RESPONSE.value, reason=decision.reason, confidence=decision.confidence, raw_text=transcript)
        else:
            final_decision = self._schedule_retry(
                lecture=lecture,
                decision=decision,
                call_sid=call_sid,
                transcript=transcript,
                attempt_number=attempt_number,
                started_at=started_at,
                ended_at=ended_at,
                duration_seconds=duration_seconds,
            )

        attempt = self._build_attempt(lecture, final_decision, call_sid, transcript, attempt_number, started_at, ended_at, duration_seconds)
        self.repository.insert_call_log(attempt)
        self.excel_writer.update_lecture_row(lecture)
        self.excel_writer.append_call_log(self._build_excel_log_row(lecture, final_decision, attempt, started_at, ended_at))
        self.logger.info(
            "Call ended teacher=%s status=%s duration=%ss call_sid=%s",
            lecture.teacher_name,
            final_decision.status,
            duration_seconds,
            call_sid,
        )
        return final_decision

    def _schedule_retry(
        self,
        lecture: LectureRecord,
        decision: CallDecision,
        call_sid: str,
        transcript: str,
        attempt_number: int,
        started_at: datetime,
        ended_at: datetime,
        duration_seconds: int,
    ) -> CallDecision:
        self.retry_manager.schedule_retry(lecture, decision.reason or "No answer received", attempt_number, current_time=ended_at)
        retry_decision = CallDecision(
            status=CallStatus.RETRY_PENDING.value,
            reason=decision.reason or "Retry scheduled",
            confidence=decision.confidence,
            normalized_text=decision.normalized_text,
            raw_text=transcript,
            metadata=decision.metadata,
        )
        self.repository.update_call_state(
            lecture,
            attempt_number,
            retry_decision,
            call_sid,
            transcript,
            started_at,
            ended_at,
            duration_seconds,
            lecture.next_call_time,
        )
        return retry_decision

    def _handle_retryable_outcome(
        self,
        lecture: LectureRecord,
        decision: CallDecision,
        call_sid: str,
        transcript: str,
        attempt_number: int,
        started_at: datetime,
        ended_at: datetime,
        duration_seconds: int,
    ) -> CallDecision:
        return self._schedule_retry(
            lecture=lecture,
            decision=decision,
            call_sid=call_sid,
            transcript=transcript,
            attempt_number=attempt_number,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
        )

    def _notify_unavailable(self, lecture: LectureRecord, decision: CallDecision) -> None:
        self.notification_service.notify(
            NotificationMessage(
                teacher_name=lecture.teacher_name,
                subject=lecture.subject,
                lecture_time=lecture.lecture_time.strftime("%I:%M %p"),
                reason=decision.reason,
                retry_count=lecture.retry_count,
                audience="HOD and Department Coordinator",
                department=lecture.department,
                teacher_id=lecture.teacher_id,
                phone_number=lecture.phone_number,
            )
        )

    def _build_attempt(
        self,
        lecture: LectureRecord,
        decision: CallDecision,
        call_sid: str,
        transcript: str,
        attempt_number: int,
        started_at: datetime,
        ended_at: datetime,
        duration_seconds: int,
    ) -> CallAttempt:
        return CallAttempt(
            lecture_id=lecture.lecture_id,
            attempt_number=attempt_number,
            call_sid=call_sid,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            transcript=transcript,
            decision_json=asdict(decision),
            status=lecture.call_status,
            reason=decision.reason,
            delay_minutes=decision.delay_minutes,
            retry_count=lecture.retry_count,
            next_call_time=lecture.next_call_time,
        )

    def _build_excel_log_row(
        self,
        lecture: LectureRecord,
        decision: CallDecision,
        attempt: CallAttempt,
        started_at: datetime,
        ended_at: datetime,
    ) -> dict[str, object]:
        return {
            "Timestamp": ended_at.isoformat(),
            "Teacher ID": lecture.teacher_id,
            "Teacher Name": lecture.teacher_name,
            "Phone Number": lecture.phone_number,
            "Department": lecture.department,
            "Subject": lecture.subject,
            "Lecture Date": lecture.lecture_date.isoformat(),
            "Lecture Time": lecture.lecture_time.strftime("%H:%M:%S"),
            "Room": lecture.room,
            "Attempt Number": attempt.attempt_number,
            "Call SID": attempt.call_sid,
            "Call Status": lecture.call_status,
            "Retry Count": lecture.retry_count,
            "Next Call Time": lecture.next_call_time.isoformat() if lecture.next_call_time else "",
            "Teacher Response": lecture.teacher_response,
            "Delay Minutes": lecture.delay_minutes,
            "Call Duration": attempt.duration_seconds,
            "Conversation Transcript": lecture.conversation_transcript,
            "Reason": lecture.reason,
            "Decision JSON": safe_json_dumps(attempt.decision_json),
        }
