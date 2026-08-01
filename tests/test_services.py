"""Unit tests for Class Call Agent."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from models import ConfirmationStatus, Teacher, Lecture
from providers.call_provider import CallContext, CallResult, CallResultStatus
from services.teacher_service import TeacherService
from services.lecture_service import LectureService
from services.retry_service import RetryService
from ai.prompt_manager import SYSTEM_PROMPT


class TestPromptManager:
    def test_system_prompt_contains_rules(self):
        assert "College Lecture Confirmation Assistant" in SYSTEM_PROMPT
        assert "conversation_finished" in SYSTEM_PROMPT
        assert "delay_minutes" in SYSTEM_PROMPT

    def test_system_prompt_has_status_mapping(self):
        assert "Available" in SYSTEM_PROMPT
        assert "Unavailable" in SYSTEM_PROMPT
        assert "Late" in SYSTEM_PROMPT


class TestTeacherService:
    def test_create_teacher(self, db_session):
        service = TeacherService(db_session)
        teacher = service.create_or_update(
            teacher_id="T001",
            name="Professor Amit",
            phone_number="+91-9876543210",
            department="CS",
        )
        db_session.commit()
        assert teacher.id is not None
        assert teacher.teacher_id == "T001"
        assert teacher.name == "Professor Amit"

    def test_get_by_id(self, db_session):
        service = TeacherService(db_session)
        service.create_or_update("T002", "Dr. Priya", "+91-111", "ECE")
        db_session.commit()
        found = service.get_by_id("T002")
        assert found is not None
        assert found.name == "Dr. Priya"

    def test_update_existing_teacher(self, db_session):
        service = TeacherService(db_session)
        service.create_or_update("T003", "Old Name", "+91-111", "ME")
        db_session.commit()
        updated = service.create_or_update("T003", "New Name", "+91-222", "ME")
        db_session.commit()
        assert updated.name == "New Name"
        assert updated.phone_number == "+91-222"


class TestLectureService:
    def _create_teacher(self, db_session):
        return TeacherService(db_session).create_or_update(
            "T001", "Professor Amit", "+91-9876543210", "CS"
        )

    def test_create_lecture(self, db_session):
        teacher = self._create_teacher(db_session)
        db_session.commit()
        service = LectureService(db_session)
        lecture = service.create_or_update(
            teacher=teacher,
            subject="DBMS",
            lecture_date=datetime.now() + timedelta(days=1),
            lecture_time="10:00 AM",
            room="Lab-301",
        )
        db_session.commit()
        assert lecture.id is not None
        assert lecture.subject == "DBMS"

    def test_get_tomorrow_lectures(self, db_session):
        teacher = self._create_teacher(db_session)
        db_session.commit()
        service = LectureService(db_session)
        tomorrow = datetime.combine(
            (datetime.now() + timedelta(days=1)).date(), datetime.min.time()
        )
        service.create_or_update(teacher, "DBMS", tomorrow, "10:00 AM", "Lab-301")
        db_session.commit()
        lectures = service.get_tomorrow_lectures()
        assert len(lectures) >= 1

    def test_update_confirmation(self, db_session):
        teacher = self._create_teacher(db_session)
        db_session.commit()
        service = LectureService(db_session)
        lecture = service.create_or_update(
            teacher, "DBMS", datetime.now() + timedelta(days=1), "10:00 AM", "Lab-301"
        )
        db_session.commit()
        service.update_confirmation(
            lecture,
            status=ConfirmationStatus.AVAILABLE.value,
            teacher_response="Yes, I will be available",
            conversation_finished=True,
        )
        db_session.commit()
        assert lecture.confirmation_status == ConfirmationStatus.AVAILABLE.value
        assert lecture.conversation_finished is True


class TestRetryService:
    def _create_lecture(self, db_session):
        teacher = TeacherService(db_session).create_or_update(
            "T001", "Professor Amit", "+91-9876543210", "CS"
        )
        db_session.commit()
        lecture = LectureService(db_session).create_or_update(
            teacher, "DBMS", datetime.now() + timedelta(days=1), "10:00 AM", "Lab-301"
        )
        db_session.commit()
        return lecture

    def test_schedule_retry(self, db_session):
        lecture = self._create_lecture(db_session)
        service = RetryService(db_session)
        entry = service.schedule_retry(lecture, reason="No response")
        db_session.commit()
        assert entry is not None
        assert lecture.retry_count == 1
        assert lecture.confirmation_status == ConfirmationStatus.RETRY_PENDING.value

    def test_max_retries_exceeded(self, db_session):
        lecture = self._create_lecture(db_session)
        lecture.retry_count = 3
        db_session.commit()
        service = RetryService(db_session)
        entry = service.schedule_retry(lecture, reason="No response")
        db_session.commit()
        assert entry is None
        assert lecture.confirmation_status == ConfirmationStatus.NO_RESPONSE.value


class TestCallProvider:
    def test_call_context_creation(self):
        ctx = CallContext(
            teacher_id="T001",
            teacher_name="Professor Amit",
            phone_number="+91-9876543210",
            department="CS",
            subject="DBMS",
            lecture_date="2026-08-01",
            lecture_time="10:00 AM",
            room="Lab-301",
        )
        assert ctx.teacher_name == "Professor Amit"

    def test_call_result_defaults(self):
        result = CallResult(
            status=CallResultStatus.SUCCESS,
            confirmation_status="Available",
        )
        assert result.delay_minutes == 0
        assert result.conversation_finished is False


class TestConfirmationService:
    @pytest.mark.asyncio
    async def test_execute_call_refreshes_excel_export(self, db_session):
        teacher = TeacherService(db_session).create_or_update(
            "T100", "Professor Test", "+91-9999999999", "CS"
        )
        db_session.commit()
        lecture = LectureService(db_session).create_or_update(
            teacher,
            "DBMS",
            datetime.now() + timedelta(days=1),
            "10:00 AM",
            "Lab-301",
        )
        db_session.commit()

        call_provider = MagicMock()
        call_provider.initiate_call = AsyncMock(
            return_value=CallResult(
                status=CallResultStatus.SUCCESS,
                confirmation_status=ConfirmationStatus.UNAVAILABLE.value,
                conversation_finished=True,
                transcript="Teacher: I am not available",
                reason="Busy",
            )
        )

        with patch("services.confirmation_service.ExcelExporter.export_file") as mock_export:
            from services.confirmation_service import ConfirmationService

            service = ConfirmationService(db_session, call_provider=call_provider)
            success = await service.execute_call(lecture.id)

        assert success is True
        mock_export.assert_called_once()
        updated = LectureService(db_session).get_by_id(lecture.id)
        assert updated is not None
        assert updated.confirmation_status == ConfirmationStatus.UNAVAILABLE.value
        assert updated.reason == "Busy"


class TestExcelExporter:
    def test_export_uses_fallback_when_save_is_locked(self, db_session, tmp_path):
        from excel.export_excel import ExcelExporter

        teacher = TeacherService(db_session).create_or_update(
            "T200", "Professor Fallback", "+91-8888888888", "CS"
        )
        db_session.commit()
        LectureService(db_session).create_or_update(
            teacher,
            "DBMS",
            datetime.now() + timedelta(days=1),
            "10:00 AM",
            "Lab-301",
        )
        db_session.commit()

        exporter = ExcelExporter(db_session)
        target = tmp_path / "lecture_schedule.xlsx"

        with patch("openpyxl.workbook.workbook.Workbook.save", side_effect=PermissionError("locked")):
            with patch.object(exporter, "_save_with_excel_com") as mock_fallback:
                exporter.export_file(target)

        mock_fallback.assert_called_once()


class TestProviderFactory:
    def test_desktop_provider_selected(self):
        with patch("providers.factory.get_settings") as mock_settings:
            mock_settings.return_value.call_provider = "desktop"
            from providers.factory import get_call_provider
            from providers.desktop_call_provider import DesktopCallProvider

            provider = get_call_provider()
            assert isinstance(provider, DesktopCallProvider)


class TestGeminiClient:
    def test_parse_json_clean(self):
        from ai.gemini_client import GeminiClient

        result = GeminiClient._parse_json('{"reply": "Hello", "status": "Pending"}')
        assert result is not None
        assert result["reply"] == "Hello"

    def test_parse_json_with_markdown(self):
        from ai.gemini_client import GeminiClient

        text = '```json\n{"reply": "Hello", "status": "Available"}\n```'
        result = GeminiClient._parse_json(text)
        assert result is not None
        assert result["status"] == "Available"


class TestConversationManager:
    def test_initial_state(self):
        with patch("ai.conversation_manager.GeminiClient"):
            from ai.conversation_manager import ConversationManager
            from models import CallState

            mgr = ConversationManager()
            assert mgr.current_state == CallState.PENDING
            assert mgr.turn_count == 0

    def test_no_response_result(self):
        with patch("ai.conversation_manager.GeminiClient"):
            from ai.conversation_manager import ConversationManager

            mgr = ConversationManager()
            result = mgr.process_teacher_input("")
            assert result["conversation_finished"] is False


class TestExcelImporter:
    def test_parse_date_formats(self):
        from excel.import_excel import ExcelImporter

        assert ExcelImporter._parse_date("2026-08-01").year == 2026
        assert ExcelImporter._parse_date("01-08-2026").day == 1
        assert ExcelImporter._parse_date("01/08/2026").month == 8

    def test_validate_headers_missing(self):
        from excel.import_excel import ExcelImporter

        with pytest.raises(ValueError, match="Missing required columns"):
            ExcelImporter._validate_headers(["Teacher ID", "Teacher Name"])
