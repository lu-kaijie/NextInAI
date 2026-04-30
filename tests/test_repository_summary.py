from datetime import datetime, timedelta, timezone

from nextinai.agents import RuleBasedIntelligenceAgent, TrendingProjectAnalysis
from nextinai.services.github_subscriptions import GitHubSubscriptionService
from nextinai.storage.files import FileStorage


class FakeIntelligenceAgent:
    def summarize_repository_updates(self, *, repository, hours, items):
        return f"repo={repository};hours={hours};count={len(items)}"

    def analyze_trending_repository(self, repo):
        return TrendingProjectAnalysis("purpose", "why", "confidence")

    def interpret_report(self, **kwargs):
        raise AssertionError("not used")


def test_repository_summary_groups_changes_by_category(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    now = datetime.now(timezone.utc)
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "github_repository",
                "source_key": "openai/gpt-oss",
                "signal_type": "release",
                "title": "New multimodal support",
                "url": "https://example.com/release",
                "external_id": "release:1",
                "published_at": now.isoformat(),
                "summary_text": "introduce image input",
                "metadata_json": {},
                "dedupe_fingerprint": "a",
            },
            {
                "source_kind": "github_repository",
                "source_key": "openai/gpt-oss",
                "signal_type": "commit",
                "title": "Fix tokenizer bug",
                "url": "https://example.com/commit",
                "external_id": "commit:1",
                "published_at": now.isoformat(),
                "summary_text": "bug fix",
                "metadata_json": {},
                "dedupe_fingerprint": "b",
            },
            {
                "source_kind": "github_repository",
                "source_key": "openai/gpt-oss",
                "signal_type": "pull_request",
                "title": "Improve eval throughput",
                "url": "https://example.com/pr",
                "external_id": "pull:1",
                "published_at": now.isoformat(),
                "summary_text": "performance improvement",
                "metadata_json": {},
                "dedupe_fingerprint": "c",
            },
        ],
    )
    service = GitHubSubscriptionService(storage=storage, collector=None, agent=FakeIntelligenceAgent())

    summary = service.summarize_repository("openai/gpt-oss", 24)

    assert summary == "repo=openai/gpt-oss;hours=24;count=3"


def test_repository_summary_handles_no_updates(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "github_repository",
                "source_key": "openai/gpt-oss",
                "signal_type": "commit",
                "title": "Old change",
                "url": "https://example.com/old",
                "external_id": "commit:old",
                "published_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                "summary_text": "old",
                "metadata_json": {},
                "dedupe_fingerprint": "old",
            }
        ],
    )
    service = GitHubSubscriptionService(storage=storage, collector=None, agent=FakeIntelligenceAgent())

    summary = service.summarize_repository("openai/gpt-oss", 24)

    assert summary == "repo=openai/gpt-oss;hours=24;count=0"


def test_repository_summary_accepts_github_z_timestamps(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "github_repository",
                "source_key": "langchain-ai/langchain",
                "signal_type": "commit",
                "title": "Add new agent runtime",
                "url": "https://example.com/commit/1",
                "external_id": "commit:1",
                "published_at": "2026-04-29T21:58:15Z",
                "summary_text": "introduce runtime",
                "metadata_json": {},
                "dedupe_fingerprint": "runtime-1",
            }
        ],
    )
    service = GitHubSubscriptionService(storage=storage, collector=None, agent=FakeIntelligenceAgent())

    summary = service.summarize_repository("langchain-ai/langchain", 168)

    assert summary == "repo=langchain-ai/langchain;hours=168;count=1"


def test_rule_based_repository_summary_deduplicates_pr_and_commit_and_explains_changes() -> None:
    agent = RuleBasedIntelligenceAgent()

    summary = agent.summarize_repository_updates(
        repository="langchain-ai/langchain",
        hours=168,
        items=[
            {
                "signal_type": "pull_request",
                "title": "feat(perplexity): add `PerplexityEmbeddings`",
                "url": "https://example.com/pr/1",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "summary_text": "new embedding integration",
            },
            {
                "signal_type": "commit",
                "title": "feat(perplexity): add `PerplexityEmbeddings` (#37082)",
                "url": "https://example.com/commit/1",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "summary_text": "new embedding integration",
            },
            {
                "signal_type": "release",
                "title": "langchain-perplexity==1.2.0",
                "url": "https://example.com/release/1",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "summary_text": "release",
            },
        ],
    )

    assert "https://example.com/commit/1" not in summary
    assert "https://example.com/pr/1" in summary
    assert "这说明仓库在补充向量化或检索相关能力" in summary
    assert "这 168 小时里，langchain-ai/langchain 主要有这些变化" in summary
