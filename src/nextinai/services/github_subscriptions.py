"""GitHub subscription service backed by local JSON storage."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from nextinai.agents import IntelligenceAgent, OpenAIIntelligenceAgent, RuleBasedIntelligenceAgent
from nextinai.collectors.github import GitHubCollectedItem, GitHubRepositoryCollector
from nextinai.core.datetime_utils import parse_datetime
from nextinai.core.config import get_settings
from nextinai.domain.enums import SourceKind
from nextinai.services.contracts import SubscriptionRecord, SubscriptionService
from nextinai.storage.files import FileStorage, ensure_workspace
from nextinai.storage.state import CheckpointState


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


def validate_repository(repository: str) -> str:
    normalized = repository.strip().lower()
    if normalized.count("/") != 1:
        raise ValueError("仓库格式必须是 owner/name。")

    owner, name = normalized.split("/", maxsplit=1)
    if not owner or not name:
        raise ValueError("仓库格式必须是 owner/name。")
    return normalized


class GitHubSubscriptionService(SubscriptionService):
    """Manage subscriptions and incremental sync for GitHub repositories."""

    def __init__(
        self,
        storage: FileStorage | None = None,
        collector: GitHubRepositoryCollector | None = None,
        agent: IntelligenceAgent | None = None,
    ) -> None:
        settings = get_settings()
        self.storage = storage or _build_storage()
        self.collector = collector or GitHubRepositoryCollector(token=settings.github_token)
        if agent is not None:
            self.agent = agent
        elif settings.ai_provider == "openai" and settings.openai_api_key:
            self.agent = OpenAIIntelligenceAgent(
                settings.openai_api_key,
                settings.ai_model,
                settings.openai_base_url,
            )
        else:
            self.agent = RuleBasedIntelligenceAgent()

    def add_subscription(self, repository: str, lookback_hours: int, refresh_minutes: int) -> str:
        normalized = validate_repository(repository)
        rows = self.storage.load_collection("subscriptions")
        if any(item["repository"] == normalized for item in rows):
            return normalized

        record = SubscriptionRecord(
            repository=normalized,
            lookback_hours=lookback_hours,
            refresh_minutes=refresh_minutes,
        )
        rows.append(
            {
                "repository": record.repository,
                "lookback_hours": record.lookback_hours,
                "refresh_minutes": record.refresh_minutes,
            }
        )
        self.storage.save_collection("subscriptions", rows)
        return normalized

    def list_subscriptions(self) -> list[dict[str, int | str]]:
        return self.storage.load_collection("subscriptions")

    def sync_subscriptions(self, repository: str | None = None) -> dict[str, int | list[str]]:
        subscriptions = self._resolve_subscriptions(repository)
        synced: list[str] = []
        no_updates: list[str] = []
        failed: list[str] = []
        created_items = 0
        checkpoints = self.storage.load_collection("checkpoints")
        content_items = self.storage.load_collection("content_items")
        content_index = {item["dedupe_fingerprint"] for item in content_items}

        for subscription in subscriptions:
            repo = subscription["repository"]
            checkpoint = self._get_checkpoint(checkpoints, repo)
            since = self._resolve_since(subscription, checkpoint)
            try:
                collected = self._collect_with_retry(repo, since)
            except Exception as exc:
                self._mark_checkpoint_failure(checkpoints, checkpoint, str(exc))
                failed.append(repo)
                continue

            new_items = self._append_content_items(content_items, content_index, repo, collected)
            created_items += new_items
            synced.append(repo)
            if new_items == 0:
                no_updates.append(repo)
            self._mark_checkpoint_success(checkpoints, checkpoint)

        self.storage.save_collection("checkpoints", checkpoints)
        self.storage.save_collection("content_items", content_items)
        return {
            "synced_repositories": synced,
            "no_update_repositories": no_updates,
            "failed_repositories": failed,
            "new_items": created_items,
        }

    def summarize_repository(self, repository: str, hours: int = 24) -> str:
        normalized = validate_repository(repository)
        window_start = datetime.now(timezone.utc) - timedelta(hours=hours)
        content_items = self.storage.load_collection("content_items")
        repo_items = [
            item
            for item in content_items
            if item["source_key"] == normalized and self._is_in_window(item.get("published_at"), window_start)
        ]
        return self.agent.summarize_repository_updates(
            repository=normalized,
            hours=hours,
            items=repo_items,
        )

    def _resolve_subscriptions(self, repository: str | None) -> list[dict[str, Any]]:
        subscriptions = self.storage.load_collection("subscriptions")
        if repository is None:
            return subscriptions

        normalized = validate_repository(repository)
        rows = [item for item in subscriptions if item["repository"] == normalized]
        if not rows:
            raise ValueError(f"未找到订阅仓库：{normalized}")
        return rows

    def _get_checkpoint(self, checkpoints: list[dict[str, Any]], repository: str) -> dict[str, Any]:
        for checkpoint in checkpoints:
            if checkpoint["source_key"] == repository:
                return checkpoint

        state = CheckpointState(source_key=repository, cursor=None)
        checkpoint = state.to_dict()
        checkpoints.append(checkpoint)
        return checkpoint

    @staticmethod
    def _resolve_since(subscription: dict[str, Any], checkpoint: dict[str, Any]) -> datetime:
        last_success_at = checkpoint.get("last_success_at")
        if last_success_at:
            return parse_datetime(last_success_at)
        return datetime.now(timezone.utc) - timedelta(hours=int(subscription["lookback_hours"]))

    @staticmethod
    def _is_in_window(value: str | None, window_start: datetime) -> bool:
        if not value:
            return False
        return parse_datetime(value) >= window_start

    @staticmethod
    def _append_content_items(
        content_items: list[dict[str, Any]],
        content_index: set[str],
        repository: str,
        collected: list[GitHubCollectedItem],
    ) -> int:
        new_items = 0
        for item in collected:
            fingerprint = hashlib.sha256(
                f"{repository}|{item.signal_type.value}|{item.external_id}|{item.url}".encode("utf-8")
            ).hexdigest()
            if fingerprint in content_index:
                continue
            content_items.append(
                {
                    "source_kind": SourceKind.GITHUB_REPOSITORY.value,
                    "source_key": repository,
                    "signal_type": item.signal_type.value,
                    "title": item.title,
                    "url": item.url,
                    "external_id": item.external_id,
                    "published_at": item.published_at,
                    "summary_text": item.summary_text,
                    "metadata_json": item.metadata_json,
                    "dedupe_fingerprint": fingerprint,
                }
            )
            content_index.add(fingerprint)
            new_items += 1
        return new_items

    def _collect_with_retry(self, repository: str, since: datetime) -> list[GitHubCollectedItem]:
        last_error: Exception | None = None
        for _attempt in range(3):
            try:
                return self.collector.collect_repository_updates(repository, since)
            except httpx.HTTPError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        return []

    @staticmethod
    def _mark_checkpoint_success(checkpoints: list[dict[str, Any]], checkpoint: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        checkpoint["last_collected_at"] = now
        checkpoint["last_success_at"] = now
        checkpoint["last_failure_at"] = None
        checkpoint["failure_count"] = 0
        checkpoint["last_error"] = None
        checkpoint["cursor"] = now

    @staticmethod
    def _mark_checkpoint_failure(
        checkpoints: list[dict[str, Any]], checkpoint: dict[str, Any], error_text: str
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        checkpoint["last_collected_at"] = now
        checkpoint["last_failure_at"] = now
        checkpoint["failure_count"] = int(checkpoint.get("failure_count", 0)) + 1
        checkpoint["last_error"] = error_text
