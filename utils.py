"""Shared helpers for date handling, file I/O, and data normalization."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import json
import math
import re
from typing import Iterable, Sequence

import pandas as pd


_PHONE_DIGIT_RE = re.compile(r"[^0-9+]")


def ensure_directory(path: Path) -> Path:
    """Create a directory and return it."""

    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text_file(path: Path) -> str:
    """Read UTF-8 text from a file when present."""

    return path.read_text(encoding="utf-8")


def write_text_file(path: Path, content: str) -> None:
    """Write UTF-8 text to a file, creating parents as needed."""

    ensure_directory(path.parent)
    path.write_text(content, encoding="utf-8")


def now_utc() -> datetime:
    """Return the current UTC time with timezone information."""

    return datetime.now(timezone.utc)


def now_local(tz) -> datetime:
    """Return the current localized time."""

    return datetime.now(tz)


def combine_date_and_time(value_date: date, value_time: time, tz) -> datetime:
    """Create a timezone-aware datetime from Excel date and time cells."""

    return datetime.combine(value_date, value_time, tzinfo=tz)


def normalize_phone_number(phone_number: str) -> str:
    """Strip formatting characters from a phone number."""

    cleaned = _PHONE_DIGIT_RE.sub("", str(phone_number or "").strip())
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned


def coerce_string(value: object) -> str:
    """Convert pandas/openpyxl values to a trimmed string."""

    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def coerce_int(value: object, default: int = 0) -> int:
    """Best-effort integer coercion for workbook values."""

    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_datetime(value: object, tz) -> datetime | None:
    """Parse mixed Excel / string datetime values into a timezone-aware datetime."""

    if value is None or value == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    native = parsed.to_pydatetime()
    if native.tzinfo is None:
        return native.replace(tzinfo=tz)
    return native.astimezone(tz)


def parse_excel_date(value: object) -> date | None:
    """Parse a workbook date value."""

    if value is None or value == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def parse_excel_time(value: object) -> time | None:
    """Parse a workbook time value."""

    if value is None or value == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        if isinstance(value, time):
            return value
        return None
    return parsed.to_pydatetime().time().replace(microsecond=0)


def minutes_from_now(minutes: int, tz) -> datetime:
    """Return a future timestamp offset by a number of minutes."""

    return now_local(tz) + timedelta(minutes=minutes)


def isoformat_or_empty(value: datetime | None) -> str:
    """Convert a datetime to ISO-8601 or return an empty string."""

    if value is None:
        return ""
    return value.isoformat()


def safe_json_dumps(payload: object) -> str:
    """Serialize a JSON payload with stable formatting."""

    return json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)


def unique_preserving_order(items: Sequence[str]) -> list[str]:
    """Return items without duplicates while preserving input order."""

    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def chunked(items: Sequence[object], size: int) -> list[list[object]]:
    """Split a sequence into fixed-size chunks."""

    return [list(items[index : index + size]) for index in range(0, len(items), size)]
