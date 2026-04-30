"""Datetime parsing helpers."""

from __future__ import annotations

from datetime import datetime


def parse_datetime(value: str) -> datetime:
    """Parse ISO datetime strings and normalize trailing Z to UTC offset."""

    return datetime.fromisoformat(value.replace("Z", "+00:00"))
