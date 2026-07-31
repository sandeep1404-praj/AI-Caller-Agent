"""Lecture repository and service."""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session, joinedload

from models import ConfirmationStatus, Lecture, Teacher

logger = logging.getLogger(__name__)


class LectureService:
    """Business logic for lecture schedule management."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(self) -> list[Lecture]:
        return (
            self.db.query(Lecture)
            .options(joinedload(Lecture.teacher))
            .order_by(Lecture.lecture_date)
            .all()
        )

    def get_by_id(self, lecture_id: int) -> Lecture | None:
        return (
            self.db.query(Lecture)
            .options(joinedload(Lecture.teacher))
            .filter(Lecture.id == lecture_id)
            .first()
        )

    def get_tomorrow_lectures(self) -> list[Lecture]:
        tomorrow = date.today() + timedelta(days=1)
        start = datetime.combine(tomorrow, datetime.min.time())
        end = datetime.combine(tomorrow, datetime.max.time())
        return (
            self.db.query(Lecture)
            .options(joinedload(Lecture.teacher))
            .filter(Lecture.lecture_date >= start, Lecture.lecture_date <= end)
            .filter(
                Lecture.confirmation_status.in_(
                    [ConfirmationStatus.PENDING.value, ConfirmationStatus.RETRY_PENDING.value]
                )
            )
            .all()
        )

    def get_today_lectures(self) -> list[Lecture]:
        today = date.today()
        start = datetime.combine(today, datetime.min.time())
        end = datetime.combine(today, datetime.max.time())
        return (
            self.db.query(Lecture)
            .options(joinedload(Lecture.teacher))
            .filter(Lecture.lecture_date >= start, Lecture.lecture_date <= end)
            .all()
        )

    def create_or_update(
        self,
        teacher: Teacher,
        subject: str,
        lecture_date: datetime,
        lecture_time: str,
        room: str,
    ) -> Lecture:
        existing = (
            self.db.query(Lecture)
            .filter(
                Lecture.teacher_id == teacher.id,
                Lecture.subject == subject,
                Lecture.lecture_date == lecture_date,
                Lecture.lecture_time == lecture_time,
            )
            .first()
        )
        if existing:
            existing.room = room
            existing.updated_at = datetime.now()
            return existing

        lecture = Lecture(
            teacher_id=teacher.id,
            subject=subject,
            lecture_date=lecture_date,
            lecture_time=lecture_time,
            room=room,
        )
        self.db.add(lecture)
        self.db.flush()
        return lecture

    def update_confirmation(
        self,
        lecture: Lecture,
        status: str,
        teacher_response: str = "",
        delay_minutes: int = 0,
        reason: str = "",
        transcript: str = "",
        conversation_finished: bool = False,
    ) -> Lecture:
        lecture.confirmation_status = status
        lecture.teacher_response = teacher_response
        lecture.delay_minutes = delay_minutes
        lecture.reason = reason
        lecture.transcript = transcript
        lecture.conversation_finished = conversation_finished
        lecture.last_call_time = datetime.now()
        lecture.updated_at = datetime.now()
        self.db.flush()
        return lecture
