"""SQLAlchemy ORM models."""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class ConfirmationStatus(str, PyEnum):
    PENDING = "Pending"
    AVAILABLE = "Available"
    UNAVAILABLE = "Unavailable"
    LATE = "Late"
    LEAVE = "Leave"
    EMERGENCY = "Emergency"
    SUBSTITUTE_REQUESTED = "Substitute Requested"
    RETRY_PENDING = "Retry Pending"
    NO_RESPONSE = "No Response"
    FAILED = "Failed"
    CALLING = "Calling"


class CallState(str, PyEnum):
    PENDING = "PENDING"
    CALLING = "CALLING"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    WAITING = "WAITING"
    FINISHED = "FINISHED"
    RETRY_PENDING = "RETRY_PENDING"
    FAILED = "FAILED"


class QueueStatus(str, PyEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    department: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    lectures: Mapped[list["Lecture"]] = relationship(back_populates="teacher")
    call_logs: Mapped[list["CallLog"]] = relationship(back_populates="teacher")


class Lecture(Base):
    __tablename__ = "lectures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    lecture_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    lecture_time: Mapped[str] = mapped_column(String(20), nullable=False)
    room: Mapped[str] = mapped_column(String(50), nullable=False)
    confirmation_status: Mapped[str] = mapped_column(
        String(50), default=ConfirmationStatus.PENDING.value
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_call_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    teacher_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_finished: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    teacher: Mapped["Teacher"] = relationship(back_populates="lectures")
    call_queue_entries: Mapped[list["CallQueue"]] = relationship(back_populates="lecture")
    retry_queue_entries: Mapped[list["RetryQueue"]] = relationship(back_populates="lecture")


class CallQueue(Base):
    __tablename__ = "call_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=QueueStatus.PENDING.value)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    lecture: Mapped["Lecture"] = relationship(back_populates="call_queue_entries")


class RetryQueue(Base):
    __tablename__ = "retry_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lecture_id: Mapped[int] = mapped_column(ForeignKey("lectures.id"), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=QueueStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    lecture: Mapped["Lecture"] = relationship(back_populates="retry_queue_entries")


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id"), nullable=False)
    lecture_id: Mapped[int | None] = mapped_column(ForeignKey("lectures.id"), nullable=True)
    call_start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    call_end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_state: Mapped[str] = mapped_column(String(30), default=CallState.PENDING.value)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_responses: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    errors: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    teacher: Mapped["Teacher"] = relationship(back_populates="call_logs")
    conversation_entries: Mapped[list["ConversationHistory"]] = relationship(
        back_populates="call_log"
    )


class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_log_id: Mapped[int] = mapped_column(ForeignKey("call_logs.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    call_log: Mapped["CallLog"] = relationship(back_populates="conversation_entries")
