PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS teachers (
    teacher_id TEXT PRIMARY KEY,
    teacher_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    department TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lectures (
    lecture_id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL,
    teacher_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    department TEXT NOT NULL,
    subject TEXT NOT NULL,
    lecture_date TEXT NOT NULL,
    lecture_time TEXT NOT NULL,
    room TEXT,
    source_row INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(teacher_id, subject, lecture_date, lecture_time, room)
);

CREATE TABLE IF NOT EXISTS call_queue (
    lecture_id TEXT PRIMARY KEY,
    teacher_id TEXT NOT NULL,
    teacher_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    department TEXT NOT NULL,
    subject TEXT NOT NULL,
    lecture_date TEXT NOT NULL,
    lecture_time TEXT NOT NULL,
    room TEXT,
    call_status TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_call_time TEXT,
    teacher_response TEXT,
    delay_minutes INTEGER NOT NULL DEFAULT 0,
    call_attempts INTEGER NOT NULL DEFAULT 0,
    last_call_time TEXT,
    conversation_transcript TEXT,
    reason TEXT,
    call_duration_seconds INTEGER NOT NULL DEFAULT 0,
    call_sid TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id TEXT NOT NULL,
    teacher_id TEXT NOT NULL,
    teacher_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    department TEXT NOT NULL,
    subject TEXT NOT NULL,
    lecture_date TEXT NOT NULL,
    lecture_time TEXT NOT NULL,
    room TEXT,
    attempt_number INTEGER NOT NULL,
    call_sid TEXT,
    call_started_at TEXT,
    call_ended_at TEXT,
    call_duration_seconds INTEGER NOT NULL DEFAULT 0,
    call_status TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_call_time TEXT,
    teacher_response TEXT,
    delay_minutes INTEGER NOT NULL DEFAULT 0,
    conversation_transcript TEXT,
    reason TEXT,
    decision_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS retry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lecture_id TEXT NOT NULL,
    teacher_id TEXT NOT NULL,
    teacher_name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    department TEXT NOT NULL,
    subject TEXT NOT NULL,
    lecture_date TEXT NOT NULL,
    lecture_time TEXT NOT NULL,
    room TEXT,
    attempt_number INTEGER NOT NULL,
    retry_count INTEGER NOT NULL,
    next_call_time TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lecture_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_retry_queue_due ON retry_queue(status, next_call_time);
CREATE INDEX IF NOT EXISTS idx_call_queue_status ON call_queue(call_status, next_call_time);
CREATE INDEX IF NOT EXISTS idx_call_logs_lecture ON call_logs(lecture_id, attempt_number);
