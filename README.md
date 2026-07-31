# Class Call Agent

AI-powered lecture confirmation system for colleges. Automatically calls faculty members to confirm their availability for scheduled lectures using Google Gemini 2.5 Flash.

> **New here?** Start with **[SETUP.md](SETUP.md)** for step-by-step install and run instructions.
> **For AI assistants:** Project context skill at `.cursor/skills/class-call-agent/SKILL.md`

**Development mode** uses a Desktop Call Simulator (microphone + speakers). **Production mode** will swap in a telephony provider with a single config change.

---

## Features

- Daily automated calling at 5:00 PM for tomorrow's lectures
- Desktop Call Simulator (microphone/speaker-based, no telephony costs)
- Google Gemini 2.5 Flash for natural conversation and response classification
- Speech-to-Text and Text-to-Speech integration
- SQLite database with full call logging
- Excel import/export for lecture schedules
- Automatic retry logic (max 3 retries, 10-minute intervals)
- Call state machine (PENDING → CALLING → LISTENING → THINKING → SPEAKING → FINISHED)
- FastAPI REST dashboard
- APScheduler background jobs
- Clean Architecture — swap call provider via one config line

---

## Architecture

```
Caller agent/
├── app.py                  # FastAPI application
├── config.py               # Environment configuration
├── database.py             # SQLAlchemy setup
├── models.py               # ORM models
├── scheduler.py            # APScheduler jobs
├── main.py                 # CLI entry point
├── services/               # Business logic
│   ├── teacher_service.py
│   ├── lecture_service.py
│   ├── confirmation_service.py
│   ├── retry_service.py
│   └── logging_service.py
├── providers/              # Call provider abstraction
│   ├── call_provider.py          # Abstract interface
│   ├── desktop_call_provider.py  # Development simulator
│   ├── future_telephony_provider.py  # Future Twilio/Exotel stub
│   └── factory.py                # Provider factory
├── speech/                 # Voice I/O
│   ├── speech_to_text.py
│   ├── text_to_speech.py
│   ├── audio_manager.py
│   ├── audio_player.py
│   └── voice_activity.py
├── ai/                     # Gemini integration
│   ├── gemini_client.py
│   ├── conversation_manager.py
│   └── prompt_manager.py
├── excel/                  # Schedule I/O
│   ├── import_excel.py
│   └── export_excel.py
├── api/                    # REST API
│   ├── routes.py
│   └── schemas.py
├── tests/                  # Unit tests
├── data/                   # Excel schedules + SQLite DB
└── logs/                   # Call log files
```

### Future Telephony Migration

To switch from desktop simulator to real phone calls, change one line in `.env`:

```env
CALL_PROVIDER=telephony
```

Then implement `TelephonyCallProvider` in `providers/future_telephony_provider.py`. No scheduler, AI, retry, database, or business logic changes required.

---

## Prerequisites

- Python 3.12+
- Microphone and speakers (for desktop simulator)
- Google Gemini API key ([Get one free](https://aistudio.google.com/apikey))
- Internet connection (Gemini, Google STT, edge-tts)

---

## Setup

### 1. Clone and enter project

```bash
cd "Caller agent"
```

### 2. Create virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Audio uses **sounddevice** (recording), **edge-tts** (speech synthesis), and **pygame** or **miniaudio** (playback). No PyAudio or pyttsx3 required.

### 4. Configure environment

```bash
copy .env.example .env    # Windows
cp .env.example .env      # macOS/Linux
```

Edit `.env` and set your Gemini API key:

```env
GEMINI_API_KEY=your_actual_api_key_here
```

### 5. Generate sample Excel schedule

```bash
python scripts/create_sample_excel.py
```

### 6. Initialize database and import schedule

```bash
python main.py init
```

---

## Usage

### Start the full application (scheduler + API)

```bash
python main.py run
```

API available at: `http://localhost:8000`
API docs at: `http://localhost:8000/docs`

### CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py init` | Initialize DB and import Excel |
| `python main.py import` | Import Excel schedule |
| `python main.py export` | Export schedule with confirmations |
| `python main.py schedule` | Run daily schedule job now |
| `python main.py call T001` | Call a specific teacher |
| `python main.py serve` | Start API server only |
| `python main.py run` | Start scheduler + API |

### Manual call test

```bash
python main.py call T001
```

This opens the Desktop Call Simulator:
1. Displays "Calling Professor Amit..."
2. AI speaks the greeting through speakers
3. Listens via microphone
4. Processes response with Gemini
5. Continues until conversation is complete

---

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/teachers` | List all teachers |
| GET | `/api/v1/calls` | List all lectures/calls |
| GET | `/api/v1/retry` | List pending retries |
| POST | `/api/v1/call/{teacher_id}` | Trigger call for teacher |
| POST | `/api/v1/retry/{teacher_id}` | Trigger retry for teacher |
| GET | `/api/v1/logs` | List call logs |
| GET | `/api/v1/status` | System status |
| GET | `/api/v1/today` | Today's lectures |
| GET | `/api/v1/tomorrow` | Tomorrow's lectures |
| POST | `/api/v1/import` | Import Excel schedule |
| POST | `/api/v1/schedule/run` | Run daily schedule manually |

---

## Excel Format

| Column | Description |
|--------|-------------|
| Teacher ID | Unique identifier (e.g., T001) |
| Teacher Name | Full name |
| Phone Number | Contact number |
| Department | Department name |
| Subject | Lecture subject |
| Lecture Date | YYYY-MM-DD |
| Lecture Time | e.g., 10:00 AM |
| Room | Room number |
| Confirmation Status | Auto-updated |
| Retry Count | Auto-updated |
| Next Retry Time | Auto-updated |
| Last Call Time | Auto-updated |
| Teacher Response | Auto-updated |
| Delay Minutes | Auto-updated |
| Reason | Auto-updated |
| Transcript | Auto-updated |
| Conversation Finished | Auto-updated |

---

## Scheduler

| Job | Schedule | Action |
|-----|----------|--------|
| Daily Schedule | 5:00 PM daily | Import Excel, find tomorrow's lectures, create call jobs, process queue |
| Retry Check | Every 1 minute | Process due retries from retry_queue |

---

## Retry Logic

Retries are triggered when:
- Teacher gives no response
- Speech recognition fails
- Gemini returns an error
- Conversation times out
- Microphone disconnects

| Setting | Default |
|---------|---------|
| Max retries | 3 |
| Retry delay | 10 minutes |
| Call timeout | 2 minutes |

After 3 failed retries, status is set to **No Response**.

---

## Call State Machine

```
PENDING → CALLING → LISTENING → THINKING → SPEAKING → WAITING → FINISHED
                                                              ↘ RETRY_PENDING
                                                              ↘ FAILED
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Database Tables

- **teachers** — Faculty information
- **lectures** — Scheduled lectures with confirmation status
- **call_queue** — Pending call jobs
- **retry_queue** — Scheduled retries
- **call_logs** — Complete call records
- **conversation_history** — Turn-by-turn conversation

---

## Logging

Call logs are stored in:
- **Database** — `call_logs` and `conversation_history` tables
- **Files** — `logs/call_{id}_{timestamp}.json`

---

## License

MIT
