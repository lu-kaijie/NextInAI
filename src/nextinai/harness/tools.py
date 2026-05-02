"""Controlled tool layer for the intelligence harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nextinai.core.config import get_settings
from nextinai.harness.adapters import BriefingViewBuilder, IntelligenceEventAdapter
from nextinai.harness.models import RunContext
from nextinai.harness.runtime import Tool, ToolRegistry
from nextinai.services.registry import ServiceRegistry, build_service_registry
from nextinai.services.task_store import DeliveryTaskStore
from nextinai.storage.files import FileStorage, ensure_workspace


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


@dataclass(slots=True)
class QueryEventsTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Any
    requires_confirmation: bool = False

    def execute(self, context: RunContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.handler(tool_input)


@dataclass(slots=True)
class ActionTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Any
    requires_confirmation: bool = True

    def execute(self, context: RunContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.handler(tool_input)


def build_harness_tool_registry(
    *,
    service_registry: ServiceRegistry | None = None,
    storage: FileStorage | None = None,
    event_adapter: IntelligenceEventAdapter | None = None,
) -> ToolRegistry:
    """Build the first minimal harness toolset."""

    services = service_registry or build_service_registry()
    capability = services.capability_service
    storage = storage or _build_storage()
    event_adapter = event_adapter or IntelligenceEventAdapter(storage=storage)
    briefing_builder = BriefingViewBuilder()

    registry = ToolRegistry()

    registry.register(
        QueryEventsTool(
            name="get_trending_events",
            description="查询 GitHub 热门榜并返回结构化热门事件。",
            input_schema={"window": "daily|7d|30d", "limit": "int"},
            output_schema={"events": "list"},
            handler=lambda payload: {"events": capability.get_trending_events(payload["window"], payload.get("limit", 10))},
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_repo_update_events",
            description="查询已采集仓库在指定窗口内的更新事件。",
            input_schema={"repository": "owner/name", "hours": "int"},
            output_schema={"events": "list"},
            handler=lambda payload: {
                "events": capability.get_repo_update_events(payload["repository"], payload.get("hours", 24))
            },
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_report_events",
            description="查询已采集 AI 公司/论坛报告的解读事件。",
            input_schema={"source_name": "optional str", "limit": "int"},
            output_schema={"events": "list"},
            handler=lambda payload: {
                "events": capability.get_report_events(
                    source_name=payload.get("source_name"),
                    limit=payload.get("limit", 10),
                )
            },
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_event_detail",
            description="从已持久化事件集合里读取单个事件详情。",
            input_schema={"event_id": "str"},
            output_schema={"event": "dict|null"},
            handler=lambda payload: {"event": capability.get_event_detail(payload["event_id"])},
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_recent_briefings",
            description="读取最近生成的简报记录。",
            input_schema={"scope": "optional str"},
            output_schema={"briefings": "list"},
            handler=lambda payload: {
                "briefings": [
                    row
                    for row in storage.load_collection("digests")
                    if payload.get("scope") is None or row.get("scope") == payload.get("scope")
                ][-10:]
            },
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_delivery_tasks",
            description="读取当前已定义的定时交付任务。",
            input_schema={},
            output_schema={"tasks": "list"},
            handler=lambda payload: {"tasks": capability.list_delivery_tasks()},
        )
    )
    registry.register(
        QueryEventsTool(
            name="generate_briefing",
            description="根据传入事件集合生成快讯版简报对象。",
            input_schema={"scope": "str", "view": "flash|deep|conversation", "events": "list"},
            output_schema={"briefing": "dict"},
            handler=lambda payload: {
                "briefing": briefing_builder.build_briefing(
                    scope=payload["scope"],
                    view=payload.get("view", "flash"),
                    events=[_event_from_dict(item) for item in payload["events"]],
                ).to_dict()
            },
        )
    )
    registry.register(
        QueryEventsTool(
            name="render_briefing_preview",
            description="根据事件查询结果直接生成 Markdown 快览。",
            input_schema={"scope": "str", "view": "flash|deep|conversation", "events": "list"},
            output_schema={"markdown": "str"},
            handler=lambda payload: {
                "markdown": capability.render_briefing_preview(
                    payload["scope"],
                    payload.get("view", "flash"),
                    payload["events"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="deliver_briefing",
            description="通过通知服务发送简报。",
            input_schema={"channel": "email|webhook", "scope": "str", "target": "optional str"},
            output_schema={"message": "str"},
            handler=lambda payload: {
                "message": capability.send_notification(
                    channel=payload["channel"],
                    content_kind="digest",
                    scope=payload.get("scope", "daily"),
                    target=payload.get("target"),
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="add_subscription",
            description="新增一个 GitHub 仓库订阅。",
            input_schema={"repository": "owner/name", "lookback_hours": "int", "refresh_minutes": "int"},
            output_schema={"repository": "str"},
            handler=lambda payload: {
                "repository": capability.add_subscription(
                    payload["repository"],
                    payload.get("lookback_hours", 24),
                    payload.get("refresh_minutes", 60),
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="create_delivery_task",
            description="创建一个本地定时推送任务记录。",
            input_schema={"channel": "email|webhook", "target": "str", "scope": "str", "view": "str", "schedule": "str"},
            output_schema={"task": "dict"},
            handler=lambda payload: {
                "task": capability.create_delivery_task(
                    channel=payload["channel"],
                    target=payload["target"],
                    scope=payload.get("scope", "daily"),
                    view=payload.get("view", "flash"),
                    schedule=payload.get("schedule"),
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="delete_delivery_task",
            description="删除一个本地定时推送任务记录。",
            input_schema={"task_id": "str"},
            output_schema={"deleted": "bool"},
            handler=lambda payload: {"deleted": capability.delete_delivery_task(payload["task_id"])},
        )
    )
    registry.register(
        ActionTool(
            name="export_repository_summary",
            description="导出单仓库更新摘要。",
            input_schema={"repository": "owner/name", "hours": "int", "formats": "list[str]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda payload: {
                "exports": capability.export_repository_summary(
                    payload["repository"],
                    payload.get("hours", 168),
                    payload.get("formats", ["md"]),
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="export_trending",
            description="导出热门榜分析结果。",
            input_schema={"window": "str", "limit": "int", "formats": "list[str]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda payload: {
                "exports": capability.export_trending(
                    payload.get("window", "daily"),
                    payload.get("limit", 5),
                    payload.get("formats", ["md"]),
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="export_report",
            description="导出单条报告详细解读。",
            input_schema={"report_id": "str", "formats": "list[str]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda payload: {
                "exports": capability.export_report(
                    payload["report_id"],
                    payload.get("formats", ["md"]),
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="export_report_summary",
            description="导出报告摘要列表。",
            input_schema={"source_name": "optional str", "limit": "int", "formats": "list[str]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda payload: {
                "exports": capability.export_report_summary(
                    payload.get("source_name"),
                    payload.get("limit", 10),
                    payload.get("formats", ["md"]),
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="export_digest",
            description="导出简报或 briefing。",
            input_schema={"scope": "str", "formats": "list[str]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda payload: {
                "exports": capability.export_digest(
                    payload.get("scope", "daily"),
                    payload.get("formats", ["md"]),
                )
            },
        )
    )
    return registry


def _event_from_dict(payload: dict[str, Any]):
    from nextinai.harness.models import IntelligenceEvent, SourceReference

    return IntelligenceEvent(
        event_id=payload["event_id"],
        event_type=payload["event_type"],
        subject=payload["subject"],
        title=payload["title"],
        summary=payload["summary"],
        rationale=payload["rationale"],
        source_refs=[SourceReference(**ref) for ref in payload.get("source_refs") or []],
        tags=list(payload.get("tags") or []),
        novelty_score=float(payload.get("novelty_score", 0.0)),
        relevance_score=float(payload.get("relevance_score", 0.0)),
        impact_score=float(payload.get("impact_score", 0.0)),
        heat_score=float(payload.get("heat_score", 0.0)),
        confidence_score=float(payload.get("confidence_score", 0.0)),
        importance_score=float(payload.get("importance_score", 0.0)),
        happened_at=payload.get("happened_at"),
        related_event_ids=list(payload.get("related_event_ids") or []),
        briefing_ids=list(payload.get("briefing_ids") or []),
        delivery_task_ids=list(payload.get("delivery_task_ids") or []),
        metadata=dict(payload.get("metadata") or {}),
        created_at=payload.get("created_at"),
        updated_at=payload.get("updated_at"),
    )
