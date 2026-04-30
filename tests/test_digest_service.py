from datetime import datetime, timezone

from nextinai.agents import DigestOverview, ReportInterpretation, TrendingProjectAnalysis
from nextinai.services.digest_service import AgenticDigestService
from nextinai.storage.files import FileStorage


class FakeIntelligenceAgent:
    def summarize_repository_updates(self, *, repository, hours, items):
        return f"# {repository}\n\n- repo items: {len(items)}"

    def analyze_trending_repository(self, repo):
        return TrendingProjectAnalysis("purpose", "why", "confidence")

    def interpret_report(self, **kwargs):
        return ReportInterpretation("fact", "interp", [], False)

    def compose_digest_overview(
        self,
        *,
        scope,
        repo_summaries,
        trending_entries,
        report_entries,
        missing_sections,
    ):
        return DigestOverview(
            title=f"Digest {scope}",
            summary=f"repo={len(repo_summaries)}, trend={len(trending_entries)}, report={len(report_entries)}",
            highlights=["h1", "h2"],
        )


def test_digest_service_generates_markdown_and_persists_digest(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    storage.save_collection("subscriptions", [{"repository": "openai/gpt-oss", "lookback_hours": 24, "refresh_minutes": 60}])
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
            },
            {
                "source_kind": "github_trending",
                "source_key": "daily",
                "signal_type": "trending_snapshot",
                "title": "openai/gpt-oss",
                "url": "https://example.com/trending",
                "published_at": now,
                "summary_text": "trending",
                "metadata_json": {"why_trending": "star 总量高"},
                "dedupe_fingerprint": "trend1",
            },
        ],
    )
    storage.save_collection(
        "analysis_results",
        [
            {
                "analysis_kind": "report_interpretation",
                "source_ref": "report:1",
                "title": "Agent workflow report",
                "factual_summary": "事实摘要",
                "interpreted_summary": "解读分析",
                "is_partial": False,
            }
        ],
    )
    service = AgenticDigestService(storage=storage, agent=FakeIntelligenceAgent())

    markdown = service.generate("daily")

    digests = storage.load_collection("digests")
    assert "# Digest daily" in markdown
    assert "## GitHub 仓库更新" in markdown
    assert "## 热门 GitHub 项目" in markdown
    assert "## AI 报告解读" in markdown
    assert len(digests) == 1


def test_digest_service_marks_missing_sections_as_unavailable(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    service = AgenticDigestService(storage=storage, agent=FakeIntelligenceAgent())

    markdown = service.generate("daily")

    assert "不可用：当前窗口内没有可用仓库更新" in markdown
    assert "不可用：当前窗口内没有可用热门榜结果" in markdown


def test_digest_service_exports_markdown_and_pdf(tmp_path) -> None:
    storage = FileStorage(tmp_path / "data")
    service = AgenticDigestService(storage=storage, agent=FakeIntelligenceAgent())
    service.report_output_dir = tmp_path / "artifacts"

    service.generate("daily")
    exported = service.export("daily", ["md", "pdf"])

    assert exported["md"].endswith(".md")
    assert exported["pdf"].endswith(".pdf")
    assert (tmp_path / "artifacts").exists()
