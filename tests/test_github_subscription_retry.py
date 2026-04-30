import httpx
from datetime import datetime, timezone

from nextinai.collectors.github import GitHubCollectedItem
from nextinai.domain.enums import EventSignal
from nextinai.services.github_subscriptions import GitHubSubscriptionService
from nextinai.storage.files import FileStorage


class FlakyCollector:
    def __init__(self, failures_before_success: int, items):
        self.failures_before_success = failures_before_success
        self.items = items
        self.calls = 0

    def collect_repository_updates(self, repository: str, since: datetime):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise httpx.ReadTimeout("timeout")
        return self.items


class AlwaysFailCollector:
    def collect_repository_updates(self, repository: str, since: datetime):
        raise httpx.ConnectError("boom")


def test_sync_retries_transient_failures(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "subscriptions",
        [{"repository": "openai/gpt-oss", "lookback_hours": 24, "refresh_minutes": 60}],
    )
    collector = FlakyCollector(
        2,
        [
            GitHubCollectedItem(
                signal_type=EventSignal.COMMIT,
                external_id="commit:ok",
                title="Improve parser",
                url="https://example.com/commit/ok",
                published_at=datetime.now(timezone.utc).isoformat(),
                summary_text="improve parser",
                metadata_json={},
            )
        ],
    )
    service = GitHubSubscriptionService(storage=storage, collector=collector)

    result = service.sync_subscriptions()

    assert collector.calls == 3
    assert result["failed_repositories"] == []
    assert result["new_items"] == 1


def test_sync_records_failure_after_retry_exhausted(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "subscriptions",
        [{"repository": "openai/gpt-oss", "lookback_hours": 24, "refresh_minutes": 60}],
    )
    service = GitHubSubscriptionService(storage=storage, collector=AlwaysFailCollector())

    result = service.sync_subscriptions()
    checkpoints = storage.load_collection("checkpoints")

    assert result["failed_repositories"] == ["openai/gpt-oss"]
    assert checkpoints[0]["failure_count"] == 1
    assert checkpoints[0]["last_error"]
