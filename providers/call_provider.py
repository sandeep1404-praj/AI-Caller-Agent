"""Abstract call provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CallResultStatus(str, Enum):
    SUCCESS = "success"
    NO_RESPONSE = "no_response"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRY = "retry"


@dataclass
class CallContext:
    """Context passed to call providers for a single call session."""

    teacher_id: str
    teacher_name: str
    phone_number: str
    department: str
    subject: str
    lecture_date: str
    lecture_time: str
    room: str
    call_log_id: int | None = None


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""

    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CallResult:
    """Result returned by a call provider after a conversation."""

    status: CallResultStatus
    confirmation_status: str
    delay_minutes: int = 0
    reason: str = ""
    transcript: str = ""
    conversation_finished: bool = False
    turns: list[ConversationTurn] = field(default_factory=list)
    gemini_responses: list[str] = field(default_factory=list)
    error_message: str | None = None
    duration_seconds: int = 0


class CallProvider(ABC):
    """Abstract base class for call providers (desktop or telephony)."""

    @abstractmethod
    async def initiate_call(self, context: CallContext) -> CallResult:
        """Initiate and conduct a call with the teacher."""
        ...

    @abstractmethod
    async def hang_up(self) -> None:
        """End the current call."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the call provider is ready."""
        ...
