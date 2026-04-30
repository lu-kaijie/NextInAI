from nextinai.agents.assistant import AssistantAgent
from nextinai.storage.files import FileStorage


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
    agent = AssistantAgent(storage=storage)
    session_id = "session-1"

    first = agent.respond("给我最近 1 篇报告", session_id=session_id)
    second = agent.respond("第 1 个详细讲讲", session_id=session_id)

    assert "最值得注意" in first.message
    assert "OpenAI models come to AWS" in second.message
    assert "核心解读" in second.message


def test_assistant_agent_requires_confirmation_for_side_effects(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    agent = AssistantAgent(storage=storage)
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
    agent = AssistantAgent(storage=storage)
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
    agent = AssistantAgent(storage=storage)

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
    agent = AssistantAgent(storage=storage)

    response = agent.respond("生成深读简报", session_id="session-4")

    assert "# NextInAI 深读简报" in response.message
    assert "判断边界" in response.message
