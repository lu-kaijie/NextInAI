"""Controlled assistant agent for the intelligence harness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from nextinai.core.config import get_settings
from nextinai.harness.models import AssistantResponse, RunContext, SessionState
from nextinai.harness.runtime import ExecutionEngine, FileSessionStateStore
from nextinai.harness.tools import build_harness_tool_registry
from nextinai.services.registry import ServiceRegistry, build_service_registry
from nextinai.storage.files import FileStorage, ensure_workspace


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


@dataclass(slots=True)
class ResolvedReference:
    kind: str
    value: str


@dataclass(slots=True)
class IntentDecision:
    intent: str
    tool_name: str
    tool_input: dict[str, Any]
    requires_confirmation: bool = False


class AssistantAgent:
    """A controlled agent that routes natural language to harness tools."""

    def __init__(
        self,
        *,
        storage: FileStorage | None = None,
        service_registry: ServiceRegistry | None = None,
        execution_engine: ExecutionEngine | None = None,
        session_store: FileSessionStateStore | None = None,
    ) -> None:
        self.storage = storage or _build_storage()
        self.services = service_registry or build_service_registry()
        self.tool_registry = build_harness_tool_registry(
            service_registry=self.services,
            storage=self.storage,
        )
        self.execution_engine = execution_engine or ExecutionEngine(
            tool_registry=self.tool_registry,
            storage=self.storage,
        )
        self.session_store = session_store or FileSessionStateStore(self.storage)

    def respond(
        self,
        message: str,
        *,
        session_id: str | None = None,
        actor_id: str | None = None,
        confirmed: bool = False,
    ) -> AssistantResponse:
        text = message.strip()
        session_id = session_id or f"chat-{uuid4()}"
        state = self.session_store.load(session_id)

        if self._is_confirmation_message(text):
            return self._handle_confirmation(text, state, actor_id=actor_id)

        decision = self._decide_intent(text, state)
        context = RunContext.create(
            trigger_type="chat",
            session_id=session_id,
            actor_id=actor_id,
            intent=decision.intent,
            model_config={"provider": get_settings().ai_provider, "model": get_settings().ai_model},
            allowed_tools=[decision.tool_name],
            metadata={"user_message": text},
        )
        result = self.execution_engine.execute_tool(
            context,
            decision.tool_name,
            decision.tool_input,
            confirmed=confirmed,
            user_input=text,
        )
        response = self._build_response(decision, result.output, state)
        self._update_session_state(state, decision, response, result.output)
        self.session_store.save(state)
        return response

    def _handle_confirmation(
        self,
        text: str,
        state: SessionState,
        *,
        actor_id: str | None,
    ) -> AssistantResponse:
        if not state.pending_tool_name or not state.pending_tool_input:
            return AssistantResponse(message="当前没有等待确认的动作。")
        if text.lower() in {"取消", "cancel", "no", "n", "不用", "算了"}:
            state.pending_action = None
            state.pending_tool_name = None
            state.pending_tool_input = None
            self.session_store.save(state)
            return AssistantResponse(message="已取消待执行动作。")

        context = RunContext.create(
            trigger_type="chat",
            session_id=state.session_id,
            actor_id=actor_id,
            intent=state.pending_action or "execute_action",
            model_config={"provider": get_settings().ai_provider, "model": get_settings().ai_model},
            allowed_tools=[state.pending_tool_name],
            metadata={"confirmation": True},
        )
        result = self.execution_engine.execute_tool(
            context,
            state.pending_tool_name,
            state.pending_tool_input,
            confirmed=True,
            user_input=text,
        )
        message = result.output.get("message")
        if not message and "task" in result.output:
            task = result.output["task"]
            message = f"已创建任务：{task['task_id']} -> {task['channel']} {task['target']}"
        if not message and "repository" in result.output:
            message = f"已新增订阅：{result.output['repository']}"
        if not message and "deleted" in result.output:
            message = "已删除任务。" if result.output["deleted"] else "未找到要删除的任务。"

        state.pending_action = None
        state.pending_tool_name = None
        state.pending_tool_input = None
        state.updated_at = context.created_at
        self.session_store.save(state)
        return AssistantResponse(message=message or "动作已执行。", raw_outputs=result.output)

    def _decide_intent(self, text: str, state: SessionState) -> IntentDecision:
        normalized = text.lower()
        if any(keyword in normalized for keyword in ["发邮件", "发到邮箱", "发送邮箱", "webhook", "发送通知", "发出去"]):
            tool_input = self._build_delivery_input(text, state)
            return IntentDecision(
                intent="execute_action",
                tool_name="deliver_briefing",
                tool_input=tool_input,
                requires_confirmation=True,
            )
        if any(keyword in normalized for keyword in ["定时", "订阅推送", "创建任务", "每天发", "每周发"]):
            tool_input = self._build_task_input(text)
            return IntentDecision(
                intent="execute_action",
                tool_name="create_delivery_task",
                tool_input=tool_input,
                requires_confirmation=True,
            )
        if ("任务" in normalized and any(keyword in normalized for keyword in ["删除", "删掉", "取消"])) or any(
            keyword in normalized for keyword in ["删除任务", "删任务", "取消任务"]
        ):
            task_id = self._resolve_task_reference(text, state)
            return IntentDecision(
                intent="execute_action",
                tool_name="delete_delivery_task",
                tool_input={"task_id": task_id},
                requires_confirmation=True,
            )
        if any(keyword in normalized for keyword in ["任务列表", "列出任务", "我的任务", "推送任务"]):
            return IntentDecision(
                intent="query_intelligence",
                tool_name="get_delivery_tasks",
                tool_input={},
            )
        if any(keyword in normalized for keyword in ["订阅仓库", "关注仓库", "添加订阅", "追踪仓库"]):
            repository = self._extract_repository(text)
            return IntentDecision(
                intent="execute_action",
                tool_name="add_subscription",
                tool_input={"repository": repository, "lookback_hours": 24, "refresh_minutes": 60},
                requires_confirmation=True,
            )
        if any(
            keyword in normalized
            for keyword in ["生成简报", "生成深读简报", "生成对话简报", "生成报告", "来个简报", "整理成简报", "深读简报"]
        ):
            return IntentDecision(
                intent="generate_briefing",
                tool_name="render_briefing_preview",
                tool_input=self._build_briefing_input(state, text),
            )
        if self._looks_like_detail_request(normalized):
            ref = self._resolve_reference(text, state)
            if ref and ref.kind == "event":
                return IntentDecision(
                    intent="explore_detail",
                    tool_name="get_event_detail",
                    tool_input={"event_id": ref.value},
                )

        if "报告" in text or "news" in normalized or "openai" in normalized or "anthropic" in normalized:
            return IntentDecision(
                intent="query_intelligence",
                tool_name="get_report_events",
                tool_input={"limit": self._extract_limit(text) or 5},
            )
        if any(keyword in normalized for keyword in ["热门", "最火", "trending", "排行榜", "上榜"]):
            return IntentDecision(
                intent="query_intelligence",
                tool_name="get_trending_events",
                tool_input={"window": self._extract_window(text), "limit": self._extract_limit(text) or 5},
            )
        repository = self._extract_repository(text, required=False)
        if repository:
            return IntentDecision(
                intent="query_intelligence",
                tool_name="get_repo_update_events",
                tool_input={"repository": repository, "hours": self._extract_hours(text) or 168},
            )
        return IntentDecision(
            intent="query_intelligence",
            tool_name="get_trending_events",
            tool_input={"window": "daily", "limit": 5},
        )

    @staticmethod
    def _looks_like_detail_request(normalized: str) -> bool:
        return bool(
            re.search(r"第\s*\d+\s*个", normalized)
            or any(keyword in normalized for keyword in ["详细", "展开", "继续讲", "继续说", "刚才那篇", "那份简报"])
        )

    def _build_response(
        self,
        decision: IntentDecision,
        output: dict[str, Any],
        state: SessionState,
    ) -> AssistantResponse:
        if output.get("status") == "pending_confirmation":
            prompt = self._build_confirmation_prompt(decision)
            return AssistantResponse(
                message=prompt,
                pending_confirmation=True,
                confirmation_prompt=prompt,
                raw_outputs=output,
            )

        if decision.tool_name in {"get_trending_events", "get_repo_update_events", "get_report_events"}:
            events = output.get("events") or []
            return self._render_events_response(decision.intent, events)
        if decision.tool_name == "get_event_detail":
            event = output.get("event")
            if not event:
                return AssistantResponse(message="没有找到对应事件，可能还没持久化或引用已经失效。")
            return AssistantResponse(
                message=self._render_event_detail(event),
                referenced_event_ids=[event["event_id"]],
                raw_outputs=output,
            )
        if decision.tool_name == "render_briefing_preview":
            markdown = output.get("markdown", "")
            return AssistantResponse(message=markdown, raw_outputs=output)
        if decision.tool_name == "get_delivery_tasks":
            tasks = output.get("tasks") or []
            return self._render_tasks_response(tasks)

        message = output.get("message")
        if not message and "repository" in output:
            message = f"已新增订阅：{output['repository']}"
        if not message and "task" in output:
            task = output["task"]
            message = f"已创建推送任务：{task['channel']} -> {task['target']}，频率={task.get('schedule') or '未指定'}"
        if not message and "deleted" in output:
            message = "已删除任务。" if output["deleted"] else "未找到要删除的任务。"
        return AssistantResponse(message=message or "操作完成。", raw_outputs=output)

    def _update_session_state(
        self,
        state: SessionState,
        decision: IntentDecision,
        response: AssistantResponse,
        output: dict[str, Any],
    ) -> None:
        state.last_intent = decision.intent
        state.updated_at = RunContext.create(trigger_type="chat").created_at
        if response.pending_confirmation:
            state.pending_action = decision.intent
            state.pending_tool_name = decision.tool_name
            state.pending_tool_input = decision.tool_input
            return
        state.pending_action = None
        state.pending_tool_name = None
        state.pending_tool_input = None
        if decision.tool_name in {"get_trending_events", "get_repo_update_events", "get_report_events"}:
            events = output.get("events") or []
            state.last_event_ids = [event["event_id"] for event in events]
            state.reference_map = {str(index): event["event_id"] for index, event in enumerate(events, start=1)}
            if events:
                state.last_subject = events[0].get("subject")
        elif decision.tool_name == "render_briefing_preview":
            state.last_briefing_id = "preview"
        elif decision.tool_name == "get_delivery_tasks":
            tasks = output.get("tasks") or []
            state.reference_map = {str(index): task["task_id"] for index, task in enumerate(tasks, start=1)}
        elif decision.tool_name == "get_event_detail":
            event = output.get("event")
            if event:
                state.last_event_ids = [event["event_id"]]
                state.reference_map = {"1": event["event_id"]}
                state.last_subject = event.get("subject")

    @staticmethod
    def _render_events_response(intent: str, events: list[dict[str, Any]]) -> AssistantResponse:
        if not events:
            return AssistantResponse(message="当前没有查询到可用结果。")
        lines = []
        if intent == "query_intelligence":
            lines.append("我帮你筛了一轮，先看最值得注意的几项：")
        for index, event in enumerate(events, start=1):
            lines.extend(
                [
                    f"{index}. {event['title']}",
                    f"   这是做什么的：{event['summary']}",
                    f"   为什么值得关注：{event['rationale']}",
                    f"   重要度：{event['importance_score']}",
                ]
            )
        lines.append("你可以直接说“第 2 个详细讲讲”或者“生成简报”。")
        return AssistantResponse(
            message="\n".join(lines),
            referenced_event_ids=[event["event_id"] for event in events],
            suggested_next_actions=["第 1 个详细讲讲", "生成简报", "发到邮箱"],
            raw_outputs={"events": events},
        )

    @staticmethod
    def _render_tasks_response(tasks: list[dict[str, Any]]) -> AssistantResponse:
        if not tasks:
            return AssistantResponse(message="当前还没有推送任务。你可以直接说“每天发一份快讯到邮箱”。")
        lines = ["当前推送任务如下："]
        for index, task in enumerate(tasks, start=1):
            lines.append(
                f"{index}. {task['channel']} -> {task['target']} / scope={task.get('scope', 'daily')} / view={task.get('view', 'flash')} / schedule={task.get('schedule') or 'daily'}"
            )
        lines.append("你可以直接说“删除第 1 个任务”。")
        return AssistantResponse(message="\n".join(lines), raw_outputs={"tasks": tasks})

    @staticmethod
    def _render_event_detail(event: dict[str, Any]) -> str:
        lines = [
            f"# {event['title']}",
            "",
            f"- 事件类型：{event['event_type']}",
            f"- 主题对象：{event['subject']}",
            f"- 核心解读：{event['summary']}",
            f"- 进一步说明：{event['rationale']}",
            f"- 重要度：{event['importance_score']}",
        ]
        source_refs = event.get("source_refs") or []
        if source_refs:
            lines.append("- 来源：")
            for ref in source_refs[:5]:
                url = ref.get("url") or "(无链接)"
                lines.append(f"  - {ref.get('source_kind')} / {ref.get('source_key')} / {url}")
        return "\n".join(lines)

    @staticmethod
    def _build_confirmation_prompt(decision: IntentDecision) -> str:
        if decision.tool_name == "deliver_briefing":
            return "这是一个外发动作。回复“确认”继续发送，回复“取消”放弃。"
        if decision.tool_name == "create_delivery_task":
            return "这是一个定时任务创建动作。回复“确认”创建，回复“取消”放弃。"
        if decision.tool_name == "add_subscription":
            return "这是一个订阅修改动作。回复“确认”继续，回复“取消”放弃。"
        return "这是一个需要确认的动作。回复“确认”继续，回复“取消”放弃。"

    def _build_briefing_input(self, state: SessionState, text: str) -> dict[str, Any]:
        events = []
        persisted_events = {row["event_id"]: row for row in self.storage.load_collection("events")}
        for event_id in state.last_event_ids[:5]:
            if event_id in persisted_events:
                events.append(persisted_events[event_id])
        if not events:
            recent = self.storage.load_collection("events")[-5:]
            events.extend(recent)
        view = "flash"
        if "深读" in text:
            view = "deep"
        elif "对话" in text:
            view = "conversation"
        return {"scope": "daily", "view": view, "events": events}

    def _build_delivery_input(self, text: str, state: SessionState) -> dict[str, Any]:
        channel = "webhook" if "webhook" in text.lower() else "email"
        return {"channel": channel, "scope": "daily"}

    def _build_task_input(self, text: str) -> dict[str, Any]:
        channel = "webhook" if "webhook" in text.lower() else "email"
        schedule = "daily"
        view = "flash"
        if "每周" in text:
            schedule = "weekly"
        elif "每小时" in text:
            schedule = "hourly"
        if "深读" in text:
            view = "deep"
        elif "对话" in text:
            view = "conversation"
        return {"channel": channel, "target": "default", "scope": "daily", "view": view, "schedule": schedule}

    def _resolve_reference(self, text: str, state: SessionState) -> ResolvedReference | None:
        match = re.search(r"第\s*(\d+)\s*个", text)
        if match:
            index = match.group(1)
            event_id = state.reference_map.get(index)
            if event_id:
                return ResolvedReference(kind="event", value=event_id)
        if any(keyword in text for keyword in ["刚才那篇", "刚刚那篇", "那个项目", "那篇报告"]) and state.last_event_ids:
            return ResolvedReference(kind="event", value=state.last_event_ids[0])
        if "那份简报" in text and state.last_briefing_id:
            return ResolvedReference(kind="briefing", value=state.last_briefing_id)
        return None

    def _resolve_task_reference(self, text: str, state: SessionState) -> str:
        match = re.search(r"第\s*(\d+)\s*个?任务", text)
        if match:
            task_id = state.reference_map.get(match.group(1))
            if task_id:
                return task_id
        raise ValueError("没有识别到要删除的任务，请先查看任务列表后再说“删除第 N 个任务”。")

    @staticmethod
    def _extract_window(text: str) -> str:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ["weekly", "7d", "这周", "最近七天"]):
            return "7d"
        if any(keyword in lowered for keyword in ["monthly", "30d", "这个月", "最近三十天"]):
            return "30d"
        return "daily"

    @staticmethod
    def _extract_hours(text: str) -> int | None:
        match = re.search(r"(\d+)\s*小时", text)
        if match:
            return int(match.group(1))
        match = re.search(r"(\d+)\s*天", text)
        if match:
            return int(match.group(1)) * 24
        return None

    @staticmethod
    def _extract_limit(text: str) -> int | None:
        match = re.search(r"(\d+)\s*(个|条|篇)", text)
        if match:
            return int(match.group(1))
        return None

    @staticmethod
    def _extract_repository(text: str, *, required: bool = True) -> str | None:
        match = re.search(r"\b([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b", text)
        if match:
            return match.group(1).lower()
        if required:
            raise ValueError("没有识别到仓库名，请使用 owner/name 格式。")
        return None

    @staticmethod
    def _is_confirmation_message(text: str) -> bool:
        return text.lower() in {"确认", "yes", "y", "ok", "取消", "cancel", "no", "n", "不用", "算了"}
