from nextinai.agents.assistant import AssistantAgent
from nextinai.core.config import get_settings
from nextinai.storage.files import FileStorage


class FakePlanner:
    def __init__(self, tool_name: str, tool_input: dict | None = None, intent: str = "query_intelligence") -> None:
        self.tool_name = tool_name
        self.tool_input = tool_input or {}
        self.intent = intent

    def decide(self, *, message: str, state) -> object:
        from nextinai.agents.assistant import IntentDecision

        return IntentDecision(
            intent=self.intent,
            tool_name=self.tool_name,
            tool_input=dict(self.tool_input),
        )


class FailingPlanner:
    def decide(self, *, message: str, state) -> object:
        raise RuntimeError("planner unavailable")


class SequencedPlanner:
    def __init__(self, decisions: list[tuple[str, dict | None, str]]) -> None:
        self.decisions = decisions
        self.index = 0

    def decide(self, *, message: str, state) -> object:
        from nextinai.agents.assistant import IntentDecision

        tool_name, tool_input, intent = self.decisions[min(self.index, len(self.decisions) - 1)]
        self.index += 1
        return IntentDecision(
            intent=intent,
            tool_name=tool_name,
            tool_input=dict(tool_input or {}),
        )


def test_assistant_agent_queries_reports_and_supports_detail_followup(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "ai_report",
                "subject": "OpenAI News",
                "source_key": "OpenAI News",
                "signal_type": "report_publication",
                "title": "OpenAI models come to AWS",
                "url": "https://example.com/aws",
                "published_at": "2026-04-30T00:00:00+00:00",
                "summary_text": "OpenAI 正在强化企业分发。",
                "body_text": "这是渠道扩展信号。",
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
                "interpreted_summary": "OpenAI 正在强化企业分发。",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )
    agent = AssistantAgent(
        storage=storage,
        intent_planner=SequencedPlanner(
            [
                ("get_report_events", {"limit": 1}, "query_intelligence"),
                ("get_event_detail", {"reference_index": 1}, "explore_detail"),
            ]
        ),
    )
    session_id = "session-1"

    first = agent.respond("给我最近 1 篇报告", session_id=session_id)
    second = agent.respond("第 1 个详细讲讲", session_id=session_id)

    assert "最值得注意" in first.message
    assert "OpenAI models come to AWS" in second.message
    assert "核心解读" in second.message


def test_assistant_agent_supports_chinese_ordinal_reference(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "ai_report",
                "subject": "OpenAI News",
                "source_key": "OpenAI News",
                "signal_type": "report_publication",
                "title": "Report 1",
                "url": "https://example.com/1",
                "published_at": "2026-04-30T00:00:00+00:00",
                "summary_text": "summary 1",
                "body_text": "body 1",
                "metadata_json": {},
                "dedupe_fingerprint": "report-1",
                "partial": False,
            },
            {
                "source_kind": "ai_report",
                "subject": "OpenAI News",
                "source_key": "OpenAI News",
                "signal_type": "report_publication",
                "title": "Report 2",
                "url": "https://example.com/2",
                "published_at": "2026-04-30T00:00:00+00:00",
                "summary_text": "summary 2",
                "body_text": "body 2",
                "metadata_json": {},
                "dedupe_fingerprint": "report-2",
                "partial": False,
            },
            {
                "source_kind": "ai_report",
                "subject": "OpenAI News",
                "source_key": "OpenAI News",
                "signal_type": "report_publication",
                "title": "Report 3",
                "url": "https://example.com/3",
                "published_at": "2026-04-30T00:00:00+00:00",
                "summary_text": "summary 3",
                "body_text": "body 3",
                "metadata_json": {},
                "dedupe_fingerprint": "report-3",
                "partial": False,
            },
        ],
    )
    storage.save_collection(
        "analysis_results",
        [
            {"analysis_kind": "report_interpretation", "source_ref": "report:report-1", "title": "Report 1", "factual_summary": "事实 1", "interpreted_summary": "解读 1", "evidence_json": [], "is_partial": False},
            {"analysis_kind": "report_interpretation", "source_ref": "report:report-2", "title": "Report 2", "factual_summary": "事实 2", "interpreted_summary": "解读 2", "evidence_json": [], "is_partial": False},
            {"analysis_kind": "report_interpretation", "source_ref": "report:report-3", "title": "Report 3", "factual_summary": "事实 3", "interpreted_summary": "解读 3", "evidence_json": [], "is_partial": False},
        ],
    )
    agent = AssistantAgent(
        storage=storage,
        intent_planner=SequencedPlanner(
            [
                ("get_report_events", {"limit": 3}, "query_intelligence"),
                ("get_event_detail", {"reference_index": 3}, "explore_detail"),
            ]
        ),
    )
    session_id = "session-cn-ordinal"

    first = agent.respond("给我最近 3 篇报告", session_id=session_id)
    second = agent.respond("第三个详细讲讲", session_id=session_id)

    assert "最值得注意" in first.message
    assert "Report 3" in second.message
    assert "核心解读" in second.message


