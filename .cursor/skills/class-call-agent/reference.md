# Class Call Agent — Detailed Reference

Use this when SKILL.md is not enough (schema details, test setup, provider interface).

---

## Full Directory Map

```
Caller agent/
├── app.py                      # FastAPI factory + lifespan (scheduler start/stop)
├── main.py                     # CLI argparse entry
├── config.py                   # pydantic-settings Settings
├── database.py                 # engine, SessionLocal, init_db, get_db, session_scope
├── models.py                   # SQLAlchemy ORM + enums
├── scheduler.py                # APScheduler jobs
├── logger.py                   # Rotating file logger (legacy, optional)
├── pytest.ini                  # testpaths=tests, asyncio_mode=auto
├── requirements.txt
├── .env / .env.example
├── SETUP.md
├── README.md
├── api/
│   ├── routes.py               # All REST endpoints
│   └── schemas.py              # Pydantic response models
├── services/
│   ├── confirmation_service.py # Main orchestrator: queue, execute_call, retries
│   ├── lecture_service.py      # CRUD lectures, get_tomorrow/today
│   ├── teacher_service.py      # CRUD teachers
│   ├── retry_service.py        # schedule_retry, get_due_retries
│   └── logging_service.py      # call_logs, conversation_history, file logs
├── providers/
│   ├── call_provider.py        # ABC: CallProvider, CallContext, CallResult
│   ├── desktop_call_provider.py# Mic/speaker simulator
│   ├── future_telephony_provider.py  # Stub for Twilio/Exotel
│   └── factory.py              # get_call_provider()
├── ai/
│   ├── gemini_client.py        # google-genai SDK wrapper (JSON schema, retries)
│   ├── conversation_manager.py # Turn history + state
│   └── prompt_manager.py       # SYSTEM_PROMPT templates
├── speech/
│   ├── audio_manager.py        # record(), speak(), play(), cleanup()
│   ├── audio_player.py         # pygame MP3 playback
│   ├── speech_to_text.py       # SpeechRecognition + AudioManager
│   ├── text_to_speech.py       # edge-tts via AudioManager
│   └── voice_activity.py       # Energy-based VAD
├── excel/
│   ├── import_excel.py         # ExcelImporter
│   └── export_excel.py         # ExcelExporter
├── scripts/
│   └── create_sample_excel.py  # Sample data generator
├── tests/
│   ├── conftest.py             # in-memory SQLite fixtures
│   ├── test_services.py        # Service + AI unit tests
│   └── test_api.py             # FastAPI TestClient tests
├── data/                       # lecture_schedule.xlsx, caller_agent.db
└── logs/                       # call_{id}_{timestamp}.json
```

---

## ORM Models Detail

### Teacher
- `teacher_id` (str, unique) — business ID e.g. "T001"
- `name`, `phone_number`, `department`

### Lecture
- FK → `teachers.id`
- `subject`, `lecture_date`, `lecture_time`, `room`
- `confirmation_status` — see ConfirmationStatus enum
- `retry_count`, `next_retry_time`, `last_call_time`
- `teacher_response`, `delay_minutes`, `reason`, `transcript`
- `conversation_finished` (bool)

### CallQueue
- `lecture_id`, `teacher_id`, `status` (QueueStatus), `scheduled_at`

### RetryQueue
- `lecture_id`, `teacher_id`, `retry_count`, `next_retry_time`, `reason`, `status`

### CallLog
- `call_start_time`, `call_end_time`, `duration_seconds`
- `current_state` (CallState), `transcript`, `gemini_responses` (JSON str)
- `errors`, `conversation_summary`, `final_status`, `retry_history`

### ConversationHistory
- `call_log_id`, `role` ("assistant"|"teacher"), `content`, `timestamp`

---

## Enums

### ConfirmationStatus
Pending, Available, Unavailable, Late, Leave, Emergency, Substitute Requested, Retry Pending, No Response, Failed, Calling

### CallState
PENDING, CALLING, LISTENING, THINKING, SPEAKING, WAITING, FINISHED, RETRY_PENDING, FAILED

### QueueStatus
pending, in_progress, completed, failed, cancelled

---

## CallProvider Interface

```python
class CallProvider(ABC):
    async def initiate_call(self, context: CallContext) -> CallResult: ...
    async def hang_up(self) -> None: ...
    def is_available(self) -> bool: ...
```

### CallContext fields
teacher_id, teacher_name, phone_number, department, subject, lecture_date, lecture_time, room, call_log_id

### CallResult fields
status (CallResultStatus), confirmation_status, delay_minutes, reason, transcript, conversation_finished, turns, gemini_responses, error_message, duration_seconds

### CallResultStatus
success, no_response, failed, timeout, retry

---

## ConfirmationService Key Methods

| Method | Purpose |
|--------|---------|
| `create_call_jobs_for_tomorrow()` | Query tomorrow lectures → insert call_queue |
| `process_call_queue()` | Process all pending call_queue entries |
| `execute_call(lecture_id)` | Single call: log → provider → update lecture |
| `execute_call_for_teacher(teacher_id)` | Find pending lecture for teacher → execute_call |
| `process_retries()` | Process due retry_queue entries |
| `run_async(coro)` | Run async from sync scheduler context |

---

## DesktopCallProvider Loop

1. Print "Calling {name}..."
2. `ConversationManager.generate_opening(context)`
3. TTS speak opening
4. Loop until finished or timeout:
   - STT listen
   - `process_teacher_input(text)` → Gemini
   - TTS speak reply
5. Return `CallResult`

Max duration: `call_timeout_seconds` (120s). Max no-response prompts: 2.

---

## Test Setup

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

- `conftest.py`: in-memory SQLite, `db_session`, `sample_teacher`, `sample_lecture`
- `test_api.py`: overrides `get_db` dependency, uses TestClient
- Mock Gemini in conversation tests via `patch("ai.conversation_manager.GeminiClient")`

---

## Adding Telephony (Future)

1. Set `.env`: `CALL_PROVIDER=telephony`
2. Implement `TelephonyCallProvider` in `providers/future_telephony_provider.py`:
   - Same `initiate_call(context) -> CallResult` contract
   - Use Twilio/Exotel webhooks or media streams for STT/TTS
   - Map telephony events to CallState transitions
3. Do NOT change: scheduler, confirmation_service (except if needed for async webhook pattern), retry_service, models, AI prompts

---

## Dependencies

| Package | Use |
|---------|-----|
| fastapi, uvicorn | API server |
| sqlalchemy | ORM |
| pydantic-settings | Config |
| google-genai | Gemini (official SDK) |
| SpeechRecognition, sounddevice, soundfile, edge-tts, pygame | Desktop voice |
| numpy, scipy | Audio processing / VAD |
| openpyxl | Excel |
| APScheduler | Cron jobs |
| pytest, httpx | Testing |

Works cross-platform via pip — no manual driver install required. See SETUP.md.

---

## Sample Teacher IDs (from create_sample_excel.py)

T001 Professor Amit Sharma, T002 Dr. Priya Patel, T003 Professor Rajesh Kumar, T004 Dr. Sneha Reddy, T005 Professor Vikram Singh

Lecture dates in sample Excel are set to **tomorrow** relative to generation date.
