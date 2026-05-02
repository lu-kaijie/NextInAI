from datetime import datetime, timedelta, timezone

from nextinai.agents import ReportInterpretation, TrendingProjectAnalysis
from nextinai.collectors.trending import TrendingQueryPlan, TrendingQueryResult, TrendingRepository
from nextinai.services.github_subscriptions import GitHubSubscriptionService
from nextinai.services.github_trending import GitHubTrendingService
from nextinai.storage.files import FileStorage


class FakeSubscriptionAgent:
    def summarize_repository_updates(self, *, repository, hours, items):
        return f"# {repository}\n\n最近 {hours} 小时共有 {len(items)} 条更新。"

    def analyze_trending_repository(self, repo):
        return TrendingProjectAnalysis("unused", "unused", "高")

    def interpret_report(self, **kwargs):
        return ReportInterpretation("unused", "unused", [], False)


class FakeTrendingCollector:
    def collect_with_metadata(self, window: str, limit: int):
        now = datetime.now(timezone.utc)
        return TrendingQueryResult(
            plan=TrendingQueryPlan(
                requested_window=window,
                resolved_window="daily",
                source_mode="official_trending_page",
                source_label="GitHub 官方 Trending 页面（日榜）",
                is_official=True,
            ),
            repositories=[
                TrendingRepository(
                    full_name="openai/gpt-oss",
                    html_url="https://github.com/openai/gpt-oss",
                    description="Open-source GPT models.",
                    stars=12345,
                    forks=900,
                    language="Python",
                    topics=[],
                    pushed_at=now.isoformat(),
                    created_at=(now - timedelta(days=2)).isoformat(),
                    readme_excerpt="README excerpt",
                    partial=False,
                    stars_in_period="1,234",
                )
            ][:limit],
        )


class FakeTrendingAgent:
    def summarize_repository_updates(self, *, repository, hours, items):
        return "unused"

    def analyze_trending_repository(self, repo):
        return TrendingProjectAnalysis("purpose", "why", "高")

    def interpret_report(self, **kwargs):
        return ReportInterpretation("unused", "unused", [], False)


def test_subscription_service_can_export_repository_summary(tmp_path) -> None:
    storage = FileStorage(tmp_path / "data")
    now = datetime.now(timezone.utc).isoformat()
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "github_repository",
                "source_key": "openai/gpt-oss",
                "signal_type": "commit",
                "title": "Improve eval throughput",
                "url": "https://example.com/repo",
                "published_at": now,
                "summary_text": "performance improvement",
                "metadata_json": {},
                "dedupe_fingerprint": "repo1",
            }
        ],
    )
    service = GitHubSubscriptionService(storage=storage, agent=FakeSubscriptionAgent())
    service.export_service.output_dir = tmp_path / "artifacts"

    exported = service.export_repository_summary("openai/gpt-oss", 24, ["md", "pdf"])

    assert exported["md"].endswith(".md")
    assert exported["pdf"].endswith(".pdf")


def test_trending_service_can_export_ranked_report(tmp_path) -> None:
    service = GitHubTrendingService(collector=FakeTrendingCollector(), agent=FakeTrendingAgent())
    service.export_service.output_dir = tmp_path / "artifacts"

    exported = service.export_trending("daily", 5, ["md", "pdf"])

    assert exported["md"].endswith(".md")
    assert exported["pdf"].endswith(".pdf")
