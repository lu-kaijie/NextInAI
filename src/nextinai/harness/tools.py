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
    intent: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Any
    requires_confirmation: bool = False

    def execute(self, context: RunContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.handler(context, tool_input)


@dataclass(slots=True)
class ActionTool:
    name: str
    description: str
    intent: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: Any
    requires_confirmation: bool = True

    def execute(self, context: RunContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        return self.handler(context, tool_input)


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
            intent="query_intelligence",
            input_schema={"window": "daily|7d|30d", "limit": "int"},
            output_schema={"events": "list"},
            handler=lambda context, payload: {"events": capability.get_trending_events(payload["window"], payload["limit"])},
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_repo_update_events",
            description="查询已采集仓库在指定窗口内的更新事件。",
            intent="query_intelligence",
            input_schema={"repository": "owner/name", "hours": "int"},
            output_schema={"events": "list"},
            handler=lambda context, payload: {
                "events": capability.get_repo_update_events(payload["repository"], payload["hours"])
            },
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_report_events",
            description="查询已采集 AI 公司/论坛报告的解读事件。",
            intent="query_intelligence",
            input_schema={"source_name": "optional str", "limit": "int"},
            output_schema={"events": "list"},
            handler=lambda context, payload: {
                "events": capability.get_report_events(
                    source_name=payload.get("source_name"),
                    limit=payload["limit"],
                )
            },
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_event_detail",
            description="从已持久化事件集合里读取单个事件详情。",
            intent="explore_detail",
            input_schema={"event_id": "str"},
            output_schema={"event": "dict|null"},
            handler=lambda context, payload: {"event": capability.get_event_detail(payload["event_id"])},
        )
    )
    registry.register(
        QueryEventsTool(
            name="resolve_event_reference",
            description="把上一轮结果中的 reference_index 解析为真实 event_id，用于后续详情查看或导出。",
            intent="resolve_reference",
            input_schema={"reference_index": "int"},
            output_schema={"resolved": "bool", "event_id": "optional str", "message": "str"},
            handler=lambda context, payload: _resolve_event_reference(storage, context, payload["reference_index"]),
        )
    )
    registry.register(
        QueryEventsTool(
            name="resolve_delivery_task_reference",
            description="把上一轮任务列表中的 reference_index 解析为真实 task_id，用于删除任务。",
            intent="resolve_reference",
            input_schema={"reference_index": "int"},
            output_schema={"resolved": "bool", "task_id": "optional str", "message": "str"},
            handler=lambda context, payload: _resolve_delivery_task_reference(storage, context, payload["reference_index"]),
        )
    )
    registry.register(
        QueryEventsTool(
            name="prepare_briefing_context",
            description="基于当前会话最近关注的事件准备简报上下文，返回 scope、view 和可直接渲染的 events。",
            intent="resolve_reference",
            input_schema={"scope": "str", "view": "flash|deep|conversation"},
            output_schema={"resolved": "bool", "scope": "str", "view": "str", "events": "list", "message": "str"},
            handler=lambda context, payload: _prepare_briefing_context(storage, context, payload["scope"], payload["view"]),
        )
    )
    registry.register(
        QueryEventsTool(
            name="prepare_report_export",
            description="把 event_id 或上一轮结果编号解析为 report_id，用于导出单条报告详细解读。",
            intent="resolve_reference",
            input_schema={
                "reference_index": "optional int",
                "event_id": "optional str",
                "report_id": "optional str",
            },
            output_schema={"resolved": "bool", "report_id": "optional str", "message": "str"},
            handler=lambda context, payload: _prepare_report_export(storage, context, payload),
        )
    )
    registry.register(
        QueryEventsTool(
            name="get_recent_briefings",
            description="读取最近生成的简报记录。",
            intent="query_intelligence",
            input_schema={"scope": "optional str"},
            output_schema={"briefings": "list"},
            handler=lambda context, payload: {
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
            intent="query_intelligence",
            input_schema={},
            output_schema={"tasks": "list"},
            handler=lambda context, payload: {"tasks": capability.list_delivery_tasks()},
        )
    )
    registry.register(
        QueryEventsTool(
            name="generate_briefing",
            description="根据传入事件集合生成快讯版简报对象。",
            intent="generate_briefing",
            input_schema={"scope": "str", "view": "optional flash|deep|conversation", "events": "list"},
            output_schema={"briefing": "dict"},
            handler=lambda context, payload: {
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
            intent="generate_briefing",
            input_schema={"scope": "str", "view": "flash|deep|conversation", "events": "list"},
            output_schema={"markdown": "str"},
            handler=lambda context, payload: {
                "markdown": capability.render_briefing_preview(
                    payload["scope"],
                    payload["view"],
                    payload["events"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="deliver_briefing",
            description="通过通知服务发送简报。",
            intent="execute_action",
            input_schema={"channel": "email|webhook", "scope": "str", "target": "str"},
            output_schema={"message": "str"},
            handler=lambda context, payload: {
                "message": capability.send_notification(
                    channel=payload["channel"],
                    content_kind="digest",
                    scope=payload["scope"],
                    target=payload["target"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="add_subscription",
            description="新增一个 GitHub 仓库订阅。",
            intent="execute_action",
            input_schema={"repository": "owner/name", "lookback_hours": "int", "refresh_minutes": "int"},
            output_schema={"repository": "str"},
            handler=lambda context, payload: {
                "repository": capability.add_subscription(
                    payload["repository"],
                    payload["lookback_hours"],
                    payload["refresh_minutes"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="create_delivery_task",
            description="创建一个本地定时推送任务记录。",
            intent="execute_action",
            input_schema={
                "channel": "email|webhook",
                "target": "str",
                "scope": "daily|7d|30d",
                "view": "flash|deep|conversation",
                "schedule": "hourly|daily|weekly",
            },
            output_schema={"task": "dict"},
            handler=lambda context, payload: {
                "task": capability.create_delivery_task(
                    channel=payload["channel"],
                    target=payload["target"],
                    scope=payload["scope"],
                    view=payload["view"],
                    schedule=payload["schedule"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="delete_delivery_task",
            description="删除一个本地定时推送任务记录。",
            intent="execute_action",
            input_schema={"task_id": "str"},
            output_schema={"deleted": "bool"},
            handler=lambda context, payload: {"deleted": capability.delete_delivery_task(payload["task_id"])},
        )
    )
    registry.register(
        ActionTool(
            name="export_repository_summary",
            description="导出单仓库更新摘要。",
            intent="export_intelligence",
            input_schema={"repository": "owner/name", "hours": "int", "formats": "list[md|pdf]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda context, payload: {
                "exports": capability.export_repository_summary(
                    payload["repository"],
                    payload["hours"],
                    payload["formats"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="export_trending",
            description="导出热门榜分析结果。",
            intent="export_intelligence",
            input_schema={"window": "daily|7d|30d", "limit": "int", "formats": "list[md|pdf]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda context, payload: {
                "exports": capability.export_trending(
                    payload["window"],
                    payload["limit"],
                    payload["formats"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="export_report",
            description="导出单条报告详细解读。",
            intent="export_intelligence",
            input_schema={"report_id": "str", "formats": "list[md|pdf]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda context, payload: {
                "exports": capability.export_report(
                    payload["report_id"],
                    payload["formats"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="export_report_summary",
            description="导出报告摘要列表。",
            intent="export_intelligence",
            input_schema={"source_name": "optional str", "limit": "int", "formats": "list[md|pdf]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda context, payload: {
                "exports": capability.export_report_summary(
                    payload.get("source_name"),
                    payload["limit"],
                    payload["formats"],
                )
            },
        )
    )
    registry.register(
        ActionTool(
            name="export_digest",
            description="导出简报或 briefing。",
            intent="export_intelligence",
            input_schema={"scope": "daily|7d|30d", "formats": "list[md|pdf]"},
            output_schema={"exports": "dict"},
            requires_confirmation=False,
            handler=lambda context, payload: {
                "exports": capability.export_digest(
                    payload["scope"],
                    payload["formats"],
                )
            },
        )
    )
    return registry


def _load_session_state(storage: FileStorage, session_id: str | None) -> dict[str, Any]:
    if not session_id:
        return {}
    for row in storage.load_collection("session_states"):
        if row.get("session_id") == session_id:
            return row
    return {}


def _resolve_event_reference(storage: FileStorage, context: RunContext, reference_index: int) -> dict[str, Any]:
    state = _load_session_state(storage, context.session_id)
    reference_map = dict(state.get("reference_map") or {})
    event_id = reference_map.get(str(reference_index))
    if not event_id:
        return {
            "resolved": False,
            "message": "没有定位到对应事件。请先获取列表，或改为提供明确的 event_id。",
            "reference_index": reference_index,
        }
    event = _find_event_by_id(storage, event_id)
    return {
        "resolved": True,
        "reference_index": reference_index,
        "event_id": event_id,
        "report_id": _extract_report_id_from_event(event),
        "message": f"已解析第 {reference_index} 项对应的 event_id。",
    }


def _resolve_delivery_task_reference(storage: FileStorage, context: RunContext, reference_index: int) -> dict[str, Any]:
    state = _load_session_state(storage, context.session_id)
    reference_map = dict(state.get("reference_map") or {})
    task_id = reference_map.get(str(reference_index))
    if not task_id:
        return {
            "resolved": False,
            "message": "没有定位到对应任务。请先列出任务，或改为提供明确的 task_id。",
            "reference_index": reference_index,
        }
    return {
        "resolved": True,
        "reference_index": reference_index,
        "task_id": task_id,
        "message": f"已解析第 {reference_index} 个任务对应的 task_id。",
    }


def _prepare_briefing_context(storage: FileStorage, context: RunContext, scope: str, view: str) -> dict[str, Any]:
    state = _load_session_state(storage, context.session_id)
    last_event_ids = list(state.get("last_event_ids") or [])
    persisted_events = {row["event_id"]: row for row in storage.load_collection("events") if row.get("event_id")}
    event_rows = [persisted_events[event_id] for event_id in last_event_ids if event_id in persisted_events][:5]
    if not event_rows:
        event_rows = list(persisted_events.values())[-5:]
    if not event_rows:
        return {
            "resolved": False,
            "scope": scope,
            "view": view,
            "events": [],
            "message": "当前没有可用于生成简报的事件，请先查询热门榜、仓库更新或报告列表。",
        }
    return {
        "resolved": True,
        "scope": scope,
        "view": view,
        "events": event_rows,
        "event_ids": [row["event_id"] for row in event_rows],
        "message": f"已准备 {len(event_rows)} 条事件，可直接生成简报。",
    }


def _prepare_report_export(storage: FileStorage, context: RunContext, payload: dict[str, Any]) -> dict[str, Any]:
    report_id = payload.get("report_id")
    if isinstance(report_id, str) and report_id.strip():
        normalized = report_id if report_id.startswith("report:") else f"report:{report_id}"
        return {
            "resolved": True,
            "report_id": normalized,
            "message": "已确认报告导出目标。",
        }
    event_id = payload.get("event_id")
    if isinstance(event_id, str) and event_id.strip():
        event = _find_event_by_id(storage, event_id)
        resolved_report_id = _extract_report_id_from_event(event)
        if resolved_report_id:
            return {
                "resolved": True,
                "event_id": event_id,
                "report_id": resolved_report_id,
                "message": "已从 event_id 解析出 report_id。",
            }
    reference_index = payload.get("reference_index")
    if isinstance(reference_index, int):
        resolved = _resolve_event_reference(storage, context, reference_index)
        event_id = resolved.get("event_id")
        if isinstance(event_id, str):
            event = _find_event_by_id(storage, event_id)
            resolved_report_id = _extract_report_id_from_event(event)
            if resolved_report_id:
                return {
                    "resolved": True,
                    "reference_index": reference_index,
                    "event_id": event_id,
                    "report_id": resolved_report_id,
                    "message": "已从上一轮结果解析出 report_id。",
                }
    return {
        "resolved": False,
        "message": "没有定位到可导出的报告对象。请先解析事件引用，或直接提供 report_id。",
    }


def _find_event_by_id(storage: FileStorage, event_id: str) -> dict[str, Any] | None:
    return next(
        (row for row in storage.load_collection("events") if row.get("event_id") == event_id),
        None,
    )


def _extract_report_id_from_event(event: dict[str, Any] | None) -> str | None:
    if not event:
        return None
    for ref in event.get("source_refs") or []:
        analysis_ref = ref.get("analysis_ref")
        if isinstance(analysis_ref, str) and analysis_ref.startswith("report:"):
            return analysis_ref
        content_ref = ref.get("content_ref")
        if isinstance(content_ref, str) and content_ref:
            return f"report:{content_ref}"
    return None


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
