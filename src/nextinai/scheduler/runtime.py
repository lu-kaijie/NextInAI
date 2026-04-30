"""Runtime support for local delivery task execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import time
from typing import Any
from uuid import uuid4

from nextinai.core.datetime_utils import parse_datetime
from nextinai.harness.tools import DeliveryTaskStore
from nextinai.services.notification_service import AgenticNotificationService
from nextinai.storage.files import FileStorage, ensure_workspace
from nextinai.core.config import get_settings


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


@dataclass(slots=True)
class TaskRunResult:
    task_id: str
    status: str
    detail: str


@dataclass(slots=True)
class DaemonRunStats:
    cycles: int
    executed_tasks: int
    success_count: int
    failed_count: int
    suppressed_count: int


class DeliveryTaskScheduler:
    """Evaluate and execute persisted delivery tasks."""

    def __init__(
        self,
        *,
        storage: FileStorage | None = None,
        notification_service: AgenticNotificationService | None = None,
        task_store: DeliveryTaskStore | None = None,
    ) -> None:
        self.storage = storage or _build_storage()
        self.notification_service = notification_service or AgenticNotificationService(storage=self.storage)
        self.task_store = task_store or DeliveryTaskStore(self.storage)

    def list_tasks(self) -> list[dict[str, Any]]:
        return self.task_store.list_tasks()

    def run_due_tasks(self, *, now: datetime | None = None, force: bool = False) -> list[TaskRunResult]:
        now = now or datetime.now(timezone.utc)
        results: list[TaskRunResult] = []
        run_id = str(uuid4())
        for task in self.task_store.list_tasks():
            if not task.get("enabled", True):
                continue
            if not force and not self._is_due(task, now):
                continue
            try:
                detail = self.notification_service.send(
                    channel=task["channel"],
                    content_kind="digest",
                    scope=task.get("scope", "daily"),
                    briefing_view=task.get("view", "flash"),
                    suppress_duplicates=True,
                    target=self._resolve_target(task),
                )
                status = "suppressed" if "通知已抑制" in detail else "success"
                self._mark_task_run(task["task_id"], now, status=status)
                results.append(TaskRunResult(task_id=task["task_id"], status=status, detail=detail))
            except Exception as exc:
                self._mark_task_run(task["task_id"], now, status="failed", error=str(exc))
                results.append(TaskRunResult(task_id=task["task_id"], status="failed", detail=str(exc)))
        self._record_scheduler_run(run_id=run_id, now=now, force=force, results=results)
        return results

    def run_loop(
        self,
        *,
        poll_seconds: int = 60,
        max_cycles: int | None = None,
        force_first_cycle: bool = False,
    ) -> DaemonRunStats:
        cycles = 0
        executed_tasks = 0
        success_count = 0
        failed_count = 0
        suppressed_count = 0
        while True:
            cycles += 1
            results = self.run_due_tasks(force=force_first_cycle and cycles == 1)
            executed_tasks += len(results)
            success_count += sum(1 for item in results if item.status == "success")
            failed_count += sum(1 for item in results if item.status == "failed")
            suppressed_count += sum(1 for item in results if item.status == "suppressed")
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(max(1, poll_seconds))
        return DaemonRunStats(
            cycles=cycles,
            executed_tasks=executed_tasks,
            success_count=success_count,
            failed_count=failed_count,
            suppressed_count=suppressed_count,
        )

    @staticmethod
    def _is_due(task: dict[str, Any], now: datetime) -> bool:
        metadata = task.get("metadata") or {}
        next_retry_at = metadata.get("next_retry_at")
        if next_retry_at:
            retry_time = parse_datetime(next_retry_at)
            return now >= retry_time
        schedule = str(task.get("schedule") or "daily").lower()
        last_run_at = task.get("last_run_at")
        if not last_run_at:
            return True
        last_run = parse_datetime(last_run_at)
        interval = timedelta(days=1)
        if schedule == "hourly":
            interval = timedelta(hours=1)
        elif schedule == "weekly":
            interval = timedelta(days=7)
        return now >= last_run + interval

    def _mark_task_run(self, task_id: str, now: datetime, status: str, error: str | None = None) -> None:
        rows = self.storage.load_collection("delivery_tasks")
        deliveries = self.storage.load_collection("deliveries")
        last_delivery_id = deliveries[-1]["delivery_id"] if deliveries else None
        for row in rows:
            if row.get("task_id") == task_id:
                row["last_run_at"] = now.astimezone(timezone.utc).isoformat()
                row["last_delivery_id"] = last_delivery_id
                row["updated_at"] = now.astimezone(timezone.utc).isoformat()
                row.setdefault("metadata", {})
                if error:
                    row["metadata"]["last_error"] = error
                    consecutive_failures = int(row["metadata"].get("consecutive_failures", 0)) + 1
                    row["metadata"]["consecutive_failures"] = consecutive_failures
                    retry_minutes = min(60, 15 * consecutive_failures)
                    row["metadata"]["next_retry_at"] = (
                        now.astimezone(timezone.utc) + timedelta(minutes=retry_minutes)
                    ).isoformat()
                else:
                    row["metadata"].pop("last_error", None)
                    row["metadata"]["consecutive_failures"] = 0
                    row["metadata"].pop("next_retry_at", None)
                    row["metadata"]["last_status"] = status
                break
        self.storage.save_collection("delivery_tasks", rows)

    def _record_scheduler_run(
        self,
        *,
        run_id: str,
        now: datetime,
        force: bool,
        results: list[TaskRunResult],
    ) -> None:
        rows = self.storage.load_collection("job_runs")
        rows.append(
            {
                "run_id": run_id,
                "trigger_type": "schedule",
                "session_id": None,
                "actor_id": "system",
                "intent": "execute_delivery_tasks",
                "user_input": None,
                "tool_calls": [],
                "output_message": f"executed={len(results)}",
                "status": "success" if all(item.status != "failed" for item in results) else "failed",
                "error": None if all(item.status != "failed" for item in results) else "scheduler_task_failure",
                "metadata": {
                    "force": force,
                    "task_results": [asdict(item) for item in results],
                },
                "created_at": now.astimezone(timezone.utc).isoformat(),
                "finished_at": now.astimezone(timezone.utc).isoformat(),
            }
        )
        self.storage.save_collection("job_runs", rows)

    @staticmethod
    def _resolve_target(task: dict[str, Any]) -> str | None:
        target = task.get("target")
        if target in {None, "", "default"}:
            return None
        return str(target)
