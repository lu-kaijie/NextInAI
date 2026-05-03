from nextinai.agents import DeepReportReading, ReportInterpretation, TrendingProjectAnalysis
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


class FakeAnthropicCollector:
    def __init__(self) -> None:
        self.calls = []

    def collect(self, source: ReportSource, progress_callback=None):
        self.calls.append((source.name, source.kind, source.url))
        return []


class FakeInterpreter:
    def __init__(self) -> None:
        self.deep_read_calls = 0
        self.translate_calls = 0

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

    def deep_read_report(self, *, title, source_name, url, summary_text, body_text):
        self.deep_read_calls += 1
        return DeepReportReading(
            markdown_body=f"# {title} 深度带读\n\n## 先说结论\n这是 {source_name} 的详细解读。",
            summary=f"{title} 的详细解读",
            evidence=[url],
            is_partial=not bool(body_text),
        )

    def translate_report_excerpt(self, *, title, source_name, excerpt_text):
        self.translate_calls += 1
        if "这是中文" in excerpt_text:
            return excerpt_text
        return f"这是一段流畅的中文译文：{title}"


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


def test_anthropic_source_uses_webpage_index_mode(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    collector = FakeAnthropicCollector()
    service = AgenticReportService(
        storage=storage,
        collector=collector,
        agent=FakeInterpreter(),
        sources=[ReportSource("Anthropic News", "company", "webpage_index", "https://www.anthropic.com/news", category="AI 公司")],
    )

    message = service.fetch_reports("company")

    assert "报告采集完成" in message
    assert collector.calls == [("Anthropic News", "webpage_index", "https://www.anthropic.com/news")]


def test_cohere_research_source_can_be_registered(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    collector = FakeAnthropicCollector()
    service = AgenticReportService(
        storage=storage,
        collector=collector,
        agent=FakeInterpreter(),
        sources=[
            ReportSource(
                "Cohere Research",
                "company",
                "webpage_index",
                "https://cohere.com/research",
                category="AI 公司",
                article_path_prefix="/research/papers/",
            )
        ],
    )

    service.fetch_reports("company")

    assert collector.calls == [("Cohere Research", "webpage_index", "https://cohere.com/research")]


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


def test_report_service_lists_sources_reports_and_detail(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector([]),
        agent=FakeInterpreter(),
        sources=[
            ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml", category="AI 公司"),
            ReportSource("Hugging Face Blog", "default", "feed", "https://example.com/hf.xml", category="开源与平台"),
        ],
    )
    report = CollectedReportItem(
        source_name="OpenAI News",
        title="Agent roadmap update",
        url="https://example.com/agent-roadmap",
        published_at="2026-04-30T00:00:00+00:00",
        summary_text="roadmap",
        body_text="details",
        metadata_json={"group": "default"},
        partial=False,
    )
    fingerprint = service._build_fingerprint(report)
    storage.save_collection("content_items", [service._build_content_record(report, fingerprint)])
    storage.save_collection(
        "analysis_results",
        [
            {
                "analysis_kind": "report_interpretation",
                "source_ref": f"report:{fingerprint}",
                "title": report.title,
                "factual_summary": "事实：Agent roadmap update",
                "interpreted_summary": "解读：OpenAI News",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )

    sources = service.list_sources(source_category="AI 公司")
    reports = service.list_reports("OpenAI News", limit=5, source_category="AI 公司")
    detail = service.get_report_detail(f"report:{fingerprint}")

    assert len(sources) == 1
    assert sources[0]["category"] == "AI 公司"
    assert reports[0]["title"] == "Agent roadmap update"
    assert reports[0]["deep_reading_ready"] is False
    assert detail is not None
    assert detail["interpreted_summary"] == "解读：OpenAI News"


def test_report_service_can_export_report_detail(tmp_path) -> None:
    storage = FileStorage(tmp_path / "data")
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector([]),
        agent=FakeInterpreter(),
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml")],
    )
    service.report_output_dir = tmp_path / "artifacts"
    report = CollectedReportItem(
        source_name="OpenAI News",
        title="Agent roadmap update",
        url="https://example.com/agent-roadmap",
        published_at="2026-04-30T00:00:00+00:00",
        summary_text="roadmap",
        body_text="details",
        metadata_json={"group": "default"},
        partial=False,
    )
    fingerprint = service._build_fingerprint(report)
    storage.save_collection("content_items", [service._build_content_record(report, fingerprint)])
    storage.save_collection(
        "analysis_results",
        [
            {
                "analysis_kind": "report_interpretation",
                "source_ref": f"report:{fingerprint}",
                "title": report.title,
                "factual_summary": "事实：Agent roadmap update",
                "interpreted_summary": "解读：OpenAI News",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )

    exported = service.export_report(f"report:{fingerprint}", ["md", "pdf"])

    assert exported["md"].endswith(".md")
    assert exported["pdf"].endswith(".pdf")


def test_report_service_can_export_report_summary(tmp_path) -> None:
    storage = FileStorage(tmp_path / "data")
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector([]),
        agent=FakeInterpreter(),
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml")],
    )
    service.report_output_dir = tmp_path / "artifacts"
    report = CollectedReportItem(
        source_name="OpenAI News",
        title="Agent roadmap update",
        url="https://example.com/agent-roadmap",
        published_at="2026-04-30T00:00:00+00:00",
        summary_text="roadmap",
        body_text="details",
        metadata_json={"group": "default"},
        partial=False,
    )
    fingerprint = service._build_fingerprint(report)
    storage.save_collection("content_items", [service._build_content_record(report, fingerprint)])
    storage.save_collection(
        "analysis_results",
        [
            {
                "analysis_kind": "report_interpretation",
                "source_ref": f"report:{fingerprint}",
                "title": report.title,
                "factual_summary": "事实：Agent roadmap update",
                "interpreted_summary": "解读：OpenAI News",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )

    exported = service.export_report_summary("OpenAI News", 10, ["md", "pdf"])

    assert exported["md"].endswith(".md")
    assert exported["pdf"].endswith(".pdf")


def test_report_service_generates_and_reuses_deep_reading(tmp_path) -> None:
    storage = FileStorage(tmp_path / "data")
    interpreter = FakeInterpreter()
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector([]),
        agent=interpreter,
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml", category="AI 公司")],
    )
    report = CollectedReportItem(
        source_name="OpenAI News",
        title="Agent roadmap update",
        url="https://example.com/agent-roadmap",
        published_at="2026-04-30T00:00:00+00:00",
        summary_text="roadmap",
        body_text="details",
        metadata_json={"group": "default", "category": "AI 公司"},
        partial=False,
    )
    fingerprint = service._build_fingerprint(report)
    storage.save_collection("content_items", [service._build_content_record(report, fingerprint)])
    storage.save_collection(
        "analysis_results",
        [
            {
                "analysis_kind": "report_interpretation",
                "source_ref": f"report:{fingerprint}",
                "title": report.title,
                "factual_summary": "事实：Agent roadmap update",
                "interpreted_summary": "解读：OpenAI News",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )

    first = service.generate_deep_report_reading(f"report:{fingerprint}")
    second = service.generate_deep_report_reading(f"report:{fingerprint}")
    forced = service.generate_deep_report_reading(f"report:{fingerprint}", force=True)

    assert first["deep_reading_ready"] is True
    assert "深度带读" in str(first["deep_reading_markdown"])
    assert second["deep_reading_ready"] is True
    assert forced["deep_reading_ready"] is True
    assert interpreter.deep_read_calls == 2


def test_report_service_exports_deep_reading_content(tmp_path) -> None:
    storage = FileStorage(tmp_path / "data")
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector([]),
        agent=FakeInterpreter(),
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml", category="AI 公司")],
    )
    service.report_output_dir = tmp_path / "artifacts"
    report = CollectedReportItem(
        source_name="OpenAI News",
        title="Agent roadmap update",
        url="https://example.com/agent-roadmap",
        published_at="2026-04-30T00:00:00+00:00",
        summary_text="roadmap",
        body_text="details",
        metadata_json={"group": "default", "category": "AI 公司"},
        partial=False,
    )
    fingerprint = service._build_fingerprint(report)
    storage.save_collection("content_items", [service._build_content_record(report, fingerprint)])
    storage.save_collection(
        "analysis_results",
        [
            {
                "analysis_kind": "report_interpretation",
                "source_ref": f"report:{fingerprint}",
                "title": report.title,
                "factual_summary": "事实：Agent roadmap update",
                "interpreted_summary": "解读：OpenAI News",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )
    service.generate_deep_report_reading(f"report:{fingerprint}")

    exported = service.export_report(f"report:{fingerprint}", ["md"])

    markdown_path = exported["md"]
    assert markdown_path.endswith(".md")
    assert "深度带读" in open(markdown_path, encoding="utf-8").read()


def test_report_service_generates_and_reuses_excerpt_translation(tmp_path) -> None:
    storage = FileStorage(tmp_path / "data")
    interpreter = FakeInterpreter()
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector([]),
        agent=interpreter,
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml", category="AI 公司")],
    )
    report = CollectedReportItem(
        source_name="OpenAI News",
        title="Agent roadmap update",
        url="https://example.com/agent-roadmap",
        published_at="2026-04-30T00:00:00+00:00",
        summary_text="roadmap",
        body_text="This post explains a new agent workflow for tool use.",
        metadata_json={"group": "default", "category": "AI 公司"},
        partial=False,
    )
    fingerprint = service._build_fingerprint(report)
    storage.save_collection("content_items", [service._build_content_record(report, fingerprint)])

    first = service.generate_report_excerpt_translation(f"report:{fingerprint}")
    second = service.generate_report_excerpt_translation(f"report:{fingerprint}")
    forced = service.generate_report_excerpt_translation(f"report:{fingerprint}", force=True)

    assert "流畅的中文译文" in str(first["localized_excerpt_text"])
    assert second["localized_excerpt_text"] == first["localized_excerpt_text"]
    assert forced["localized_excerpt_text"] == first["localized_excerpt_text"]
    assert interpreter.translate_calls == 2


def test_report_service_keeps_chinese_excerpt_without_translation_changes(tmp_path) -> None:
    storage = FileStorage(tmp_path / "data")
    interpreter = FakeInterpreter()
    service = AgenticReportService(
        storage=storage,
        collector=FakeReportCollector([]),
        agent=interpreter,
        sources=[ReportSource("OpenAI News", "default", "feed", "https://example.com/feed.xml", category="AI 公司")],
    )
    report = CollectedReportItem(
        source_name="OpenAI News",
        title="中文报告",
        url="https://example.com/cn-report",
        published_at="2026-04-30T00:00:00+00:00",
        summary_text="摘要",
        body_text="这是中文原文摘录，应该直接展示。",
        metadata_json={"group": "default", "category": "AI 公司"},
        partial=False,
    )
    fingerprint = service._build_fingerprint(report)
    storage.save_collection("content_items", [service._build_content_record(report, fingerprint)])

    detail = service.generate_report_excerpt_translation(f"report:{fingerprint}")

    assert detail["localized_excerpt_text"] == "这是中文原文摘录，应该直接展示。"
