"""Core confirmation call orchestration service."""

import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from config import get_settings
from excel.export_excel import ExcelExporter
from models import CallQueue, CallState, ConfirmationStatus, Lecture, QueueStatus
from providers.call_provider import CallContext, CallProvider, CallResultStatus
from providers.factory import get_call_provider
from services.lecture_service import LectureService
from services.logging_service import LoggingService
from services.retry_service import RetryService

logger = logging.getLogger(__name__)


class ConfirmationService:
    """Orchestrate lecture confirmation calls end-to-end."""

    def __init__(self, db: Session, call_provider: CallProvider | None = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.call_provider = call_provider or get_call_provider()
        self.lecture_service = LectureService(db)
        self.retry_service = RetryService(db)
        self.logging_service = LoggingService(db)

    async def process_call_queue(self) -> int:
        """Process all pending call queue entries. Returns count processed."""
        pending = (
            self.db.query(CallQueue)
            .options(joinedload(CallQueue.lecture).joinedload(Lecture.teacher))
            .filter(CallQueue.status == QueueStatus.PENDING.value)
            .all()
        )
        count = 0
        for entry in pending:
            entry.status = QueueStatus.IN_PROGRESS.value
            entry.started_at = datetime.now()
            self.db.flush()

            success = await self.execute_call(entry.lecture_id)
            entry.status = QueueStatus.COMPLETED.value if success else QueueStatus.FAILED.value
            entry.completed_at = datetime.now()
            self.db.commit()
            count += 1
        return count

    async def execute_call(self, lecture_id: int) -> bool:
        """Execute a single confirmation call for a lecture."""
        lecture = self.lecture_service.get_by_id(lecture_id)
        if not lecture or not lecture.teacher:
            logger.error("Lecture %s or teacher not found", lecture_id)
            return False

        teacher = lecture.teacher
        call_log = self.logging_service.create_call_log(teacher.id, lecture.id)
        self.db.commit()

        context = CallContext(
            teacher_id=teacher.teacher_id,
            teacher_name=teacher.name,
            phone_number=teacher.phone_number,
            department=teacher.department,
            subject=lecture.subject,
            lecture_date=lecture.lecture_date.strftime("%Y-%m-%d"),
            lecture_time=lecture.lecture_time,
            room=lecture.room,
            call_log_id=call_log.id,
        )

        lecture.confirmation_status = ConfirmationStatus.CALLING.value
        self.logging_service.update_call_log(
            call_log, current_state=CallState.CALLING.value
        )
        self.db.commit()

        try:
            result = await self.call_provider.initiate_call(context)

            summary = ""
            if result.transcript:
                try:
                    from ai.gemini_client import GeminiClient
                    summary = GeminiClient().generate_summary(result.transcript)
                except Exception:
                    summary = "Summary unavailable"

            if result.status == CallResultStatus.SUCCESS and result.conversation_finished:
                self.lecture_service.update_confirmation(
                    lecture,
                    status=result.confirmation_status,
                    teacher_response=result.transcript.split("\n")[-1] if result.transcript else "",
                    delay_minutes=result.delay_minutes,
                    reason=result.reason,
                    transcript=result.transcript,
                    conversation_finished=True,
                )
                final_state = CallState.FINISHED.value
            elif result.status in (
                CallResultStatus.NO_RESPONSE,
                CallResultStatus.TIMEOUT,
                CallResultStatus.FAILED,
            ):
                self.retry_service.schedule_retry(
                    lecture, reason=result.error_message or result.status.value
                )
                final_state = CallState.RETRY_PENDING.value
            else:
                final_state = CallState.FINISHED.value

            self.logging_service.update_call_log(
                call_log,
                end_time=datetime.now(),
                duration_seconds=result.duration_seconds,
                current_state=final_state,
                transcript=result.transcript,
                gemini_responses=result.gemini_responses,
                errors=result.error_message,
                conversation_summary=summary,
                final_status=result.confirmation_status,
            )
            self.logging_service.write_file_log(call_log)
            self.db.commit()

            self._export_excel_snapshot()
            return result.status == CallResultStatus.SUCCESS

        except Exception as exc:
            logger.exception("Call execution failed: %s", exc)
            self.retry_service.schedule_retry(lecture, reason=str(exc))
            self.logging_service.update_call_log(
                call_log,
                end_time=datetime.now(),
                current_state=CallState.FAILED.value,
                errors=str(exc),
            )
            self.db.commit()
            self._export_excel_snapshot()
            return False

    async def execute_call_for_teacher(self, teacher_id: str) -> bool:
        """Manually trigger a call for a teacher's next pending lecture."""
        from models import Lecture
        from services.teacher_service import TeacherService

        teacher = TeacherService(self.db).get_by_id(teacher_id)
        if not teacher:
            logger.error("Teacher %s not found", teacher_id)
            return False

        lecture = (
            self.db.query(Lecture)
            .filter(
                Lecture.teacher_id == teacher.id,
                Lecture.confirmation_status.in_(
                    [
                        ConfirmationStatus.PENDING.value,
                        ConfirmationStatus.RETRY_PENDING.value,
                    ]
                ),
            )
            .order_by(Lecture.lecture_date)
            .first()
        )
        if not lecture:
            logger.warning("No pending lectures for teacher %s", teacher_id)
            return False

        return await self.execute_call(lecture.id)

    async def process_retries(self) -> int:
        """Process all due retry entries. Returns count processed."""
        due = self.retry_service.get_due_retries()
        count = 0
        for entry in due:
            success = await self.execute_call(entry.lecture_id)
            if success:
                self.retry_service.mark_completed(entry)
            else:
                self.retry_service.mark_failed(entry)
            self.db.commit()
            count += 1
        return count

    def create_call_jobs_for_tomorrow(self) -> int:
        """Find tomorrow's lectures and enqueue call jobs."""
        lectures = self.lecture_service.get_tomorrow_lectures()
        count = 0
        for lecture in lectures:
            existing = (
                self.db.query(CallQueue)
                .filter(
                    CallQueue.lecture_id == lecture.id,
                    CallQueue.status.in_(
                        [QueueStatus.PENDING.value, QueueStatus.IN_PROGRESS.value]
                    ),
                )
                .first()
            )
            if existing:
                continue

            job = CallQueue(
                lecture_id=lecture.id,
                teacher_id=lecture.teacher_id,
                status=QueueStatus.PENDING.value,
                scheduled_at=datetime.now(),
            )
            self.db.add(job)
            count += 1

        self.db.commit()
        logger.info("Created %d call jobs for tomorrow's lectures", count)
        return count

    @staticmethod
    def run_async(coro):
        """Helper to run async code from sync scheduler context."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, coro).result()
            return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def _export_excel_snapshot(self) -> None:
        """Best-effort Excel refresh so workbook stays in sync with the database."""
        try:
            ExcelExporter(self.db).export_file()
        except Exception as exc:
            logger.exception("Excel export refresh failed: %s", exc)
