"""Task store shared by web, capabilities, and harness tools."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from nextinai.core.config import get_settings
from nextinai.harness.models import DeliveryTask
from nextinai.storage.files import FileStorage, ensure_workspace


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


class DeliveryTaskStore:
    """Manage delivery task records on top of file storage."""

    def __init__(self, storage: FileStorage | None = None) -> None:
        self.storage = storage or _build_storage()

    def list_tasks(self) -> list[dict[str, Any]]:
        return self.storage.load_collection("delivery_tasks")

    def create_task(self, *, channel: str, target: str, scope: str, view: str, schedule: str | None) -> DeliveryTask:
        task = DeliveryTask(
            task_id=str(uuid4()),
            channel=channel,
            target=target,
            scope=scope,
            view=view,
            schedule=schedule,
        )
        rows = self.storage.load_collection("delivery_tasks")
        rows.append(task.to_dict())
        self.storage.save_collection("delivery_tasks", rows)
        return task

    def delete_task(self, task_id: str) -> bool:
        rows = self.storage.load_collection("delivery_tasks")
        remaining = [row for row in rows if row.get("task_id") != task_id]
        deleted = len(remaining) != len(rows)
        if deleted:
            self.storage.save_collection("delivery_tasks", remaining)
        return deleted

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        for row in self.storage.load_collection("delivery_tasks"):
            if row.get("task_id") == task_id:
                return row
        return None
