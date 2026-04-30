from nextinai.harness.adapters import BriefingViewBuilder, MigrationGuide
from nextinai.harness.models import IntelligenceEvent


def _sample_event(event_id: str = "event-1") -> IntelligenceEvent:
    return IntelligenceEvent(
        event_id=event_id,
        event_type="trend_event",
        subject="mattpocock/skills",
        title="mattpocock/skills",
        summary="一个围绕 AI 工程技能和工作流的仓库。",
        rationale="作者影响力强，且主题贴合当前 AI agent 热点。",
        novelty_score=0.8,
        relevance_score=0.75,
        impact_score=0.7,
        heat_score=0.9,
        confidence_score=0.88,
        importance_score=0.79,
    )


def test_briefing_view_builder_supports_deep_and_conversation_views() -> None:
    builder = BriefingViewBuilder()
    events = [_sample_event()]

    deep = builder.build_briefing(scope="daily", view="deep", events=events)
    conversation = builder.build_briefing(scope="daily", view="conversation", events=events)

    assert "深读简报" in deep.title
    assert "判断边界" in deep.content_markdown
    assert "对话视图" in conversation.title
    assert "第 1 个详细讲讲" in conversation.content_markdown


def test_migration_guide_lists_reuse_items_and_pipeline() -> None:
    items = MigrationGuide.direct_reuse_items()
    steps = MigrationGuide.event_pipeline_steps()

    assert any(item["capability"] == "deliver_briefing" for item in items)
    assert "IntelligenceEventAdapter 将模块输出提升为事件级对象" in steps
