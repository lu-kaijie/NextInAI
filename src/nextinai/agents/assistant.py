"""Controlled assistant agent for the intelligence harness."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from openai import OpenAI

from nextinai.core.config import get_settings
from nextinai.core.logging import get_logger, log_error, log_event
from nextinai.harness.models import AssistantResponse, RunContext, SessionState
from nextinai.harness.runtime import ExecutionEngine, FileSessionStateStore
from nextinai.harness.tools import build_harness_tool_registry
from nextinai.services.registry import ServiceRegistry, build_service_registry
from nextinai.storage.files import FileStorage, ensure_workspace


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


def _build_service_registry_for_storage(storage: FileStorage) -> ServiceRegistry:
    return build_service_registry(storage)


@dataclass(slots=True)
class IntentDecision:
    intent: str
    tool_name: str
    tool_input: dict[str, Any]
    requires_confirmation: bool = False


class ReferenceResolutionError(ValueError):
    """Raised when the user is clearly referring to prior context but resolution fails."""


class IntentPlanner:
    """Planner interface for converting chat requests into tool decisions."""

    def decide(self, *, message: str, state: SessionState) -> IntentDecision | None:
        raise NotImplementedError


class OpenAIIntentPlanner(IntentPlanner):
    """LLM-backed planner that selects harness tools via tool calling."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.system_prompt = (
            "你是 NextInAI 的受控 agent。"
            "你的职责是根据用户目标、会话上下文和工具结果，决定下一步是否调用工具。"
            "不要依赖关键词匹配思维，不要假装已经完成未执行的动作。"
            "你必须显式给出工具参数，不能把时间窗口、导出格式、仓库名、报告来源之类参数留给程序猜。"
            "如果需要查看列表、展开细节、生成简报、导出、发送通知或管理任务，就主动选择工具。"
            "涉及外发、订阅修改、任务创建/删除等副作用动作时，也照常选择工具，系统会负责确认门。"
            "如果用户是在追问上一轮结果，可以使用 reference_index。"
        )
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_trending_events",
                    "description": "查询 GitHub 热门项目榜，适合最近最火、热门榜、star 增长之类问题。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "window": {"type": "string", "description": "时间窗口，如 daily、7d、30d、14d。"},
                            "limit": {"type": "integer", "description": "返回条数。"},
                        },
                        "required": ["window"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_report_events",
                    "description": "查看 AI 公司或论坛的报告列表，可按来源筛选。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_name": {"type": "string", "description": "报告来源名称，如 OpenAI News。"},
                            "limit": {"type": "integer", "description": "返回条数。"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_repo_update_events",
                    "description": "查看某个 GitHub 仓库最近的更新事件。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repository": {"type": "string", "description": "GitHub 仓库，格式 owner/name。"},
                            "hours": {"type": "integer", "description": "时间窗口小时数。"},
                        },
                        "required": ["repository"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_event_detail",
                    "description": "查看上一轮结果中的某一项详细解读。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reference_index": {"type": "integer", "description": "上一轮结果中的编号，如第 2 个就是 2。"},
                            "event_id": {"type": "string", "description": "已知事件 ID 时可直接传。"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "render_briefing_preview",
                    "description": "基于最近结果生成简报预览。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scope": {"type": "string", "description": "简报范围，如 daily。"},
                            "view": {"type": "string", "description": "视图，如 flash、deep、conversation。"},
                        },
                        "required": ["view"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "export_repository_summary",
                    "description": "导出某个 GitHub 仓库的更新摘要。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repository": {"type": "string", "description": "GitHub 仓库，格式 owner/name。"},
                            "hours": {"type": "integer", "description": "时间窗口小时数。"},
                            "formats": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "导出格式，如 md、pdf。",
                            },
                        },
                        "required": ["repository", "formats"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "export_trending",
                    "description": "导出热门榜分析结果。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "window": {"type": "string", "description": "时间窗口，如 daily、7d、30d。"},
                            "limit": {"type": "integer", "description": "导出条数。"},
                            "formats": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "导出格式，如 md、pdf。",
                            },
                        },
                        "required": ["window", "formats"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "export_report",
                    "description": "导出单条报告的详细解读。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "report_id": {"type": "string", "description": "报告 ID。"},
                            "reference_index": {"type": "integer", "description": "上一轮结果编号。"},
                            "formats": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "导出格式，如 md、pdf。",
                            },
                        },
                        "required": ["formats"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "export_report_summary",
                    "description": "导出某个来源的最近报告摘要列表。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_name": {"type": "string", "description": "报告来源名称，如 OpenAI News。"},
                            "limit": {"type": "integer", "description": "导出条数。"},
                            "formats": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "导出格式，如 md、pdf。",
                            },
                        },
                        "required": ["formats"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "export_digest",
                    "description": "导出简报 Markdown 或 PDF。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scope": {"type": "string", "description": "简报范围，如 daily。"},
                            "formats": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "导出格式，如 md、pdf。",
                            },
                        },
                        "required": ["formats"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_delivery_tasks",
                    "description": "列出当前推送任务。",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_subscription",
                    "description": "新增 GitHub 仓库订阅。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repository": {"type": "string", "description": "GitHub 仓库，格式 owner/name。"},
                            "lookback_hours": {"type": "integer"},
                            "refresh_minutes": {"type": "integer"},
                        },
                        "required": ["repository"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_delivery_task",
                    "description": "创建定时推送任务。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "email 或 webhook。"},
                            "target": {"type": "string", "description": "投递目标，不填通常表示默认值。"},
                            "scope": {"type": "string"},
                            "view": {"type": "string"},
                            "schedule": {"type": "string"},
                        },
                        "required": ["channel", "view"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_delivery_task",
                    "description": "删除某个推送任务。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reference_index": {"type": "integer", "description": "上一轮任务列表中的编号。"},
                            "task_id": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "deliver_briefing",
                    "description": "立刻把简报发送到邮箱或 webhook。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "email 或 webhook。"},
                            "scope": {"type": "string"},
                            "target": {"type": "string"},
                        },
                        "required": ["channel"],
                    },
                },
            },
        ]

    def build_messages(self, *, message: str, state: SessionState) -> list[dict[str, Any]]:
        state_summary = (
            f"last_intent={state.last_intent}, "
            f"last_query={state.last_query}, "
            f"last_event_ids={state.last_event_ids[:5]}, "
            f"reference_map={state.reference_map}, "
            f"pending_tool={state.pending_tool_name}"
        )
        return [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": f"会话状态: {state_summary}\n用户请求: {message}",
            },
        ]

    def create_completion(self, messages: list[dict[str, Any]]):
        return self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=messages,
            tools=self.tools,
            tool_choice="auto",
        )

    def decide(self, *, message: str, state: SessionState) -> IntentDecision | None:
        completion = self.create_completion(self.build_messages(message=message, state=state))
        tool_calls = completion.choices[0].message.tool_calls or []
        if not tool_calls:
            return None
        tool_call = tool_calls[0]
        if tool_call.function is None:
            return None

        tool_input = json.loads(tool_call.function.arguments or "{}")
        tool_name = tool_call.function.name
        intent = _infer_intent_from_tool(tool_name)
        return IntentDecision(
            intent=intent,
            tool_name=tool_name,
            tool_input=tool_input,
        )


