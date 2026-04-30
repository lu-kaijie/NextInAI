"""GitHub data collector for repository subscriptions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from nextinai.domain.enums import EventSignal


@dataclass(slots=True)
class GitHubCollectedItem:
    signal_type: EventSignal
    external_id: str
    title: str
    url: str
    published_at: str | None
    summary_text: str | None
    metadata_json: dict[str, Any]


class GitHubRepositoryCollector:
    """Collect recent repository changes from GitHub APIs."""

    def __init__(self, token: str | None = None, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "nextinai/0.2.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=20.0,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def collect_repository_updates(self, repository: str, since: datetime) -> list[GitHubCollectedItem]:
        items: list[GitHubCollectedItem] = []
        items.extend(self._collect_releases(repository, since))
        items.extend(self._collect_merged_pulls(repository, since))
        items.extend(self._collect_commits(repository, since))
        return sorted(items, key=lambda item: item.published_at or "", reverse=True)

    def _collect_releases(self, repository: str, since: datetime) -> list[GitHubCollectedItem]:
        response = self.client.get(f"/repos/{repository}/releases", params={"per_page": 20})
        response.raise_for_status()
        items: list[GitHubCollectedItem] = []
        for release in response.json():
            published_at = release.get("published_at") or release.get("created_at")
            if not self._is_new_enough(published_at, since):
                continue
            items.append(
                GitHubCollectedItem(
                    signal_type=EventSignal.RELEASE,
                    external_id=f"release:{release['id']}",
                    title=release.get("name") or release.get("tag_name") or "Untitled release",
                    url=release["html_url"],
                    published_at=published_at,
                    summary_text=release.get("body"),
                    metadata_json={
                        "tag_name": release.get("tag_name"),
                        "prerelease": release.get("prerelease", False),
                    },
                )
            )
        return items

    def _collect_merged_pulls(self, repository: str, since: datetime) -> list[GitHubCollectedItem]:
        response = self.client.get(
            f"/repos/{repository}/pulls",
            params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 30},
        )
        response.raise_for_status()
        items: list[GitHubCollectedItem] = []
        for pull in response.json():
            merged_at = pull.get("merged_at")
            if not merged_at or not self._is_new_enough(merged_at, since):
                continue
            items.append(
                GitHubCollectedItem(
                    signal_type=EventSignal.PULL_REQUEST,
                    external_id=f"pull:{pull['id']}",
                    title=pull["title"],
                    url=pull["html_url"],
                    published_at=merged_at,
                    summary_text=pull.get("body"),
                    metadata_json={
                        "number": pull.get("number"),
                        "author": (pull.get("user") or {}).get("login"),
                    },
                )
            )
        return items

    def _collect_commits(self, repository: str, since: datetime) -> list[GitHubCollectedItem]:
        response = self.client.get(
            f"/repos/{repository}/commits",
            params={"since": since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "per_page": 30},
        )
        response.raise_for_status()
        items: list[GitHubCollectedItem] = []
        for commit in response.json():
            commit_data = commit.get("commit", {})
            authored_at = ((commit_data.get("author") or {}).get("date")) or (
                (commit_data.get("committer") or {}).get("date")
            )
            if not self._is_new_enough(authored_at, since):
                continue
            sha = commit["sha"]
            message = commit_data.get("message", "").strip()
            items.append(
                GitHubCollectedItem(
                    signal_type=EventSignal.COMMIT,
                    external_id=f"commit:{sha}",
                    title=message.splitlines()[0] if message else sha[:12],
                    url=commit["html_url"],
                    published_at=authored_at,
                    summary_text=message,
                    metadata_json={
                        "sha": sha,
                        "author": ((commit_data.get("author") or {}).get("name")),
                    },
                )
            )
            documentation_item = self._collect_documentation_change(repository, sha, authored_at, commit["html_url"])
            if documentation_item is not None:
                items.append(documentation_item)
        return items

    def _collect_documentation_change(
        self, repository: str, sha: str, authored_at: str | None, fallback_url: str
    ) -> GitHubCollectedItem | None:
        response = self.client.get(f"/repos/{repository}/commits/{sha}")
        response.raise_for_status()
        payload = response.json()
        files = payload.get("files") or []
        doc_files = [item["filename"] for item in files if self._is_documentation_file(item.get("filename", ""))]
        if not doc_files:
            return None
        return GitHubCollectedItem(
            signal_type=EventSignal.DOCUMENTATION,
            external_id=f"documentation:{sha}",
            title=f"文档更新 {sha[:12]}",
            url=payload.get("html_url", fallback_url),
            published_at=authored_at,
            summary_text="; ".join(doc_files[:5]),
            metadata_json={"sha": sha, "files": doc_files},
        )

    @staticmethod
    def _is_documentation_file(path: str) -> bool:
        lowered = path.lower()
        return lowered.startswith("docs/") or lowered.endswith(".md") or "readme" in lowered

    @staticmethod
    def _is_new_enough(value: str | None, since: datetime) -> bool:
        if not value:
            return False
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed >= since.astimezone(timezone.utc)
