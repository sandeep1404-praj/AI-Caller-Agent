---
name: class-call-agent
description: >-
  Complete context for the Class Call Agent project — AI lecture confirmation
  system for colleges using Gemini, desktop call simulator, SQLite, Excel, and
  FastAPI. Use when working in Caller agent repo, modifying call flow, scheduler,
  retry logic, Gemini prompts, speech modules, API routes, Excel import/export,
  or adding telephony provider. Read this skill first before exploring the codebase.
---

# Class Call Agent — Project Context

**Read this skill before exploring the codebase.** It contains architecture, flows, conventions, and file responsibilities.

**Project root:** `Caller agent/` (flat layout — no nested package folder)

**Setup guide:** [SETUP.md](../../SETUP.md) | **Full docs:** [README.md](../../README.md)

---

## What This Project Does

Every day at **5:00 PM**, the system:

1. Reads lecture schedule from Excel (`data/lecture_schedule.xlsx`)
2. Finds teachers with lectures **tomorrow**
3. Calls each teacher (desktop simulator: mic + speakers)
4. Uses **Gemini 2.5 Flash** to converse and classify responses
5. Updates SQLite DB and exports Excel
6. Retries failed calls automatically (max 3, 10 min apart)

**No telephony yet.** Development uses `DesktopCallProvider`. Future: set `CALL_PROVIDER=telephony` and implement `TelephonyCallProvider` — nothing else changes.

---

## Architecture (Clean / Provider Pattern)

```
Entry points          Business logic         Infrastructure
─────────────         ────────────────       ──────────────
main.py (CLI)    →    services/          →   database.py
app.py (FastAPI)      confirmation_service    models.py
scheduler.py          lecture_service         config.py
                      retry_service
                      logging_service
                      teacher_service

Call abstraction      AI / Speech            Data I/O
──────────────        ──────────             ────────
providers/            ai/                    excel/
  call_provider.py      gemini_client.py       import_excel.py
  desktop_call_provider conversation_manager   export_excel.py
  future_telephony      prompt_manager
  factory.py          speech/
                        audio_manager.py   ← all mic/speaker access
                        audio_player.py    ← pygame MP3 playback
                        speech_to_text.py  ← wrapper (STT)
                        text_to_speech.py  ← wrapper (edge-tts)
                        voice_activity.py
```

### Audio layer rule

**All microphone and speaker access goes through `speech/audio_manager.py`.**

- Recording: sounddevice → temp WAV (16 kHz mono)
- TTS: edge-tts → temp MP3 → AudioPlayer (pygame)
- STT: unchanged SpeechRecognition API; reads WAV from AudioManager
- Default voice: `en-IN-NeerjaNeural` (config: `TTS_VOICE`)
- No PyAudio or pyttsx3

### Critical design rule

**Only the call provider changes for telephony migration.**

- Factory: `providers/factory.py` reads `CALL_PROVIDER` from `.env`
- Business logic: `services/confirmation_service.py` calls `get_call_provider()` — never imports desktop/telephony directly
- Do NOT add telephony logic to scheduler, retry, AI, or database layers

---

## Import Convention

All imports are **root-relative** (project root is on PYTHONPATH):

```python
from config import get_settings
from models import Lecture, ConfirmationStatus
from services.confirmation_service import ConfirmationService
from providers.factory import get_call_provider
```

**Never** use `class_call_agent.` prefix — project was moved to flat root layout.

---

## Key Files — What to Edit For Common Tasks

| Task | Edit these files |
|------|------------------|
| Add/change API endpoint | `api/routes.py`, `api/schemas.py` |
| Change business/call flow | `services/confirmation_service.py` |
| Retry rules | `services/retry_service.py`, `config.py` |
| Gemini prompts / JSON schema | `ai/prompt_manager.py`, `ai/gemini_client.py` |
| Conversation state machine | `ai/conversation_manager.py`, `providers/desktop_call_provider.py` |
| Change speech / mic / TTS | `speech/audio_manager.py`, `speech/audio_player.py`, `speech/speech_to_text.py`, `speech/text_to_speech.py` |
| Scheduler timing | `scheduler.py`, `config.py` |
| Excel columns | `excel/import_excel.py`, `excel/export_excel.py` |
| DB schema | `models.py` → run init or migration |
| Add telephony | `providers/future_telephony_provider.py` only + `.env` |
| Env / settings | `config.py`, `.env` |
| CLI commands | `main.py` |

---

## Call Flow (End-to-End)

```
scheduler daily_schedule_job (5 PM)
  → ExcelImporter.import_file()
  → ConfirmationService.create_call_jobs_for_tomorrow()
  → ConfirmationService.process_call_queue()
      → execute_call(lecture_id)
          → get_call_provider().initiate_call(context)
          → [Desktop] STT → Gemini → TTS loop
          → update lecture confirmation status
          → LoggingService → DB + logs/*.json
          → on failure: RetryService.schedule_retry()

scheduler retry_check_job (every 1 min)
  → ConfirmationService.process_retries()
```

### Call state machine

```
PENDING → CALLING → LISTENING → THINKING → SPEAKING → WAITING → FINISHED
                                                          ↘ RETRY_PENDING
                                                          ↘ FAILED
```

States tracked in `CallState` enum (`models.py`) and `CallLog.current_state`.

---

## Gemini Integration