def _infer_intent_from_tool(tool_name: str) -> str:
    if tool_name in {"deliver_briefing", "add_subscription", "create_delivery_task", "delete_delivery_task"}:
        return "execute_action"
    if tool_name in {
        "export_repository_summary",
        "export_trending",
        "export_report",
        "export_report_summary",
        "export_digest",
    }:
        return "export_intelligence"
    if tool_name == "render_briefing_preview":
        return "generate_briefing"
    if tool_name == "get_event_detail":
        return "explore_detail"
    return "query_intelligence"


class AssistantAgent:
    """A controlled agent that routes natural language to harness tools."""

    def __init__(
        self,
        *,
        storage: FileStorage | None = None,
        service_registry: ServiceRegistry | None = None,
        execution_engine: ExecutionEngine | None = None,
        session_store: FileSessionStateStore | None = None,
        intent_planner: IntentPlanner | None = None,
    ) -> None:
        self.logger = get_logger("assistant")
        self.storage = storage or _build_storage()
        self.services = service_registry or _build_service_registry_for_storage(self.storage)
        self.tool_registry = build_harness_tool_registry(
            service_registry=self.services,
            storage=self.storage,
        )
        self.execution_engine = execution_engine or ExecutionEngine(
            tool_registry=self.tool_registry,
            storage=self.storage,
        )
        self.session_store = session_store or FileSessionStateStore(self.storage)
        settings = get_settings()
        self.intent_planner = intent_planner
        if self.intent_planner is None and settings.ai_provider == "openai" and settings.openai_api_key and settings.ai_model:
            self.intent_planner = OpenAIIntentPlanner(
                api_key=settings.openai_api_key,
                model=settings.ai_model,
                base_url=settings.openai_base_url,
            )

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
        log_event(self.logger, "收到用户消息", session_id=session_id, actor_id=actor_id, user_message=text)

        if self._is_confirmation_message(text):
            log_event(self.logger, "进入确认流", session_id=session_id)
            return self._handle_confirmation(text, state, actor_id=actor_id)

        if self.intent_planner is None:
            return AssistantResponse(
                message="当前 chat 未配置 AI planner，不能继续调度工具。请先配置可用的 OpenAI API Key 和模型。"
            )

        if isinstance(self.intent_planner, OpenAIIntentPlanner):
            return self._respond_with_openai_loop(text, state, actor_id=actor_id)

        return self._respond_with_single_planner_decision(text, state, actor_id=actor_id)

    def _respond_with_single_planner_decision(
        self,
        text: str,
        state: SessionState,
        *,
        actor_id: str | None,
    ) -> AssistantResponse:
        try:
            decision = self._decide_intent(text, state)
        except ReferenceResolutionError as exc:
            log_error(self.logger, "引用解析失败", session_id=state.session_id, error=exc)
            return AssistantResponse(message=str(exc))
        except Exception as exc:
            log_error(self.logger, "planner 调度失败", session_id=state.session_id, error=exc)
            return AssistantResponse(message=f"planner 调度失败：{exc}")
        return self._execute_decision(text, state, decision, actor_id=actor_id)

    def _respond_with_openai_loop(
        self,
        text: str,
        state: SessionState,
        *,
        actor_id: str | None,
    ) -> AssistantResponse:
        planner = self.intent_planner
        assert isinstance(planner, OpenAIIntentPlanner)
        messages = planner.build_messages(message=text, state=state)
        final_response: AssistantResponse | None = None
        for step in range(4):
            completion = planner.create_completion(messages)
            assistant_message = completion.choices[0].message
            tool_calls = assistant_message.tool_calls or []
            content = assistant_message.content or ""
            if not tool_calls:
                if content.strip():
                    response = AssistantResponse(
                        message=content.strip(),
                        raw_outputs=final_response.raw_outputs if final_response else {},
                    )
                    self.session_store.save(state)
                    log_event(self.logger, "agent loop 输出最终回答", session_id=state.session_id, step=step + 1)
                    return response
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments or "{}",
                            },
                        }
                        for tool_call in tool_calls
                        if tool_call.function is not None
                    ],
                }
            )

            for tool_call in tool_calls:
                if tool_call.function is None:
                    continue
                decision = IntentDecision(
                    intent=_infer_intent_from_tool(tool_call.function.name),
                    tool_name=tool_call.function.name,
                    tool_input=json.loads(tool_call.function.arguments or "{}"),
                )
                try:
                    normalized = self._normalize_planned_decision(decision, state)
                except ReferenceResolutionError as exc:
                    log_error(self.logger, "引用解析失败", session_id=state.session_id, error=exc)
                    return AssistantResponse(message=str(exc))

                response = self._execute_decision(text, state, normalized, actor_id=actor_id, save_state=False)
                final_response = response
                if response.pending_confirmation:
                    self.session_store.save(state)
                    return response
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(response.raw_outputs, ensure_ascii=False),
                    }
                )

        self.session_store.save(state)
        if final_response is not None:
            return final_response
        return AssistantResponse(message="这次 agent loop 没有产出可用结果。")

    def _execute_decision(
        self,
        text: str,
        state: SessionState,
        decision: IntentDecision,
        *,
        actor_id: str | None,
        save_state: bool = True,
    ) -> AssistantResponse:
        log_event(
            self.logger,
            "完成意图判定",
            session_id=state.session_id,
            intent=decision.intent,
            tool=decision.tool_name,
            requires_confirmation=decision.requires_confirmation,
        )
        context = RunContext.create(
            trigger_type="chat",
            session_id=state.session_id,
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
            confirmed=False,
            user_input=text,
        )
        response = self._build_response(decision, result.output, state)
        self._update_session_state(state, decision, response, result.output)
        if save_state:
            self.session_store.save(state)
        log_event(
            self.logger,
            "完成消息响应",
            session_id=state.session_id,
            tool=decision.tool_name,
            pending_confirmation=response.pending_confirmation,
        )
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
            log_event(self.logger, "用户取消待执行动作", session_id=state.session_id)
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
        executed_tool_name = state.pending_tool_name
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
        log_event(
            self.logger,
            "确认动作已执行",
            session_id=state.session_id,
            tool=executed_tool_name,
        )
        return AssistantResponse(message=message or "动作已执行。", raw_outputs=result.output)

    def _decide_intent(self, text: str, state: SessionState) -> IntentDecision:
        if self.intent_planner is None:
            raise RuntimeError("未配置 planner。")
        decision = self.intent_planner.decide(message=text, state=state)
        if decision is None:
            raise RuntimeError("planner 没有返回任何工具决策。")
        return self._normalize_planned_decision(decision, state)

    def _normalize_planned_decision(self, decision: IntentDecision, state: SessionState) -> IntentDecision:
        tool = self.tool_registry.get(decision.tool_name)
        tool_input = {key: value for key, value in dict(decision.tool_input).items() if value is not None and value != ""}
        if decision.tool_name == "get_event_detail":
            tool_input["event_id"] = self._resolve_event_id(tool_input, state)
        elif decision.tool_name == "delete_delivery_task":
            tool_input["task_id"] = self._resolve_task_id(tool_input, state)
        elif decision.tool_name == "render_briefing_preview":
            tool_input = self._build_briefing_input(state, tool_input)
        elif decision.tool_name == "add_subscription":
            tool_input.setdefault("lookback_hours", 24)
            tool_input.setdefault("refresh_minutes", 60)
        elif decision.tool_name == "create_delivery_task":
            tool_input.setdefault("target", "default")
            tool_input.setdefault("scope", "daily")
            tool_input.setdefault("view", "flash")
            tool_input.setdefault("schedule", "daily")
        elif decision.tool_name == "deliver_briefing":
            tool_input.setdefault("scope", "daily")
        elif decision.tool_name == "get_trending_events":
            tool_input.setdefault("limit", 5)
        elif decision.tool_name == "get_report_events":
            tool_input.setdefault("limit", 5)
        elif decision.tool_name == "get_repo_update_events":
            tool_input.setdefault("hours", 168)
        elif decision.tool_name in {
            "export_repository_summary",
            "export_trending",
            "export_report",
            "export_report_summary",
            "export_digest",
        }:
            tool_input = self._normalize_export_tool_input(decision.tool_name, state, tool_input)

        return IntentDecision(
            intent=decision.intent or _infer_intent_from_tool(decision.tool_name),
            tool_name=decision.tool_name,
            tool_input=tool_input,
            requires_confirmation=tool.requires_confirmation,
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
        if output.get("status") == "validation_error":
            error = output.get("error") or {}
            return AssistantResponse(
                message=str(error.get("message") or "工具参数不合法。"),
                raw_outputs=output,
                error=str(error.get("error_type") or "validation_error"),
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
        if decision.tool_name in {
            "export_repository_summary",
            "export_trending",
            "export_report",
            "export_report_summary",
            "export_digest",
        }:
            return self._render_export_response(decision.tool_name, output)

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
            state.last_query = dict(decision.tool_input)
            state.last_query["tool_name"] = decision.tool_name
        elif decision.tool_name == "render_briefing_preview":
            state.last_briefing_id = "preview"
            state.last_query = dict(decision.tool_input)
            state.last_query["tool_name"] = decision.tool_name
        elif decision.tool_name == "get_delivery_tasks":
            tasks = output.get("tasks") or []
            state.reference_map = {str(index): task["task_id"] for index, task in enumerate(tasks, start=1)}
            state.last_query = {"tool_name": decision.tool_name}
        elif decision.tool_name == "get_event_detail":
            event = output.get("event")
            if event:
                state.last_event_ids = [event["event_id"]]
                state.reference_map = {"1": event["event_id"]}
                state.last_subject = event.get("subject")
                state.last_query = {
                    "tool_name": decision.tool_name,
                    "event_id": event["event_id"],
                    "report_id": self._extract_report_id_from_event(event),
                    "subject": event.get("subject"),
                }

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
    def _render_export_response(tool_name: str, output: dict[str, Any]) -> AssistantResponse:
        exports = output.get("exports") or {}
        if not exports:
            return AssistantResponse(message="导出没有生成文件，请检查输入条件后重试。", raw_outputs=output)
        label_map = {
            "export_repository_summary": "仓库更新摘要",
            "export_trending": "热门榜分析",
            "export_report": "报告详细解读",
            "export_report_summary": "报告摘要",
            "export_digest": "简报",
        }
        lines = [f"{label_map.get(tool_name, '内容')}导出完成："]
        for fmt, path in exports.items():
            lines.append(f"- {fmt}: {path}")
        return AssistantResponse(message="\n".join(lines), raw_outputs=output)

    @staticmethod
    def _render_event_detail(event: dict[str, Any]) -> str:
        if event["event_type"] == "insight_event":
            lines = [
                f"# {event['title']}",
                "",
                f"- 事件类型：{event['event_type']}",
                f"- 来源对象：{event['subject']}",
                f"- 事实摘要：{event['rationale']}",
                f"- 核心解读：{event['summary']}",
                f"- 解读分析：{event['summary']}",
                f"- 重要度：{event['importance_score']}",
            ]
        else:
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

    def _build_briefing_input(self, state: SessionState, tool_input: dict[str, Any]) -> dict[str, Any]:
        events = []
        persisted_events = {row["event_id"]: row for row in self.storage.load_collection("events")}
        for event_id in state.last_event_ids[:5]:
            if event_id in persisted_events:
                events.append(persisted_events[event_id])
        if not events:
            recent = self.storage.load_collection("events")[-5:]
            events.extend(recent)
        normalized = dict(tool_input)
        normalized.setdefault("scope", "daily")
        normalized["events"] = events
        return normalized

    def _resolve_event_id(self, tool_input: dict[str, Any], state: SessionState) -> str:
        if "event_id" in tool_input and isinstance(tool_input["event_id"], str):
            return tool_input["event_id"]
        reference_index = tool_input.pop("reference_index", None)
        if reference_index is not None:
            event_id = state.reference_map.get(str(reference_index))
            if event_id:
                return event_id
        raise ReferenceResolutionError(
            "没有成功定位到具体对象。请让 agent 显式提供 event_id，或使用 reference_index 指向上一轮结果。"
        )

    def _resolve_task_id(self, tool_input: dict[str, Any], state: SessionState) -> str:
        if "task_id" in tool_input and isinstance(tool_input["task_id"], str):
            return tool_input["task_id"]
        reference_index = tool_input.pop("reference_index", None)
        if reference_index is not None:
            task_id = state.reference_map.get(str(reference_index))
            if task_id:
                return task_id
        raise ReferenceResolutionError("没有定位到要删除的任务，请先列出任务后再通过 reference_index 指定。")

    def _normalize_export_tool_input(
        self,
        tool_name: str,
        state: SessionState,
        raw_input: dict[str, Any],
    ) -> dict[str, Any]:
        tool_input = {
            key: value
            for key, value in raw_input.items()
            if value is not None and value != "" and value != []
        }
        if tool_name == "export_repository_summary":
            tool_input.setdefault("hours", 168)
        elif tool_name == "export_trending":
            tool_input.setdefault("limit", 5)
        elif tool_name == "export_report":
            existing_report_id = tool_input.get("report_id")
            if isinstance(existing_report_id, str) and not existing_report_id.startswith("report:"):
                event = self._find_event_by_id(existing_report_id)
                normalized_report_id = self._extract_report_id_from_event(event)
                if normalized_report_id:
                    tool_input["report_id"] = normalized_report_id
                else:
                    tool_input.pop("report_id", None)
            if "report_id" not in tool_input:
                reference_index = tool_input.pop("reference_index", None)
                if reference_index is not None:
                    event_id = state.reference_map.get(str(reference_index))
                    if event_id:
                        event = self._find_event_by_id(event_id)
                        report_id = self._extract_report_id_from_event(event)
                        if report_id:
                            tool_input["report_id"] = report_id
        elif tool_name == "export_report_summary":
            tool_input.setdefault("limit", 10)
        elif tool_name == "export_digest":
            tool_input.setdefault("scope", "daily")
        return tool_input

    def _find_event_by_id(self, event_id: str) -> dict[str, Any] | None:
        return next(
            (row for row in self.storage.load_collection("events") if row.get("event_id") == event_id),
            None,
        )

    @staticmethod
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

    @staticmethod
    def _extract_reference_index(text: str, suffix: str = "个") -> str | None:
        if suffix == "个":
            pattern = r"第\s*(\d+|[一二三四五六七八九十两]+)\s*个"
        else:
            pattern = rf"第\s*(\d+|[一二三四五六七八九十两]+)\s*(个)?\s*{suffix}"
        match = re.search(pattern, text)
        if not match:
            return None
        token = match.group(1)
        if token.isdigit():
            return token
        chinese_map = {
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        if token == "十":
            return "10"
        if token.startswith("十") and len(token) == 2:
            return str(10 + chinese_map.get(token[1], 0))
        if token.endswith("十") and len(token) == 2:
            return str(chinese_map.get(token[0], 0) * 10)
        if "十" in token and len(token) == 3:
            return str(chinese_map.get(token[0], 0) * 10 + chinese_map.get(token[2], 0))
        return str(chinese_map.get(token, 0)) if token in chinese_map else None

    @staticmethod
    def _is_confirmation_message(text: str) -> bool:
        return text.lower() in {"确认", "yes", "y", "ok", "取消", "cancel", "no", "n", "不用", "算了"}
