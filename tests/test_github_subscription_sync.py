from datetime import datetime, timezone

from nextinai.collectors.github import GitHubCollectedItem
from nextinai.domain.enums import EventSignal
from nextinai.services.github_subscriptions import GitHubSubscriptionService
from nextinai.storage.files import FileStorage


class FakeCollector:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def collect_repository_updates(self, repository: str, since: datetime):
        self.calls.append((repository, since))
        return self.items


def test_sync_subscriptions_persists_items_and_checkpoint(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "subscriptions",
        [{"repository": "openai/gpt-oss", "lookback_hours": 24, "refresh_minutes": 60}],
    )
    collector = FakeCollector(
        [
            GitHubCollectedItem(
                signal_type=EventSignal.RELEASE,
                external_id="release:1",
                title="v1.0.0",
                url="https://github.com/openai/gpt-oss/releases/tag/v1.0.0",
                published_at=datetime.now(timezone.utc).isoformat(),
                summary_text="first release",
                metadata_json={"tag_name": "v1.0.0"},
            )
        ]
    )
    service = GitHubSubscriptionService(storage=storage, collector=collector)

    result = service.sync_subscriptions()

    items = storage.load_collection("content_items")
    checkpoints = storage.load_collection("checkpoints")
    assert result["new_items"] == 1
    assert result["synced_repositories"] == ["openai/gpt-oss"]
    assert items[0]["signal_type"] == "release"
    assert checkpoints[0]["source_key"] == "openai/gpt-oss"
    assert checkpoints[0]["failure_count"] == 0


def test_sync_subscriptions_deduplicates_existing_items(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "subscriptions",
        [{"repository": "openai/gpt-oss", "lookback_hours": 24, "refresh_minutes": 60}],
    )
    published_at = datetime.now(timezone.utc).isoformat()
    item = GitHubCollectedItem(
        signal_type=EventSignal.COMMIT,
        external_id="commit:abc123",
        title="fix bug",
        url="https://github.com/openai/gpt-oss/commit/abc123",
        published_at=published_at,
        summary_text="fix bug",
        metadata_json={},
    )
    collector = FakeCollector([item])
    service = GitHubSubscriptionService(storage=storage, collector=collector)

    first = service.sync_subscriptions()
    second = service.sync_subscriptions()

    assert first["new_items"] == 1
    assert second["new_items"] == 0
    assert len(storage.load_collection("content_items")) == 1
