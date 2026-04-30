from nextinai.agents import ReportInterpretation, TrendingProjectAnalysis
from nextinai.collectors.reports import CollectedReportItem, ReportSource
from nextinai.services.report_agent import AgenticReportService
from nextinai.storage.files import FileStorage


class FakeReportCollector:
    def __init__(self, items):
        self.items = items
        self.calls = []

    def collect(self, source: ReportSource, progress_callback=None):
        self.calls.append(source.name)
        if progress_callback is not None:
            progress_callback(f"collector:{source.name}")
        return self.items


class FakeInterpreter:
    def summarize_repository_updates(self, *, repository, hours, items):
        return "unused"

    def analyze_trending_repository(self, repo):
        return TrendingProjectAnalysis("unused", "unused", "unused")

    def interpret_report(self, *, title, source_name, url, summary_text, body_text):
        return ReportInterpretation(
            factual_summary=f"事实：{title}",
            interpreted_summary=f"解读：{source_name}",
            evidence=[url],
            is_partial=not bool(body_text),
        )


def test_report_service_collects_and_interprets_reports(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    collector = FakeReportCollector(
        [
            CollectedReportItem(
                source_name="OpenAI News",
                title="Introducing a new agent workflow",
                url="https://example.com/agent-workflow",
                published_at="2026-04-30T00:00:00+00:00",
                summary_text="OpenAI 发布新的 agent 工作流。",
                body_text="This post explains a new agent workflow for tool use.",
                metadata_json={"group": "default"},
                partial=False,
            )
        ]
    )
    service = AgenticReportService(
        storage=storage,
        collector=collector,
        agent=FakeInterpreter(),
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml")],
    )

    message = service.fetch_reports("default")

    content_items = storage.load_collection("content_items")
    analysis_results = storage.load_collection("analysis_results")
    assert "新增 1 条" in message
    assert len(content_items) == 1
    assert len(analysis_results) == 1
    assert analysis_results[0]["factual_summary"] == "事实：Introducing a new agent workflow"
    assert analysis_results[0]["interpreted_summary"] == "解读：OpenAI News"


def test_report_service_records_skip_for_duplicate_or_unreadable(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    collector = FakeReportCollector(
        [
            CollectedReportItem(
                source_name="OpenAI News",
                title="Unreadable item",
                url="https://example.com/unreadable",
                published_at="2026-04-30T00:00:00+00:00",
                summary_text=None,
                body_text=None,
                metadata_json={"group": "default"},
                partial=True,
            )
        ]
    )
    service = AgenticReportService(
        storage=storage,
        collector=collector,
        agent=FakeInterpreter(),
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml")],
    )

    message = service.fetch_reports("default")

    skips = storage.load_collection("report_skips")
    assert "跳过 1 条" in message
    assert skips[0]["reason"] == "unreadable"


def test_report_service_retries_interpretation_for_existing_content_without_analysis(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector(
            [
                CollectedReportItem(
                    source_name="OpenAI News",
                    title="Agent roadmap update",
                    url="https://example.com/agent-roadmap",
                    published_at="2026-04-30T00:00:00+00:00",
                    summary_text="roadmap",
                    body_text="details",
                    metadata_json={"group": "default"},
                    partial=False,
                )
            ]
        ),
        agent=FakeInterpreter(),
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml")],
    )
    existing = CollectedReportItem(
        source_name="OpenAI News",
        title="Agent roadmap update",
        url="https://example.com/agent-roadmap",
        published_at="2026-04-30T00:00:00+00:00",
        summary_text="roadmap",
        body_text="details",
        metadata_json={"group": "default"},
        partial=False,
    )
    fingerprint = service._build_fingerprint(existing)
    storage.save_collection(
        "content_items",
        [service._build_content_record(existing, fingerprint)],
    )

    message = service.fetch_reports("default")

    analysis_results = storage.load_collection("analysis_results")
    skips = storage.load_collection("report_skips")
    assert "解读 1 条" in message
    assert len(analysis_results) == 1
    assert skips == []


def test_report_service_emits_progress_messages(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    progress_messages: list[str] = []
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector(
            [
                CollectedReportItem(
                    source_name="OpenAI News",
                    title="Agent roadmap update",
                    url="https://example.com/agent-roadmap",
                    published_at="2026-04-30T00:00:00+00:00",
                    summary_text="roadmap",
                    body_text="details",
                    metadata_json={"group": "default"},
                    partial=False,
                )
            ]
        ),
        agent=FakeInterpreter(),
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml")],
    )

    service.fetch_reports("default", progress_callback=progress_messages.append)

    assert any("开始抓取来源：OpenAI News" in message for message in progress_messages)
    assert any("collector:OpenAI News" in message for message in progress_messages)
    assert any("正在解读：Agent roadmap update" in message for message in progress_messages)
