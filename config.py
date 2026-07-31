"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for Class Call Agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Class Call Agent"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: Literal["development", "production", "testing"] = "development"

    # Paths
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent)
    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "data")
    logs_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent / "logs")

    # Database
    database_url: str = ""

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        db_path = self.data_dir / "caller_agent.db"
        return f"sqlite:///{db_path.as_posix()}"

    # Gemini AI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.3
    gemini_max_tokens: int = 1024

    # Call provider — swap this single value to migrate to telephony
    call_provider: Literal["desktop", "telephony"] = "desktop"

    # Scheduler
    daily_schedule_hour: int = 17
    daily_schedule_minute: int = 0
    retry_check_interval_seconds: int = 60

    # Retry logic
    max_retries: int = 3
    retry_delay_minutes: int = 10

    # Call settings
    call_timeout_seconds: int = 120
    speech_listen_timeout_seconds: int = 15
    speech_phrase_limit_seconds: int = 30
    silence_threshold: float = 0.01
    silence_duration_seconds: float = 1.5

    # Excel
    excel_file_path: str = "data/lecture_schedule.xlsx"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # TTS (edge-tts)
    tts_voice: str = "en-IN-NeerjaNeural"

    def ensure_directories(self) -> None:
        """Create required directories if they do not exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
