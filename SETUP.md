# Class Call Agent — Setup Guide

Follow these steps to install, configure, and run the project on your machine.

**Project folder:** `C:\Users\praja\Desktop\Caller agent`

---

## 1. Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Python 3.12+** | Works on Windows, Linux, and macOS |
| **Microphone & speakers** | Required for the desktop call simulator |
| **Internet** | Required for Gemini API, Google STT, and edge-tts |
| **Gemini API key** | Free key from [Google AI Studio](https://aistudio.google.com/apikey) |

Check Python:

```powershell
python --version
```

---

## 2. Open the project folder

```powershell
cd "C:\Users\praja\Desktop\Caller agent"
```

---

## 3. Create & activate virtual environment

If `.venv` already exists, skip the create step.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

You should see `(.venv)` in your terminal prompt.

---

## 4. Install dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

**Verify audio devices:**

```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Audio stack: **sounddevice** (mic), **edge-tts** (speech), **pygame** or **miniaudio** (playback). No PyAudio required.

---

## 5. Configure environment variables

Copy the example env file:

```powershell
copy .env.example .env
```

Open `.env` in a text editor and set your Gemini key:

```env
GEMINI_API_KEY=your_actual_api_key_here
```

Other useful defaults (already set in `.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `CALL_PROVIDER` | `desktop` | Use microphone/speaker simulator |
| `DAILY_SCHEDULE_HOUR` | `17` | Daily job runs at 5:00 PM |
| `API_PORT` | `8000` | REST API port |
| `EXCEL_FILE_PATH` | `data/lecture_schedule.xlsx` | Schedule file location |

---

## 6. Create sample Excel schedule

```powershell
python scripts/create_sample_excel.py
```

This creates `data/lecture_schedule.xlsx` with 5 sample teachers scheduled for **tomorrow**.

---

## 7. Initialize the database

```powershell
python main.py init
```

This will:

- Create `data/caller_agent.db` (SQLite)
- Import teachers and lectures from the Excel file
- Create the `logs/` folder

Expected output:

```
Database initialized at sqlite:///...
Imported 5 rows from Excel
```

---

## 8. Run the application

### Full app (scheduler + API) — recommended

```powershell
python main.py run
```

- Scheduler runs daily at **5:00 PM** and checks retries every **1 minute**
- API available at: **http://localhost:8000**
- Interactive docs: **http://localhost:8000/docs**

### API server only

```powershell
python main.py serve
```

---

## 9. Test a call manually

With the app running (or in a second terminal with venv activated):

```powershell
python main.py call T001
```

What happens:

1. Terminal shows: `Calling Professor Amit Sharma...`
2. AI speaks the greeting through your **speakers**
3. App listens via **microphone**
4. You respond (e.g. "Yes, I will be available")
5. Gemini processes your reply and the conversation continues
6. Results saved to database and `logs/`

Other sample teacher IDs: `T002`, `T003`, `T004`, `T005`

---

## 10. Useful CLI commands

| Command | What it does |
|---------|--------------|
| `python main.py init` | Create DB + import Excel |
| `python main.py import` | Re-import Excel schedule |
| `python main.py export` | Export confirmations to Excel |
| `python main.py schedule` | Run the 5 PM job immediately (for testing) |
| `python main.py call T001` | Call one teacher now |
| `python main.py serve` | Start API only |
| `python main.py run` | Start scheduler + API |

---

## 11. REST API quick reference

Base URL: `http://localhost:8000/api/v1`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | System status |
| GET | `/teachers` | List teachers |
| GET | `/tomorrow` | Tomorrow's lectures |
| GET | `/today` | Today's lectures |
| GET | `/calls` | All lectures with status |
| GET | `/retry` | Pending retries |
| GET | `/logs` | Call logs |
| POST | `/call/{teacher_id}` | Trigger a call |
| POST | `/retry/{teacher_id}` | Trigger a retry |
| POST | `/import` | Import Excel |
| POST | `/schedule/run` | Run daily schedule now |

**Examples (PowerShell):**

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/status
Invoke-RestMethod http://localhost:8000/api/v1/tomorrow
Invoke-RestMethod -Method POST http://localhost:8000/api/v1/call/T001
```

Or open **http://localhost:8000/docs** and try endpoints in the browser.

---

## 12. Run tests

```powershell
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

---

## 13. Daily workflow (automatic)

Once `python main.py run` is active:

| Time | What happens |
|------|--------------|
| **5:00 PM daily** | Reads Excel → finds tomorrow's lectures → creates call jobs → calls each teacher |
| **Every 1 minute** | Checks retry queue and retries failed calls (max 3 retries, 10 min apart) |

After calls complete, confirmation status is written back to Excel via export.

---

## 14. Troubleshooting

### `ModuleNotFoundError` (fastapi, pydantic, etc.)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### `GEMINI_API_KEY is not set`

Edit `.env` and add your key, then restart the app.

### Microphone not working

- Check audio devices: `python -c "import sounddevice as sd; print(sd.query_devices())"`
- Check Windows microphone permissions: **Settings → Privacy → Microphone**
- Ensure `sounddevice` installed: `pip install sounddevice soundfile`

### `Excel file not found`

```powershell
python scripts/create_sample_excel.py
python main.py init
```

### Speech not recognized

- Speak clearly after the AI finishes talking
- Reduce background noise
- Ensure internet is connected (Google STT is used by default)

### Port 8000 already in use

Change in `.env`:

```env
API_PORT=8001
```

### Call times out

Default call timeout is 2 minutes. Increase in `.env`:

```env
CALL_TIMEOUT_SECONDS=180
```

---

## 15. Quick start (copy-paste)

Run everything in order:

```powershell
cd "C:\Users\praja\Desktop\Caller agent"
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` → set `GEMINI_API_KEY`, then:

```powershell
python scripts/create_sample_excel.py
python main.py init
python main.py run
```

In another terminal:

```powershell
cd "C:\Users\praja\Desktop\Caller agent"
.\.venv\Scripts\Activate.ps1
python main.py call T001
```

---

## 16. Project structure

```
Caller agent/
├── main.py              ← CLI entry point
├── app.py               ← FastAPI app
├── config.py            ← Settings (.env)
├── data/                ← Excel + SQLite DB
├── logs/                ← Call log JSON files
├── scripts/             ← Sample Excel generator
├── services/            ← Business logic
├── providers/           ← Desktop call simulator
├── ai/                  ← Gemini integration
├── speech/              ← STT / TTS
├── api/                 ← REST routes
├── .env                 ← Your secrets (create from .env.example)
└── requirements.txt
```

---

## Need help?

1. Check logs in the `logs/` folder
2. Hit `GET /api/v1/status` for system state
3. Run `python main.py schedule` to test the daily job without waiting until 5 PM
