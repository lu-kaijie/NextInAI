"""Local JSON file storage for personal-use mode."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nextinai.core.config import Settings

DEFAULT_COLLECTIONS = {
    "subscriptions": [],
    "checkpoints": [],
    "content_items": [],
    "analysis_results": [],
    "deep_report_readings": [],
    "report_excerpt_translations": [],
    "report_skips": [],
    "events": [],
    "session_states": [],
    "delivery_tasks": [],
    "digests": [],
    "deliveries": [],
    "job_runs": [],
}


def ensure_workspace(settings: Settings) -> None:
    """Create data and artifact directories with default files."""

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for name, default_value in DEFAULT_COLLECTIONS.items():
        path = settings.data_dir / f"{name}.json"
        if not path.exists():
            path.write_text(json.dumps(default_value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class FileStorage:
    """Small helper around JSON collections stored on disk."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path_for(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def load_collection(self, name: str) -> list[dict[str, Any]]:
        path = self._path_for(name)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def save_collection(self, name: str, records: list[dict[str, Any]]) -> None:
        path = self._path_for(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
