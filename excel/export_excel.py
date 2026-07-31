"""Excel schedule export."""

import logging
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import Session, joinedload

from config import get_settings
from models import Lecture

logger = logging.getLogger(__name__)

EXPORT_COLUMNS = [
    "Teacher ID",
    "Teacher Name",
    "Phone Number",
    "Department",
    "Subject",
    "Lecture Date",
    "Lecture Time",
    "Room",
    "Confirmation Status",
    "Retry Count",
    "Next Retry Time",
    "Last Call Time",
    "Teacher Response",
    "Delay Minutes",
    "Reason",
    "Transcript",
    "Conversation Finished",
]


class ExcelExporter:
    """Export lecture schedule with confirmation data to Excel."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def export_file(self, file_path: str | Path | None = None) -> Path:
        """Export all lectures to Excel and return the file path."""
        path = Path(file_path) if file_path else Path(self.settings.excel_file_path)
        if not path.is_absolute():
            path = self.settings.data_dir / path.name

        lectures = (
            self.db.query(Lecture)
            .options(joinedload(Lecture.teacher))
            .order_by(Lecture.lecture_date, Lecture.lecture_time)
            .all()
        )

        wb = Workbook()
        ws = wb.active
        ws.title = "Lecture Schedule"

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

        for col_idx, header in enumerate(EXPORT_COLUMNS, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill

        for row_idx, lecture in enumerate(lectures, start=2):
            teacher = lecture.teacher
            row_data = [
                teacher.teacher_id if teacher else "",
                teacher.name if teacher else "",
                teacher.phone_number if teacher else "",
                teacher.department if teacher else "",
                lecture.subject,
                lecture.lecture_date.strftime("%Y-%m-%d") if lecture.lecture_date else "",
                lecture.lecture_time,
                lecture.room,
                lecture.confirmation_status,
                lecture.retry_count,
                lecture.next_retry_time.isoformat() if lecture.next_retry_time else "",
                lecture.last_call_time.isoformat() if lecture.last_call_time else "",
                lecture.teacher_response or "",
                lecture.delay_minutes,
                lecture.reason or "",
                lecture.transcript or "",
                "Yes" if lecture.conversation_finished else "No",
            ]
            for col_idx, value in enumerate(row_data, start=1):
                ws.cell(row=row_idx, column=col_idx, value=value)

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

        path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(path)
        logger.info("Exported %d lectures to %s", len(lectures), path)
        return path
