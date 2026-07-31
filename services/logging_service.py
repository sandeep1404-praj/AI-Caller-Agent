"""Logging service for call sessions."""

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from config import get_settings
from models import CallLog, CallState, ConversationHistory

logger = logging.getLogger(__name__)


class LoggingService:
    """Persist call logs to database and filesystem."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def create_call_log(self, teacher_id: int, lecture_id: int | None = None) -> CallLog:
        call_log = CallLog(
            teacher_id=teacher_id,
            lecture_id=lecture_id,
            call_start_time=datetime.now(),
            current_state=CallState.PENDING.value,
        )
        self.db.add(call_log)
        self.db.flush()
        return call_log

    def update_call_log(
        self,
        call_log: CallLog,
        *,
        end_time: datetime | None = None,
        duration_seconds: int | None = None,
        current_state: str | None = None,
        transcript: str | None = None,
        gemini_responses: list[str] | None = None,
        errors: str | None = None,
        conversation_summary: str | None = None,
        final_status: str | None = None,
        retry_history: str | None = None,
    ) -> CallLog:
        if end_time:
            call_log.call_end_time = end_time
        if duration_seconds is not None:
            call_log.duration_seconds = duration_seconds
        if current_state:
            call_log.current_state = current_state
        if transcript is not None:
            call_log.transcript = transcript
        if gemini_responses is not None:
            call_log.gemini_responses = json.dumps(gemini_responses)
        if errors is not None:
            call_log.errors = errors
        if conversation_summary is not None:
            call_log.conversation_summary = conversation_summary
        if final_status is not None:
            call_log.final_status = final_status
        if retry_history is not None:
            call_log.retry_history = retry_history
        self.db.flush()
        return call_log

    def add_conversation_turn(self, call_log_id: int, role: str, content: str) -> None:
        entry = ConversationHistory(
            call_log_id=call_log_id,
            role=role,
            content=content,
        )
        self.db.add(entry)

    def get_all_logs(self, limit: int = 100) -> list[CallLog]:
        return (
            self.db.query(CallLog)
            .order_by(CallLog.call_start_time.desc())
            .limit(limit)
            .all()
        )

    def write_file_log(self, call_log: CallLog, extra: dict | None = None) -> Path:
        """Write a JSON log file to logs/ directory."""
        timestamp = call_log.call_start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"call_{call_log.id}_{timestamp}.json"
        filepath = self.settings.logs_dir / filename

        data = {
            "call_log_id": call_log.id,
            "teacher_id": call_log.teacher_id,
            "lecture_id": call_log.lecture_id,
            "call_start_time": call_log.call_start_time.isoformat(),
            "call_end_time": call_log.call_end_time.isoformat() if call_log.call_end_time else None,
            "duration_seconds": call_log.duration_seconds,
            "current_state": call_log.current_state,
            "transcript": call_log.transcript,
            "gemini_responses": call_log.gemini_responses,
            "errors": call_log.errors,
            "conversation_summary": call_log.conversation_summary,
            "final_status": call_log.final_status,
            "retry_history": call_log.retry_history,
        }
        if extra:
            data.update(extra)

        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Log written to %s", filepath)
        return filepath
