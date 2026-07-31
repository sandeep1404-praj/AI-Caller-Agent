"""FastAPI REST API routes."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from api.schemas import (
    ActionResponse,
    CallLogResponse,
    ImportResponse,
    LectureResponse,
    RetryQueueResponse,
    StatusResponse,
    TeacherResponse,
)
from config import get_settings
from database import get_db
from excel.import_excel import ExcelImporter
from models import CallQueue, Lecture, QueueStatus, Teacher
from scheduler import _scheduler
from services.confirmation_service import ConfirmationService
from services.lecture_service import LectureService
from services.logging_service import LoggingService
from services.retry_service import RetryService
from services.teacher_service import TeacherService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/teachers", response_model=list[TeacherResponse])
def list_teachers(db: Session = Depends(get_db)):
    return TeacherService(db).get_all()


@router.get("/calls", response_model=list[LectureResponse])
def list_calls(db: Session = Depends(get_db)):
    return LectureService(db).get_all()


@router.get("/retry", response_model=list[RetryQueueResponse])
def list_retries(db: Session = Depends(get_db)):
    retries = RetryService(db).get_all_pending()
    return retries


@router.post("/call/{teacher_id}", response_model=ActionResponse)
async def trigger_call(teacher_id: str, db: Session = Depends(get_db)):
    service = ConfirmationService(db)
    success = await service.execute_call_for_teacher(teacher_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Call failed for teacher {teacher_id}")
    return ActionResponse(success=True, message=f"Call completed for teacher {teacher_id}")


@router.post("/retry/{teacher_id}", response_model=ActionResponse)
async def trigger_retry(teacher_id: str, db: Session = Depends(get_db)):
    teacher = TeacherService(db).get_by_id(teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail=f"Teacher {teacher_id} not found")

    lecture = (
        db.query(Lecture)
        .filter(Lecture.teacher_id == teacher.id)
        .order_by(Lecture.lecture_date.desc())
        .first()
    )
    if not lecture:
        raise HTTPException(status_code=404, detail="No lectures found for teacher")

    retry_service = RetryService(db)
    retry_service.schedule_retry(lecture, reason="Manual retry triggered via API")
    db.commit()

    service = ConfirmationService(db)
    success = await service.execute_call(lecture.id)
    return ActionResponse(
        success=success,
        message=f"Retry {'succeeded' if success else 'failed'} for teacher {teacher_id}",
    )


@router.get("/logs", response_model=list[CallLogResponse])
def list_logs(limit: int = 100, db: Session = Depends(get_db)):
    return LoggingService(db).get_all_logs(limit=limit)


@router.get("/status", response_model=StatusResponse)
def system_status(db: Session = Depends(get_db)):
    settings = get_settings()
    pending_calls = (
        db.query(CallQueue).filter(CallQueue.status == QueueStatus.PENDING.value).count()
    )
    pending_retries = len(RetryService(db).get_all_pending())
    total_teachers = db.query(Teacher).count()
    total_lectures = db.query(Lecture).count()

    return StatusResponse(
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        call_provider=settings.call_provider,
        scheduler_running=_scheduler is not None and _scheduler.running,
        pending_calls=pending_calls,
        pending_retries=pending_retries,
        total_teachers=total_teachers,
        total_lectures=total_lectures,
    )


@router.get("/today", response_model=list[LectureResponse])
def today_lectures(db: Session = Depends(get_db)):
    return LectureService(db).get_today_lectures()


@router.get("/tomorrow", response_model=list[LectureResponse])
def tomorrow_lectures(db: Session = Depends(get_db)):
    return LectureService(db).get_tomorrow_lectures()


@router.post("/import", response_model=ImportResponse)
def import_excel(db: Session = Depends(get_db)):
    try:
        result = ExcelImporter(db).import_file()
        return ImportResponse(**result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/schedule/run", response_model=ActionResponse)
async def run_daily_schedule(db: Session = Depends(get_db)):
    """Manually trigger the daily schedule job (for testing)."""
    importer = ExcelImporter(db)
    import_result = importer.import_file()
    service = ConfirmationService(db)
    jobs = service.create_call_jobs_for_tomorrow()
    processed = await service.process_call_queue()
    return ActionResponse(
        success=True,
        message="Daily schedule executed",
        detail={"imported": import_result["imported"], "jobs": jobs, "processed": processed},
    )
