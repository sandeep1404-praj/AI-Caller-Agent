"""Pydantic schemas for API request/response models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TeacherResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    teacher_id: str
    name: str
    phone_number: str
    department: str
    created_at: datetime | None = None


class LectureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    teacher_id: int
    subject: str
    lecture_date: datetime
    lecture_time: str
    room: str
    confirmation_status: str
    retry_count: int
    next_retry_time: datetime | None = None
    last_call_time: datetime | None = None
    teacher_response: str | None = None
    delay_minutes: int
    reason: str | None = None
    conversation_finished: bool
    teacher: TeacherResponse | None = None


class CallLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    teacher_id: int
    lecture_id: int | None = None
    call_start_time: datetime
    call_end_time: datetime | None = None
    duration_seconds: int | None = None
    current_state: str
    transcript: str | None = None
    final_status: str | None = None
    conversation_summary: str | None = None
    errors: str | None = None


class RetryQueueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lecture_id: int
    teacher_id: int
    retry_count: int
    next_retry_time: datetime
    reason: str | None = None
    status: str
    lecture: LectureResponse | None = None


class StatusResponse(BaseModel):
    app_name: str
    version: str
    environment: str
    call_provider: str
    scheduler_running: bool
    pending_calls: int
    pending_retries: int
    total_teachers: int
    total_lectures: int


class ActionResponse(BaseModel):
    success: bool
    message: str
    detail: dict | None = None


class ImportResponse(BaseModel):
    imported: int
    errors: list[str]
    file: str
