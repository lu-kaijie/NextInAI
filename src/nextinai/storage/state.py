"""File-backed state models used before introducing a database."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class CheckpointState:
    source_key: str
    cursor: str | None = None
    last_collected_at: str | None = None
    last_success_at: str | None = None
    last_failure_at: str | None = None
    failure_count: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class JobRunState:
    job_name: str
    run_key: str
    status: str = "pending"
    attempt: int = 1
    payload: dict[str, Any] = field(default_factory=dict)
    error_text: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