- **Model:** `gemini-2.5-flash` (config: `GEMINI_MODEL`)
- **Client:** `ai/gemini_client.py` — uses official `google-genai` SDK
- **JSON:** forced via `response_mime_type="application/json"` + schema; retries with backoff; safe fallback on failure
- **Prompts:** `ai/prompt_manager.py` — `SYSTEM_PROMPT` defines role, rules, JSON format
- **Manager:** `ai/conversation_manager.py` — turn history, state transitions

### Required JSON response from Gemini

```json
{
  "reply": "spoken text",
  "status": "Available|Unavailable|Late|Leave|Emergency|Substitute Requested|Pending",
  "delay_minutes": 0,
  "reason": "",
  "conversation_finished": false,
  "confidence": 0.95,
  "needs_delay_clarification": false
}
```

If teacher says "late" → ask delay minutes → set `conversation_finished: true`.

---

## Database (SQLite)

**Path:** `data/caller_agent.db` (via `config.resolved_database_url`)

| Table | Purpose |
|-------|---------|
| `teachers` | Faculty info (teacher_id, name, phone, department) |
| `lectures` | Schedule + confirmation fields (status, retry_count, transcript, etc.) |
| `call_queue` | Pending call jobs from daily scheduler |
| `retry_queue` | Scheduled retries with next_retry_time |
| `call_logs` | Full call records (duration, transcript, errors, summary) |
| `conversation_history` | Turn-by-turn messages per call |

**ORM:** SQLAlchemy 2.0 in `models.py`. Init: `python main.py init` or `database.init_db()`.

---

## Retry Logic

Triggered on: no response, STT failure, Gemini error, timeout, mic disconnect.

| Setting | Default |
|---------|---------|
| `MAX_RETRIES` | 3 |
| `RETRY_DELAY_MINUTES` | 10 |
| `CALL_TIMEOUT_SECONDS` | 120 |

After max retries → status `No Response`, stop retrying.

Implementation: `services/retry_service.py`

---

## Scheduler (APScheduler)

| Job | Trigger | Function |
|-----|---------|----------|
| Daily schedule | Cron 17:00 | `scheduler.daily_schedule_job` |
| Retry check | Every 60s | `scheduler.retry_check_job` |

Started in `app.py` lifespan via `start_scheduler()`.

---

## REST API

**Base:** `/api/v1` — routes in `api/routes.py`

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/teachers` | List teachers |
| GET | `/calls` | All lectures |
| GET | `/retry` | Pending retries |
| GET | `/logs` | Call logs |
| GET | `/status` | System status |
| GET | `/today`, `/tomorrow` | Lectures by date |
| POST | `/call/{teacher_id}` | Manual call |
| POST | `/retry/{teacher_id}` | Manual retry |
| POST | `/import` | Import Excel |
| POST | `/schedule/run` | Run daily job now |

**Docs:** `http://localhost:8000/docs`

---

## CLI Commands

```bash
python main.py init       # DB + import Excel
python main.py import     # Re-import Excel
python main.py export     # Export confirmations
python main.py schedule   # Run 5 PM job now
python main.py call T001  # Call one teacher
python main.py serve      # API only
python main.py run        # Scheduler + API
```

---

## Configuration (.env)

Key variables — full list in `.env.example`:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Required for AI |
| `CALL_PROVIDER` | `desktop` or `telephony` |
| `DAILY_SCHEDULE_HOUR/MINUTE` | Default 17:00 |
| `MAX_RETRIES`, `RETRY_DELAY_MINUTES` | Retry policy |
| `EXCEL_FILE_PATH` | `data/lecture_schedule.xlsx` |

Settings class: `config.py` → `get_settings()` (cached).

---

## Excel Format

**Import columns (required):** Teacher ID, Teacher Name, Phone Number, Department, Subject, Lecture Date, Lecture Time, Room

**Export adds:** Confirmation Status, Retry Count, Next Retry Time, Last Call Time, Teacher Response, Delay Minutes, Reason, Transcript, Conversation Finished

Sample generator: `python scripts/create_sample_excel.py`

---

## Code Conventions

- **Python 3.12+**, type hints, PEP8, async where needed (call provider)
- **Minimal diffs** — match existing patterns; don't over-engineer
- **No hardcoded secrets** — use `.env` via `config.py`
- **Repository pattern** — services take `Session`, no raw SQL in routes
- **Logging** — `logs/` JSON files + `call_logs` table via `LoggingService`
- **Tests** — `tests/` with pytest; run `pytest tests/ -v`

---

## Legacy Files (ignore unless asked)

These are from an older version — **do not modify** unless user requests cleanup:

`caller.py`, `voice_agent.py`, `excel_reader.py`, `excel_writer.py`, `llm.py`, `speech.py`, `webhook.py`, `notification.py`, `retry_manager.py`, `schema.sql`, `utils.py`

Active codebase uses the modular structure listed above.

---

## When Making Changes

1. **Read this skill first** — avoid full codebase exploration
2. Identify layer: API / service / provider / AI / speech / excel / scheduler
3. Follow provider abstraction for anything call-related
4. Update tests in `tests/` for service/API changes
5. Update `SETUP.md` if setup steps change
6. For deeper detail (full schema, test patterns), see [reference.md](reference.md)

---

## Quick Troubleshooting

| Issue | Check |
|-------|-------|
| Import errors | Run from project root; imports are root-relative |
| Gemini fails | `GEMINI_API_KEY` in `.env` |
| Mic not working | `sounddevice` installed; check `python -c "import sounddevice as sd; print(sd.query_devices())"` |
| No lectures to call | Excel dates must include tomorrow; run `init` |
| Scheduler not running | Use `python main.py run`, not `serve` alone |
