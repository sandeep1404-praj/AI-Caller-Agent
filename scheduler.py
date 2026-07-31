"""APScheduler job definitions."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import get_settings
from database import session_scope
from excel.export_excel import ExcelExporter
from excel.import_excel import ExcelImporter
from services.confirmation_service import ConfirmationService

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def daily_schedule_job() -> None:
    """
    Job 1: Runs daily at 5 PM.
    Read Excel, find tomorrow's lectures, create call jobs, process queue.
    """
    logger.info("Running daily schedule job")
    try:
        with session_scope() as db:
            importer = ExcelImporter(db)
            result = importer.import_file()
            logger.info("Excel import: %d rows", result["imported"])

            service = ConfirmationService(db)
            jobs_created = service.create_call_jobs_for_tomorrow()
            logger.info("Call jobs created: %d", jobs_created)

            processed = ConfirmationService.run_async(service.process_call_queue())
            logger.info("Calls processed: %d", processed)

            exporter = ExcelExporter(db)
            export_path = exporter.export_file()
            logger.info("Schedule exported to %s", export_path)
    except Exception as exc:
        logger.exception("Daily schedule job failed: %s", exc)


def retry_check_job() -> None:
    """
    Job 2: Runs every minute.
    Check retry_queue and retry due calls.
    """
    try:
        with session_scope() as db:
            service = ConfirmationService(db)
            count = ConfirmationService.run_async(service.process_retries())
            if count:
                logger.info("Retries processed: %d", count)
                exporter = ExcelExporter(db)
                exporter.export_file()
    except Exception as exc:
        logger.exception("Retry check job failed: %s", exc)


def start_scheduler() -> BackgroundScheduler:
    """Start the background scheduler with both jobs."""
    global _scheduler
    settings = get_settings()

    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        daily_schedule_job,
        CronTrigger(
            hour=settings.daily_schedule_hour,
            minute=settings.daily_schedule_minute,
        ),
        id="daily_schedule",
        name="Daily 5 PM Schedule Job",
        replace_existing=True,
    )
    _scheduler.add_job(
        retry_check_job,
        IntervalTrigger(seconds=settings.retry_check_interval_seconds),
        id="retry_check",
        name="Retry Queue Check",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — daily at %02d:%02d, retry every %ds",
        settings.daily_schedule_hour,
        settings.daily_schedule_minute,
        settings.retry_check_interval_seconds,
    )
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None