def test_assistant_agent_returns_explicit_message_when_reference_resolution_fails(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    agent = AssistantAgent(storage=storage, intent_planner=FakePlanner("get_event_detail", {}))

    response = agent.respond("第三个详细讲讲", session_id="session-missing-ref")

    assert "没有成功定位到具体对象" in response.message


def test_assistant_agent_returns_validation_error_for_unsupported_trending_window(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    agent = AssistantAgent(
        storage=storage,
        intent_planner=FakePlanner("get_trending_events", {"window": "60d", "limit": 5}),
    )

    response = agent.respond("最近两个月star增长最快的五个项目", session_id="session-unsupported-window")

    assert "参数 window 不支持值 '60d'" in response.message
    assert response.raw_outputs["error"]["allowed_values"] == ["daily", "7d", "30d"]


def test_assistant_agent_returns_validation_error_for_missing_required_export_format(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    agent = AssistantAgent(
        storage=storage,
        intent_planner=FakePlanner("export_trending", {"window": "daily"}),
    )

    response = agent.respond("导出热门榜", session_id="session-missing-export-format")

    assert "缺少必填参数：formats" in response.message
    assert response.raw_outputs["error"]["error_type"] == "missing_required_field"


def test_assistant_agent_requires_confirmation_for_side_effects(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    agent = AssistantAgent(
        storage=storage,
        intent_planner=FakePlanner("add_subscription", {"repository": "openai/openai-python"}),
    )
    session_id = "session-2"

    first = agent.respond("订阅仓库 openai/openai-python", session_id=session_id)
    second = agent.respond("确认", session_id=session_id)

    assert first.pending_confirmation is True
    assert "需要确认" in first.message or "回复“确认”" in first.message
    assert "已新增订阅" in second.message


def test_assistant_agent_lists_and_deletes_tasks(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "delivery_tasks",
        [
            {
                "task_id": "task-1",
                "channel": "email",
                "target": "default",
                "scope": "daily",
                "view": "flash",
                "schedule": "daily",
                "enabled": True,
                "created_at": "2026-04-30T00:00:00+00:00",
                "updated_at": "2026-04-30T00:00:00+00:00",
            }
        ],
    )
    agent = AssistantAgent(
        storage=storage,
        intent_planner=SequencedPlanner(
            [
                ("get_delivery_tasks", {}, "query_intelligence"),
                ("delete_delivery_task", {"reference_index": 1}, "execute_action"),
            ]
        ),
    )
    session_id = "session-task"

    first = agent.respond("列出任务", session_id=session_id)
    second = agent.respond("删除第 1 个任务", session_id=session_id)

    assert "当前推送任务如下" in first.message
    assert second.pending_confirmation is True


def test_assistant_agent_generates_briefing_from_last_events(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "events",
        [
            {
                "event_id": "report_1",
                "event_type": "insight_event",
                "subject": "OpenAI News",
                "title": "OpenAI models come to AWS",
                "summary": "OpenAI 正在强化企业分发。",
                "rationale": "这是渠道扩展，不只是单篇新闻。",
                "source_refs": [],
                "tags": [],
                "novelty_score": 0.8,
                "relevance_score": 0.7,
                "impact_score": 0.7,
                "heat_score": 0.6,
                "confidence_score": 0.8,
                "importance_score": 0.73,
                "happened_at": "2026-04-30T00:00:00+00:00",
                "related_event_ids": [],
                "briefing_ids": [],
                "delivery_task_ids": [],
                "metadata": {},
                "created_at": "2026-04-30T00:00:00+00:00",
                "updated_at": "2026-04-30T00:00:00+00:00",
            }
        ],
    )
    agent = AssistantAgent(
        storage=storage,
        intent_planner=FakePlanner("render_briefing_preview", {"view": "flash"}, "generate_briefing"),
    )

    response = agent.respond("生成简报", session_id="session-3")

    assert "# NextInAI 快讯简报" in response.message


def test_assistant_agent_generates_deep_briefing(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "events",
        [
            {
                "event_id": "report_1",
                "event_type": "insight_event",
                "subject": "OpenAI News",
                "title": "OpenAI models come to AWS",
                "summary": "OpenAI 正在强化企业分发。",
                "rationale": "这是渠道扩展，不只是单篇新闻。",
                "source_refs": [],
                "tags": [],
                "novelty_score": 0.8,
                "relevance_score": 0.7,
                "impact_score": 0.7,
                "heat_score": 0.6,
                "confidence_score": 0.8,
                "importance_score": 0.73,
                "happened_at": "2026-04-30T00:00:00+00:00",
                "related_event_ids": [],
                "briefing_ids": [],
                "delivery_task_ids": [],
                "metadata": {},
                "created_at": "2026-04-30T00:00:00+00:00",
                "updated_at": "2026-04-30T00:00:00+00:00",
            }
        ],
    )
    agent = AssistantAgent(
        storage=storage,
        intent_planner=FakePlanner("render_briefing_preview", {"view": "deep"}, "generate_briefing"),
    )

    response = agent.respond("生成深读简报", session_id="session-4")

    assert "# NextInAI 深读简报" in response.message
    assert "判断边界" in response.message


def test_assistant_agent_can_use_planner_for_task_listing(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "delivery_tasks",
        [
            {
                "task_id": "task-1",
                "channel": "email",
                "target": "default",
                "scope": "daily",
                "view": "flash",
                "schedule": "daily",
                "enabled": True,
                "created_at": "2026-04-30T00:00:00+00:00",
                "updated_at": "2026-04-30T00:00:00+00:00",
            }
        ],
    )
    agent = AssistantAgent(storage=storage, intent_planner=FakePlanner("get_delivery_tasks"))

    response = agent.respond("把我的任务给我看看", session_id="session-planner")

    assert "当前推送任务如下" in response.message


def test_assistant_agent_can_use_planner_for_reports_by_source(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "ai_report",
                "subject": "OpenAI News",
                "source_key": "OpenAI News",
                "signal_type": "report_publication",
                "title": "OpenAI models come to AWS",
                "url": "https://example.com/aws",
                "published_at": "2026-04-30T00:00:00+00:00",
                "summary_text": "OpenAI 正在强化企业分发。",
                "body_text": "这是渠道扩展信号。",
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
                "interpreted_summary": "OpenAI 正在强化企业分发。",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )
    agent = AssistantAgent(
        storage=storage,
        intent_planner=FakePlanner("get_report_events", {"source_name": "OpenAI News", "limit": 5}),
    )

    response = agent.respond("看看 OpenAI 最近的报告", session_id="session-source-report")

    assert "OpenAI models come to AWS" in response.message


def test_assistant_agent_reports_planner_failure(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "events",
        [
            {
                "event_id": "report_1",
                "event_type": "insight_event",
                "subject": "OpenAI News",
                "title": "OpenAI models come to AWS",
                "summary": "OpenAI 正在强化企业分发。",
                "rationale": "这是渠道扩展，不只是单篇新闻。",
                "source_refs": [],
                "tags": [],
                "novelty_score": 0.8,
                "relevance_score": 0.7,
                "impact_score": 0.7,
                "heat_score": 0.6,
                "confidence_score": 0.8,
                "importance_score": 0.73,
                "happened_at": "2026-04-30T00:00:00+00:00",
                "related_event_ids": [],
                "briefing_ids": [],
                "delivery_task_ids": [],
                "metadata": {},
                "created_at": "2026-04-30T00:00:00+00:00",
                "updated_at": "2026-04-30T00:00:00+00:00",
            }
        ],
    )
    agent = AssistantAgent(storage=storage, intent_planner=FailingPlanner())

    response = agent.respond("生成简报", session_id="session-planner-fallback")

    assert "planner 调度失败" in response.message


def test_assistant_agent_can_export_report_summary_from_chat(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXTINAI_REPORT_OUTPUT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "ai_report",
                "subject": "OpenAI News",
                "source_key": "OpenAI News",
                "signal_type": "report_publication",
                "title": "OpenAI models come to AWS",
                "url": "https://example.com/aws",
                "published_at": "2026-04-30T00:00:00+00:00",
                "summary_text": "OpenAI 正在强化企业分发。",
                "body_text": "这是渠道扩展信号。",
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
                "interpreted_summary": "OpenAI 正在强化企业分发。",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )
    agent = AssistantAgent(
        storage=storage,
        intent_planner=SequencedPlanner(
            [
                ("get_report_events", {"limit": 1}, "query_intelligence"),
                ("export_report_summary", {"source_name": "OpenAI News", "formats": ["pdf"]}, "export_intelligence"),
            ]
        ),
    )
    session_id = "session-export-report-summary"

    first = agent.respond("给我最近 1 篇报告", session_id=session_id)
    second = agent.respond("把刚才的报告导出成 pdf", session_id=session_id)

    assert "最值得注意" in first.message
    assert "报告摘要导出完成" in second.message
    assert ".pdf" in second.message
    get_settings.cache_clear()


def test_assistant_agent_can_export_report_detail_from_chat(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("NEXTINAI_REPORT_OUTPUT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "content_items",
        [
            {
                "source_kind": "ai_report",
                "subject": "OpenAI News",
                "source_key": "OpenAI News",
                "signal_type": "report_publication",
                "title": "OpenAI models come to AWS",
                "url": "https://example.com/aws",
                "published_at": "2026-04-30T00:00:00+00:00",
                "summary_text": "OpenAI 正在强化企业分发。",
                "body_text": "这是渠道扩展信号。",
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
                "interpreted_summary": "OpenAI 正在强化企业分发。",
                "evidence_json": [],
                "is_partial": False,
            }
        ],
    )
    agent = AssistantAgent(
        storage=storage,
        intent_planner=SequencedPlanner(
            [
                ("get_report_events", {"limit": 1}, "query_intelligence"),
                ("get_event_detail", {"reference_index": 1}, "explore_detail"),
                ("export_report", {"reference_index": 1, "formats": ["md"]}, "export_intelligence"),
            ]
        ),
    )
    session_id = "session-export-report-detail"

    first = agent.respond("给我最近 1 篇报告", session_id=session_id)
    detail = agent.respond("第 1 个详细讲讲", session_id=session_id)
    exported = agent.respond("导出这篇报告为 markdown", session_id=session_id)

    assert "最值得注意" in first.message
    assert "核心解读" in detail.message
    assert "报告详细解读导出完成" in exported.message
    assert ".md" in exported.message
    get_settings.cache_clear()
