from datetime import datetime, timedelta, timezone

from nextinai.harness.tools import DeliveryTaskStore
from nextinai.scheduler.runtime import DeliveryTaskScheduler
from nextinai.storage.files import FileStorage


class FakeNotificationService:
    def __init__(self, storage: FileStorage) -> None:
        self.storage = storage
        self.calls: list[dict] = []

    def send(self, **kwargs) -> str:
        self.calls.append(kwargs)
        deliveries = self.storage.load_collection("deliveries")
        deliveries.append(
            {
                "delivery_id": f"delivery-{len(deliveries) + 1}",
                "channel": kwargs["channel"],
                "target": kwargs.get("target") or "default",
                "status": "success",
            }
        )
        self.storage.save_collection("deliveries", deliveries)
        return f"sent:{kwargs['channel']}:{kwargs.get('briefing_view', 'flash')}"


def test_scheduler_runs_due_tasks_and_updates_state(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    task_store = DeliveryTaskStore(storage)
    task = task_store.create_task(
        channel="email",
        target="default",
        scope="daily",
        view="deep",
        schedule="daily",
    )
    scheduler = DeliveryTaskScheduler(
        storage=storage,
        notification_service=FakeNotificationService(storage),
        task_store=task_store,
    )

    results = scheduler.run_due_tasks(now=datetime.now(timezone.utc))

    rows = storage.load_collection("delivery_tasks")
    job_runs = storage.load_collection("job_runs")
    assert len(results) == 1
    assert results[0].status == "success"
    assert rows[0]["last_run_at"] is not None
    assert rows[0]["last_delivery_id"] == "delivery-1"
    assert job_runs[-1]["trigger_type"] == "schedule"


def test_scheduler_skips_not_due_tasks_unless_forced(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    task_store = DeliveryTaskStore(storage)
    task = task_store.create_task(
        channel="webhook",
        target="default",
        scope="daily",
        view="flash",
        schedule="daily",
    )
    rows = storage.load_collection("delivery_tasks")
    rows[0]["last_run_at"] = datetime.now(timezone.utc).isoformat()
    storage.save_collection("delivery_tasks", rows)
    fake_notification = FakeNotificationService(storage)
    scheduler = DeliveryTaskScheduler(
        storage=storage,
        notification_service=fake_notification,
        task_store=task_store,
    )

    normal_results = scheduler.run_due_tasks(now=datetime.now(timezone.utc) + timedelta(hours=1))
    forced_results = scheduler.run_due_tasks(now=datetime.now(timezone.utc) + timedelta(hours=1), force=True)

    assert normal_results == []
    assert len(forced_results) == 1
    assert fake_notification.calls[0]["briefing_view"] == "flash"


def test_scheduler_sets_retry_metadata_after_failure_and_honors_backoff(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    task_store = DeliveryTaskStore(storage)
    task_store.create_task(
        channel="email",
        target="default",
        scope="daily",
        view="flash",
        schedule="daily",
    )

    class FailingNotificationService:
        def send(self, **kwargs) -> str:
            raise RuntimeError("smtp down")

    scheduler = DeliveryTaskScheduler(
        storage=storage,
        notification_service=FailingNotificationService(),
        task_store=task_store,
    )
    now = datetime.now(timezone.utc)

    first = scheduler.run_due_tasks(now=now)
    second = scheduler.run_due_tasks(now=now + timedelta(minutes=5))
    third = scheduler.run_due_tasks(now=now + timedelta(minutes=20))

    rows = storage.load_collection("delivery_tasks")
    metadata = rows[0]["metadata"]
    assert first[0].status == "failed"
    assert second == []
    assert third[0].status == "failed"
    assert metadata["consecutive_failures"] >= 1
    assert metadata["next_retry_at"] is not None


def test_scheduler_run_loop_collects_stats(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    task_store = DeliveryTaskStore(storage)
    task_store.create_task(
        channel="email",
        target="default",
        scope="daily",
        view="flash",
        schedule="daily",
    )
    scheduler = DeliveryTaskScheduler(
        storage=storage,
        notification_service=FakeNotificationService(storage),
        task_store=task_store,
    )

    stats = scheduler.run_loop(poll_seconds=1, max_cycles=2, force_first_cycle=True)

    assert stats.cycles == 2
    assert stats.executed_tasks >= 1
