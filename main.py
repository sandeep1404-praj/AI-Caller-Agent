"""CLI entry point for Class Call Agent."""

import argparse
import asyncio
import logging
import sys

from config import get_settings
from database import init_db, session_scope
from excel.export_excel import ExcelExporter
from excel.import_excel import ExcelImporter
from scheduler import daily_schedule_job, start_scheduler, stop_scheduler
from services.confirmation_service import ConfirmationService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_init() -> None:
    """Initialize database and import sample Excel."""
    settings = get_settings()
    settings.ensure_directories()
    init_db()
    logger.info("Database initialized at %s", settings.resolved_database_url)
    try:
        with session_scope() as db:
            result = ExcelImporter(db).import_file()
            logger.info("Imported %d rows from Excel", result["imported"])
    except FileNotFoundError:
        logger.warning("No Excel file found — place schedule at data/lecture_schedule.xlsx")


def cmd_import() -> None:
    with session_scope() as db:
        result = ExcelImporter(db).import_file()
        print(f"Imported {result['imported']} rows")
        if result["errors"]:
            print(f"Errors: {result['errors']}")


def cmd_export() -> None:
    with session_scope() as db:
        path = ExcelExporter(db).export_file()
        print(f"Exported to {path}")


def cmd_call(teacher_id: str) -> None:
    with session_scope() as db:
        service = ConfirmationService(db)
        success = asyncio.run(service.execute_call_for_teacher(teacher_id))
        print(f"Call {'succeeded' if success else 'failed'}")


def cmd_schedule() -> None:
    daily_schedule_job()


def cmd_serve() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


def cmd_run() -> None:
    """Run scheduler + API server together."""
    settings = get_settings()
    settings.ensure_directories()
    init_db()
    start_scheduler()
    logger.info("Scheduler running. Starting API server...")
    try:
        import uvicorn

        uvicorn.run(
            "app:app",
            host=settings.api_host,
            port=settings.api_port,
        )
    finally:
        stop_scheduler()


def main() -> None:
    parser = argparse.ArgumentParser(description="Class Call Agent")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize database and import Excel")
    sub.add_parser("import", help="Import Excel schedule")
    sub.add_parser("export", help="Export schedule to Excel")
    sub.add_parser("schedule", help="Run daily schedule job now")
    sub.add_parser("serve", help="Start API server only")
    sub.add_parser("run", help="Start scheduler + API server")

    call_parser = sub.add_parser("call", help="Call a specific teacher")
    call_parser.add_argument("teacher_id", help="Teacher ID to call")

    args = parser.parse_args()
    commands = {
        "init": cmd_init,
        "import": cmd_import,
        "export": cmd_export,
        "schedule": cmd_schedule,
        "serve": cmd_serve,
        "run": cmd_run,
        "call": lambda: cmd_call(args.teacher_id),
    }

    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
