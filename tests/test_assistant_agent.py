import json
from dataclasses import dataclass
from typing import Callable

from nextinai.agents.assistant import AssistantAgent
from nextinai.core.config import get_settings
from nextinai.storage.files import FileStorage


@dataclass
class _FakeFunction:
    name: str
    arguments: str


@dataclass
class _FakeToolCall:
    id: str
    function: _FakeFunction | None
    type: str = "function"


@dataclass
class _FakeMessage:
    tool_calls: list[_FakeToolCall] | None = None
    content: str | None = None


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeCompletion:
    choices: list[_FakeChoice]


def _has_tool_result(messages: list[dict]) -> bool:
    return any(message.get("role") == "tool" for message in messages)


ToolInputFactory = dict | Callable[[list[dict]], dict]


def _last_tool_output(messages: list[dict]) -> dict:
    for message in reversed(messages):
        if message.get("role") == "tool":
            return json.loads(message.get("content") or "{}")
    return {}


class ScriptedPlanner:
    def __init__(self, turns: list[list[tuple[str, ToolInputFactory | None, str]]]) -> None:
        self.turns = turns
        self.turn_index = -1

    def build_messages(self, *, message: str, state) -> list[dict]:
        self.turn_index += 1
        return [{"role": "user", "content": message}]

    def create_completion(self, messages) -> _FakeCompletion:
        current_turn = self.turns[min(self.turn_index, len(self.turns) - 1)]
        executed_tools = sum(1 for message in messages if message.get("role") == "tool")
        if executed_tools >= len(current_turn):
            return _FakeCompletion(choices=[_FakeChoice(message=_FakeMessage(tool_calls=None, content=""))])
        tool_name, raw_tool_input, intent = current_turn[executed_tools]
        tool_input = raw_tool_input(messages) if callable(raw_tool_input) else dict(raw_tool_input or {})
        return _FakeCompletion(
            choices=[
                _FakeChoice(
                    message=_FakeMessage(
                        tool_calls=[
                            _FakeToolCall(
                                id=f"fake-call-{self.turn_index + 1}-{executed_tools + 1}",
                                function=_FakeFunction(
                                    name=tool_name,
                                    arguments=json.dumps(
                                        {
                                            **tool_input,
                                            "__test_intent": intent,
                                        },
                                        ensure_ascii=False,
                                    ),
                                ),
                            )
                        ]
                    )
                )
            ]
        )


class FailingPlanner:
    def build_messages(self, *, message: str, state) -> list[dict]:
        return [{"role": "user", "content": message}]

    def create_completion(self, messages) -> _FakeCompletion:
        if _has_tool_result(messages):
            return _FakeCompletion(choices=[_FakeChoice(message=_FakeMessage(tool_calls=None, content=""))])
        raise RuntimeError("planner unavailable")


class SequencedPlanner:
    def __init__(self, turns: list[list[tuple[str, ToolInputFactory | None, str]]]) -> None:
        self.delegate = ScriptedPlanner(turns)

    def build_messages(self, *, message: str, state) -> list[dict]:
        return self.delegate.build_messages(message=message, state=state)

    def create_completion(self, messages) -> _FakeCompletion:
        return self.delegate.create_completion(messages)


class FakePlanner(SequencedPlanner):
    def __init__(self, tool_name: str, tool_input: dict | None = None, intent: str = "query_intelligence") -> None:
        super().__init__([[(tool_name, tool_input or {}, intent)]])


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
                [("get_report_events", {"limit": 1}, "query_intelligence")],
                [
                    ("resolve_event_reference", {"reference_index": 1}, "resolve_reference"),
                    ("get_event_detail", lambda messages: {"event_id": _last_tool_output(messages)["event_id"]}, "explore_detail"),
                ],
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
                [("get_report_events", {"limit": 3}, "query_intelligence")],
                [
                    ("resolve_event_reference", {"reference_index": 3}, "resolve_reference"),
                    ("get_event_detail", lambda messages: {"event_id": _last_tool_output(messages)["event_id"]}, "explore_detail"),
                ],
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
    agent = AssistantAgent(storage=storage, intent_planner=FakePlanner("resolve_event_reference", {"reference_index": 3}))

    response = agent.respond("第三个详细讲讲", session_id="session-missing-ref")

    assert "没有定位到对应事件" in response.message


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
        intent_planner=FakePlanner("export_trending", {"window": "daily", "limit": 5}),
    )

    response = agent.respond("导出热门榜", session_id="session-missing-export-format")

    assert "缺少必填参数：formats" in response.message
    assert response.raw_outputs["error"]["error_type"] == "missing_required_field"


