from datetime import datetime, timezone

from nextinai.agents import ReportInterpretation, TrendingProjectAnalysis
from nextinai.collectors.trending import TrendingQueryPlan, TrendingQueryResult, TrendingRepository
from nextinai.harness.adapters import BriefingViewBuilder, IntelligenceEventAdapter
from nextinai.storage.files import FileStorage


class FakeTrendingCollector:
    def collect_with_metadata(self, window: str, limit: int):
        repositories = [
            TrendingRepository(
                full_name="mattpocock/skills",
                html_url="https://github.com/mattpocock/skills",
                description="Skills for Real Engineers.",
                stars=47000,
                forks=3800,
                language="Shell",
                topics=[],
                pushed_at=None,
                created_at=None,
                readme_excerpt=None,
                partial=False,
                stars_in_period="7,280",
            )
        ][:limit]
        return TrendingQueryResult(
            plan=TrendingQueryPlan(
                requested_window=window,
                source_mode="official_trending",
                source_label="GitHub 官方 Trending",
                resolved_window=window,
                is_official=True,
            ),
            repositories=repositories,
        )


class FakeIntelligenceAgent:
    def summarize_repository_updates(self, *, repository, hours, items):
        return "unused"

    def analyze_trending_repository(self, repo):
        return TrendingProjectAnalysis(
            purpose=f"{repo.full_name} 是一个工程技能仓库。",
            why_trending="作者影响力强，且 AI 工作流主题传播度高。",
            confidence="高",
        )

    def interpret_report(self, *, title, source_name, url, summary_text, body_text):
        return ReportInterpretation("事实", "解读", [url], False)


def test_event_adapter_builds_repo_update_events(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "github_repository",
                "source_key": "langchain-ai/langchain",
                "signal_type": "pull_request",
                "title": "feat(perplexity): add PerplexityEmbeddings",
                "url": "https://github.com/langchain-ai/langchain/pull/1",
                "published_at": now,
                "summary_text": "add embeddings support",
                "metadata_json": {},
                "dedupe_fingerprint": "repo-1",
            },
            {
                "source_kind": "github_repository",
                "source_key": "langchain-ai/langchain",
                "signal_type": "commit",
                "title": "feat(perplexity): add PerplexityEmbeddings (#1)",
                "url": "https://github.com/langchain-ai/langchain/commit/1",
                "published_at": now,
                "summary_text": "same change",
                "metadata_json": {},
                "dedupe_fingerprint": "repo-2",
            },
        ],
    )
    adapter = IntelligenceEventAdapter(storage=storage, collector=FakeTrendingCollector(), agent=FakeIntelligenceAgent())

    events = adapter.get_repo_update_events("langchain-ai/langchain", hours=24)

    assert len(events) == 1
    assert events[0].event_type == "change_event"
    assert events[0].metadata["source_item_count"] == 2


def test_event_adapter_builds_report_events_from_content_and_analysis(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "ai_report",
                "source_key": "OpenAI News",
                "signal_type": "report_publication",
                "title": "OpenAI models come to AWS",
                "url": "https://example.com/aws",
                "published_at": now,
                "summary_text": "summary",
                "body_text": "body",
                "metadata_json": {},
                "dedupe_fingerprint": "report-1",
                "partial": False,
            }
        ],
    )
    storage.save_collection(
        "analysis_results",
        [
            {
                "analysis_kind": "report_interpretation",
                "source_ref": "report:report-1",
                "title": "OpenAI models come to AWS",
                "factual_summary": "这是一次渠道扩展。",
                "interpreted_summary": "意味着 OpenAI 正在强化企业分发。",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )
    adapter = IntelligenceEventAdapter(storage=storage, collector=FakeTrendingCollector(), agent=FakeIntelligenceAgent())

    events = adapter.get_report_events()

    assert len(events) == 1
    assert events[0].event_type == "insight_event"
    assert "企业分发" in events[0].summary


def test_event_adapter_builds_trending_events_and_flash_briefing(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    adapter = IntelligenceEventAdapter(storage=storage, collector=FakeTrendingCollector(), agent=FakeIntelligenceAgent())

    events = adapter.get_trending_events("daily", limit=1)
    briefing = BriefingViewBuilder().build_flash_briefing(scope="daily", events=events)

    assert len(events) == 1
    assert events[0].event_type == "trend_event"
    assert "mattpocock/skills" in briefing.content_markdown
