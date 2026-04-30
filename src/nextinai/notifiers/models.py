"""Notification message and delivery models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nextinai.domain.enums import DeliveryChannel, DeliveryStatus


@dataclass(slots=True)
class NotificationTarget:
    channel: DeliveryChannel
    destination: str


@dataclass(slots=True)
class NotificationMessage:
    content_kind: str
    content_ref: str
    title: str
    body: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DeliveryAttempt:
    attempt_number: int
    status: DeliveryStatus
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "status": self.status.value,
            "detail": self.detail,
        }


@dataclass(slots=True)
class DeliveryResult:
    channel: DeliveryChannel
    target: str
    status: DeliveryStatus
    detail: str
    attempts: list[DeliveryAttempt] = field(default_factory=list)