def test_assistant_agent_requires_confirmation_for_side_effects(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    agent = AssistantAgent(
        storage=storage,
        intent_planner=FakePlanner(
            "add_subscription",
            {"repository": "openai/openai-python", "lookback_hours": 24, "refresh_minutes": 60},
        ),
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
                [("get_delivery_tasks", {}, "query_intelligence")],
                [
                    ("resolve_delivery_task_reference", {"reference_index": 1}, "resolve_reference"),
                    (
                        "delete_delivery_task",
                        lambda messages: {"task_id": _last_tool_output(messages)["task_id"]},
                        "execute_action",
                    ),
                ],
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
        intent_planner=SequencedPlanner(
            [
                [
                    ("prepare_briefing_context", {"scope": "daily", "view": "flash"}, "resolve_reference"),
                    (
                        "render_briefing_preview",
                        lambda messages: {
                            "scope": _last_tool_output(messages)["scope"],
                            "view": _last_tool_output(messages)["view"],
                            "events": _last_tool_output(messages)["events"],
                        },
                        "generate_briefing",
                    ),
                ]
            ]
        ),
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
        intent_planner=SequencedPlanner(
            [
                [
                    ("prepare_briefing_context", {"scope": "daily", "view": "deep"}, "resolve_reference"),
                    (
                        "render_briefing_preview",
                        lambda messages: {
                            "scope": _last_tool_output(messages)["scope"],
                            "view": _last_tool_output(messages)["view"],
                            "events": _last_tool_output(messages)["events"],
                        },
                        "generate_briefing",
                    ),
                ]
            ]
        ),
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


def test_assistant_agent_stops_on_repeated_tool_call(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    agent = AssistantAgent(
        storage=storage,
        intent_planner=SequencedPlanner(
            [
                [
                    ("get_delivery_tasks", {}, "query_intelligence"),
                    ("get_delivery_tasks", {}, "query_intelligence"),
                ]
            ]
        ),
    )

    response = agent.respond("列出任务", session_id="session-repeat-guard")

    assert "重复工具调用" in response.message


def test_assistant_agent_stops_when_step_limit_is_hit(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    agent = AssistantAgent(
        storage=storage,
        intent_planner=SequencedPlanner(
            [
                [
                    ("resolve_event_reference", {"reference_index": 1}, "resolve_reference"),
                    ("resolve_event_reference", {"reference_index": 2}, "resolve_reference"),
                    ("resolve_event_reference", {"reference_index": 3}, "resolve_reference"),
                    ("resolve_event_reference", {"reference_index": 4}, "resolve_reference"),
                    ("resolve_event_reference", {"reference_index": 5}, "resolve_reference"),
                    ("resolve_event_reference", {"reference_index": 6}, "resolve_reference"),
                    ("resolve_event_reference", {"reference_index": 7}, "resolve_reference"),
                    ("resolve_event_reference", {"reference_index": 8}, "resolve_reference"),
                ]
            ]
        ),
    )

    response = agent.respond("把最近结果逐个展开", session_id="session-step-limit")

    assert "最大步数限制" in response.message


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
                [("get_report_events", {"limit": 1}, "query_intelligence")],
                [
                    (
                        "export_report_summary",
                        {"source_name": "OpenAI News", "limit": 1, "formats": ["pdf"]},
                        "export_intelligence",
                    )
                ],
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
                [("get_report_events", {"limit": 1}, "query_intelligence")],
                [
                    ("resolve_event_reference", {"reference_index": 1}, "resolve_reference"),
                    ("get_event_detail", lambda messages: {"event_id": _last_tool_output(messages)["event_id"]}, "explore_detail"),
                ],
                [
                    ("prepare_report_export", {"reference_index": 1}, "resolve_reference"),
                    (
                        "export_report",
                        lambda messages: {"report_id": _last_tool_output(messages)["report_id"], "formats": ["md"]},
                        "export_intelligence",
                    ),
                ],
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
