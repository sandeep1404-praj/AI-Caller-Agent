"""Retry queue service."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from config import get_settings
from models import ConfirmationStatus, Lecture, QueueStatus, RetryQueue

logger = logging.getLogger(__name__)


class RetryService:
    """Manage automatic retry logic for failed calls."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def schedule_retry(self, lecture: Lecture, reason: str) -> RetryQueue | None:
        """Schedule a retry if under max retry limit."""
        lecture.retry_count += 1

        if lecture.retry_count > self.settings.max_retries:
            lecture.confirmation_status = ConfirmationStatus.NO_RESPONSE.value
            lecture.reason = f"Max retries exceeded. Last reason: {reason}"
            logger.warning(
                "Max retries exceeded for lecture %s (teacher retry #%d)",
                lecture.id,
                lecture.retry_count,
            )
            return None

        next_retry = datetime.now() + timedelta(minutes=self.settings.retry_delay_minutes)
        lecture.confirmation_status = ConfirmationStatus.RETRY_PENDING.value
        lecture.next_retry_time = next_retry
        lecture.reason = reason

        retry_entry = RetryQueue(
            lecture_id=lecture.id,
            teacher_id=lecture.teacher_id,
            retry_count=lecture.retry_count,
            next_retry_time=next_retry,
            reason=reason,
            status=QueueStatus.PENDING.value,
        )
        self.db.add(retry_entry)
        self.db.flush()
        logger.info(
            "Retry #%d scheduled for lecture %s at %s",
            lecture.retry_count,
            lecture.id,
            next_retry.isoformat(),
        )
        return retry_entry

    def get_due_retries(self) -> list[RetryQueue]:
        """Return retry entries whose next_retry_time has passed."""
        now = datetime.now()
        return (
            self.db.query(RetryQueue)
            .options(joinedload(RetryQueue.lecture).joinedload(Lecture.teacher))
            .filter(
                RetryQueue.status == QueueStatus.PENDING.value,
                RetryQueue.next_retry_time <= now,
            )
            .all()
        )

    def mark_completed(self, retry_entry: RetryQueue) -> None:
        retry_entry.status = QueueStatus.COMPLETED.value
        retry_entry.updated_at = datetime.now()

    def mark_failed(self, retry_entry: RetryQueue) -> None:
        retry_entry.status = QueueStatus.FAILED.value
        retry_entry.updated_at = datetime.now()

    def get_all_pending(self) -> list[RetryQueue]:
        return (
            self.db.query(RetryQueue)
            .options(joinedload(RetryQueue.lecture).joinedload(Lecture.teacher))
            .filter(RetryQueue.status == QueueStatus.PENDING.value)
            .order_by(RetryQueue.next_retry_time)
            .all()
        )
