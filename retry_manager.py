"""Retry scheduling and retry queue processing."""
from __future__ import annotations

from datetime import datetime, timedelta

from config import AppConfig
from database import SQLiteRepository
from models import CallStatus, LectureRecord, NotificationMessage
from notification import NotificationService
from utils import now_local


class RetryManager:
    """Manage retry-state transitions and retry queue processing."""

    def __init__(self, config: AppConfig, repository: SQLiteRepository, notifier: NotificationService, logger) -> None:
        self.config = config
        self.repository = repository
        self.notifier = notifier
        self.logger = logger

    def schedule_retry(self, lecture: LectureRecord, reason: str, attempt_number: int, current_time: datetime | None = None) -> None:
        """Mark the lecture as retry pending and enqueue the next attempt."""

        current_time = current_time or now_local(self.config.timezone)
        lecture.retry_count = attempt_number
        lecture.call_status = CallStatus.RETRY_PENDING.value
        lecture.reason = reason
        lecture.next_call_time = current_time + timedelta(minutes=self.config.retry_interval_minutes)
        self.repository.record_retry_request(lecture, attempt_number, lecture.next_call_time, reason)
        self.logger.info(
            "Retry scheduled lecture_id=%s attempt=%s next_call_time=%s reason=%s",
            lecture.lecture_id,
            attempt_number,
            lecture.next_call_time.isoformat(),
            reason,
        )

    def mark_failed_permanently(self, lecture: LectureRecord, reason: str) -> None:
        """Stop retrying and notify the HOD/coordinator."""

        lecture.call_status = CallStatus.NO_RESPONSE.value
        lecture.reason = reason
        self.repository.mark_no_response(lecture, reason)
        self.logger.warning("Retries exhausted lecture_id=%s reason=%s", lecture.lecture_id, reason)
        self.notifier.notify(
            NotificationMessage(
                teacher_name=lecture.teacher_name,
                subject=lecture.subject,
                lecture_time=lecture.lecture_time.strftime("%I:%M %p"),
                reason=reason,
                retry_count=lecture.retry_count,
                audience="HOD and Department Coordinator",
                department=lecture.department,
                teacher_id=lecture.teacher_id,
                phone_number=lecture.phone_number,
            )
        )

    def process_due_retries(self, callback, current_time: datetime | None = None) -> int:
        """Dispatch all retry rows that are ready to be called again."""

        current_time = current_time or now_local(self.config.timezone)
        due_requests = self.repository.fetch_due_retry_requests(current_time)
        processed = 0
        for request in due_requests:
            callback(request)
            self.repository.mark_retry_complete(request.lecture_id)
            processed += 1
        return processed
