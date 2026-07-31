"""Read lecture schedules from the Excel workbook."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from models import LectureRecord
from utils import coerce_int, coerce_string, normalize_phone_number, parse_datetime, parse_excel_date, parse_excel_time


EXPECTED_COLUMNS = [
    "Teacher ID",
    "Teacher Name",
    "Phone Number",
    "Department",
    "Subject",
    "Lecture Date",
    "Lecture Time",
    "Room",
    "Call Status",
    "Retry Count",
    "Next Call Time",
    "Teacher Response",
    "Delay Minutes",
    "Call Attempts",
    "Last Call Time",
    "Conversation Transcript",
    "Reason",
]


class ExcelReader:
    """Load lecture rows from the source workbook."""

    def __init__(self, workbook_path: Path, sheet_name: str, timezone) -> None:
        self.workbook_path = workbook_path
        self.sheet_name = sheet_name
        self.timezone = timezone

    def read_lectures(self) -> list[LectureRecord]:
        """Return all lecture rows from the configured sheet."""

        if not self.workbook_path.exists():
            raise FileNotFoundError(f"Excel workbook not found: {self.workbook_path}")

        frame = pd.read_excel(self.workbook_path, sheet_name=self.sheet_name)
        frame.columns = [str(column).strip() for column in frame.columns]
        self._validate_columns(frame.columns)

        lectures: list[LectureRecord] = []
        for index, row in frame.iterrows():
            lecture_date = parse_excel_date(row["Lecture Date"])
            lecture_time = parse_excel_time(row["Lecture Time"])
            if lecture_date is None or lecture_time is None:
                continue

            lecture = LectureRecord(
                teacher_id=coerce_string(row["Teacher ID"]),
                teacher_name=coerce_string(row["Teacher Name"]),
                phone_number=normalize_phone_number(coerce_string(row["Phone Number"])),
                department=coerce_string(row["Department"]),
                subject=coerce_string(row["Subject"]),
                lecture_date=lecture_date,
                lecture_time=lecture_time,
                room=coerce_string(row.get("Room", "")),
                call_status=coerce_string(row.get("Call Status", "Pending")) or "Pending",
                retry_count=coerce_int(row.get("Retry Count", 0)),
                next_call_time=parse_datetime(row.get("Next Call Time"), self.timezone),
                teacher_response=coerce_string(row.get("Teacher Response", "")),
                delay_minutes=coerce_int(row.get("Delay Minutes", 0)),
                call_attempts=coerce_int(row.get("Call Attempts", 0)),
                last_call_time=parse_datetime(row.get("Last Call Time"), self.timezone),
                conversation_transcript=coerce_string(row.get("Conversation Transcript", "")),
                reason=coerce_string(row.get("Reason", "")),
                source_row=index + 2,
            )
            lectures.append(lecture)
        return lectures

    def _validate_columns(self, columns: Iterable[str]) -> None:
        missing = [column for column in EXPECTED_COLUMNS if column not in columns]
        if missing:
            raise ValueError(f"Missing required Excel columns: {', '.join(missing)}")
