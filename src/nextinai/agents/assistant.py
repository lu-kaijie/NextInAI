"""Controlled assistant agent for the intelligence harness."""

from __future__ import annotations

import json
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

MAX_AGENT_LOOP_STEPS = 8


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


def _build_service_registry_for_storage(storage: FileStorage) -> ServiceRegistry:
    return build_service_registry(storage)


@dataclass(slots=True)
class IntentDecision:
    intent: str | None
    tool_name: str
    tool_input: dict[str, Any]
    requires_confirmation: bool = False


class OpenAIIntentPlanner:
    """LLM-backed planner that selects harness tools via tool calling."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.system_prompt = (
            "你是 NextInAI 的受控 agent。"
            "你的职责是根据用户目标、会话上下文和工具结果，决定下一步是否调用工具。"
            "不要依赖关键词匹配思维，不要假装已经完成未执行的动作。"
            "你必须显式给出工具参数，不能把时间窗口、数量、导出格式、仓库名、报告来源、scope、view、target 留给程序猜。"
            "如果缺少 event_id、task_id、report_id 或简报 events，请先调用 resolver / prepare 类工具，不要假设程序会自动补齐。"
            "当需要从上一轮结果里选对象时，请传递语义化 selection 对象，由你自己推断 index、direction 等参数，不要依赖程序理解用户原话。"
            "selection 对象必须明确包含 strategy、index、direction 三个字段。"
            "如果需要查看列表、展开细节、生成简报、导出、发送通知或管理任务，就主动选择工具。"
            "涉及外发、订阅修改、任务创建/删除等副作用动作时，也照常选择工具，系统会负责确认门。"
            "如果用户是在追问上一轮结果，请优先调用 reference resolver 工具取得真实目标，再调用业务工具。"
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
                        "required": ["window", "limit"],
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
                        "required": ["limit"],
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
                        "required": ["repository", "hours"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_event_detail",
                    "description": "查看单个事件的详细解读。调用前必须已经拿到真实 event_id。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string", "description": "真实事件 ID。若只有 ordinal 引用，请先调用 resolve_event_reference。"},
                        },
                        "required": ["event_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "resolve_event_reference",
                    "description": "把上一轮结果中的语义选择解析成真实 event_id，可用于详情查看或报告导出。selection 由模型根据用户表达自行推断。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selection": {
                                "type": "object",
                                "description": "语义选择对象。",
                                "properties": {
                                    "strategy": {"type": "string", "description": "固定传 ordinal。"},
                                    "index": {"type": "integer", "description": "第几个，必须是正整数。"},
                                    "direction": {
                                        "type": "string",
                                        "description": "from_start 表示正数第 N 个，from_end 表示倒数第 N 个。",
                                    },
                                },
                                "required": ["strategy", "index", "direction"],
                            },
                        },
                        "required": ["selection"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "resolve_delivery_task_reference",
                    "description": "把上一轮任务列表中的语义选择解析成真实 task_id，用于删除任务。selection 由模型根据用户表达自行推断。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "selection": {
                                "type": "object",
                                "description": "语义选择对象。",
                                "properties": {
                                    "strategy": {"type": "string", "description": "固定传 ordinal。"},
                                    "index": {"type": "integer", "description": "第几个，必须是正整数。"},
                                    "direction": {
                                        "type": "string",
                                        "description": "from_start 表示正数第 N 个，from_end 表示倒数第 N 个。",
                                    },
                                },
                                "required": ["strategy", "index", "direction"],
                            },
                        },
                        "required": ["selection"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "prepare_briefing_context",
                    "description": "为简报生成准备 scope、view 和 events。调用 render_briefing_preview 前优先使用。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "scope": {"type": "string", "description": "简报范围，如 daily、7d、30d。"},
                            "view": {"type": "string", "description": "视图，如 flash、deep、conversation。"},
                        },
                        "required": ["scope", "view"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "prepare_report_export",
                    "description": "把 report_id、event_id 或语义选择解析成真实 report_id，用于 export_report。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "report_id": {"type": "string", "description": "已知 report_id 时直接传。"},
                            "event_id": {"type": "string", "description": "已知 event_id 时可传。"},
                            "selection": {
                                "type": "object",
                                "description": "语义选择对象；当用户引用上一轮列表中的某个对象时使用。",
                                "properties": {
                                    "strategy": {"type": "string", "description": "固定传 ordinal。"},
                                    "index": {"type": "integer", "description": "第几个，必须是正整数。"},
                                    "direction": {
                                        "type": "string",
                                        "description": "from_start 表示正数第 N 个，from_end 表示倒数第 N 个。",
                                    },
                                },
                                "required": ["strategy", "index", "direction"],
                            },
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
                            "events": {
                                "type": "array",
                                "description": "完整事件对象数组。通常先调用 prepare_briefing_context 获得。",
                                "items": {"type": "object"},
                            },
                        },
                        "required": ["scope", "view", "events"],
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
                        "required": ["repository", "hours", "formats"],
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
                        "required": ["window", "limit", "formats"],
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
                            "report_id": {"type": "string", "description": "真实报告 ID。若还没有，请先调用 prepare_report_export。"},
                            "formats": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "导出格式，如 md、pdf。",
                            },
                        },
                        "required": ["report_id", "formats"],
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
                        "required": ["limit", "formats"],
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
                        "required": ["scope", "formats"],
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
                            "lookback_hours": {"type": "integer", "description": "回看窗口小时数。"},
                            "refresh_minutes": {"type": "integer", "description": "刷新频率分钟数。"},
                        },
                        "required": ["repository", "lookback_hours", "refresh_minutes"],
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
                            "target": {"type": "string", "description": "投递目标。若用默认配置，请显式传 default。"},
                            "scope": {"type": "string", "description": "范围，如 daily、7d、30d。"},
                            "view": {"type": "string", "description": "视图，如 flash、deep、conversation。"},
                            "schedule": {"type": "string", "description": "调度频率，如 hourly、daily、weekly。"},
                        },
                        "required": ["channel", "target", "scope", "view", "schedule"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_delivery_task",
                    "description": "删除某个推送任务。调用前必须已经拿到真实 task_id。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string", "description": "真实任务 ID。若只有 ordinal 引用，请先调用 resolve_delivery_task_reference。"},
                        },
                        "required": ["task_id"],
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
                            "scope": {"type": "string", "description": "范围，如 daily、7d、30d。"},
                            "target": {"type": "string", "description": "投递目标。若用默认配置，请显式传 default。"},
                        },
                        "required": ["channel", "scope", "target"],
                    },
                },
            },
        ]

    def build_messages(self, *, message: str, state: SessionState) -> list[dict[str, Any]]:
        state_summary = (
            f"last_intent={state.last_intent}, "
            f"last_query={state.last_query}, "
            f"last_event_ids={state.last_event_ids[:5]}, "
            f"current_event_id={state.current_event_id}, "
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


class AssistantAgent:
    """A controlled agent that routes natural language to harness tools."""

    def __init__(
        self,
        *,
        storage: FileStorage | None = None,
        service_registry: ServiceRegistry | None = None,
        execution_engine: ExecutionEngine | None = None,
        session_store: FileSessionStateStore | None = None,
        intent_planner: Any | None = None,
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

        return self._respond_with_planner_loop(text, state, actor_id=actor_id)

    def _respond_with_planner_loop(
        self,
        text: str,
        state: SessionState,
        *,
        actor_id: str | None,
    ) -> AssistantResponse:
        planner = self.intent_planner
        assert planner is not None
        messages = planner.build_messages(message=text, state=state)
        final_response: AssistantResponse | None = None
        last_signature: str | None = None
        hit_step_limit = True
        for step in range(MAX_AGENT_LOOP_STEPS):
            try:
                completion = planner.create_completion(messages)
            except Exception as exc:
                log_error(self.logger, "planner 调度失败", session_id=state.session_id, error=exc)
                return AssistantResponse(message=f"planner 调度失败：{exc}")
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
                hit_step_limit = False
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
                decision = self._build_planned_decision(tool_call.function.name, tool_call.function.arguments or "{}")
                signature = self._build_tool_signature(decision)
                if signature == last_signature:
                    self.session_store.save(state)
                    log_event(
                        self.logger,
                        "agent loop 检测到重复调用并终止",
                        session_id=state.session_id,
                        tool=decision.tool_name,
                        step=step + 1,
                    )
                    if final_response is not None and final_response.error:
                        return final_response
                    return AssistantResponse(
                        message="agent loop 检测到重复工具调用且没有新进展，已主动停止。请换个问法或补充更明确的目标。"
                    )

                response = self._execute_decision(text, state, decision, actor_id=actor_id, save_state=False)
                final_response = response
                last_signature = signature
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
        if hit_step_limit:
            return AssistantResponse(
                message="agent loop 达到最大步数限制，已停止继续调用工具。你可以补充更明确的目标后再试一次。",
                raw_outputs=final_response.raw_outputs if final_response else {},
            )
        if final_response is not None:
            return final_response
        return AssistantResponse(message="agent loop 达到上限或没有继续信号，本轮没有产出最终可用结果。")

    def _build_planned_decision(self, tool_name: str, raw_arguments: str) -> IntentDecision:
        tool = self.tool_registry.get(tool_name)
        tool_input = json.loads(raw_arguments or "{}")
        intent = tool.intent
        if isinstance(tool_input.get("__test_intent"), str):
            intent = str(tool_input.pop("__test_intent"))
        normalized_input = {
            key: value
            for key, value in dict(tool_input).items()
            if value is not None and value != ""
        }
        return IntentDecision(
            intent=intent,
            tool_name=tool_name,
            tool_input=normalized_input,
            requires_confirmation=tool.requires_confirmation,
        )

    @staticmethod
    def _build_tool_signature(decision: IntentDecision) -> str:
        return f"{decision.tool_name}:{json.dumps(decision.tool_input, sort_keys=True, ensure_ascii=False)}"

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
            "准备执行 planner 决策",
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
            metadata={"user_message": text, "tool_name": decision.tool_name},
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
            metadata={"confirmation": True, "tool_name": state.pending_tool_name},
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
            "resolve_event_reference",
            "resolve_delivery_task_reference",
            "prepare_briefing_context",
            "prepare_report_export",
        }:
            return AssistantResponse(message=str(output.get("message") or "解析完成。"), raw_outputs=output)
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
            displayed_event_ids = list(response.referenced_event_ids)
            all_events = output.get("events") or []
            event_index = {
                event["event_id"]: event
                for event in all_events
                if isinstance(event, dict) and event.get("event_id")
            }
            displayed_events = [event_index[event_id] for event_id in displayed_event_ids if event_id in event_index]
            state.last_event_ids = displayed_event_ids
            state.reference_map = {
                str(index): event_id
                for index, event_id in enumerate(displayed_event_ids, start=1)
            }
            if displayed_events:
                state.last_subject = displayed_events[0].get("subject")
            state.current_event_id = displayed_event_ids[0] if displayed_event_ids else None
            state.last_query = dict(decision.tool_input)
            state.last_query["tool_name"] = decision.tool_name
        elif decision.tool_name == "render_briefing_preview":
            state.last_briefing_id = "preview"
            state.last_query = dict(decision.tool_input)
            state.last_query["tool_name"] = decision.tool_name
        elif decision.tool_name == "get_delivery_tasks":
            tasks = output.get("tasks") or []
            state.reference_map = {str(index): task["task_id"] for index, task in enumerate(tasks, start=1)}
            state.current_event_id = None
            state.last_query = {"tool_name": decision.tool_name}
        elif decision.tool_name == "get_event_detail":
            event = output.get("event")
            if event:
                state.current_event_id = event["event_id"]
                state.last_subject = event.get("subject")
                state.last_query = {
                    "tool_name": decision.tool_name,
                    "event_id": event["event_id"],
                    "report_id": self._extract_report_id_from_event(event),
                    "subject": event.get("subject"),
                }
        elif decision.tool_name == "prepare_briefing_context":
            events = output.get("events") or []
            state.last_event_ids = [event["event_id"] for event in events if event.get("event_id")]
            if events:
                state.reference_map = {str(index): event["event_id"] for index, event in enumerate(events, start=1)}
                state.last_subject = events[0].get("subject")
                state.current_event_id = events[0]["event_id"]
            state.last_query = {
                "tool_name": decision.tool_name,
                "scope": output.get("scope"),
                "view": output.get("view"),
            }

    @staticmethod
    def _render_events_response(intent: str | None, events: list[dict[str, Any]]) -> AssistantResponse:
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
    def _is_confirmation_message(text: str) -> bool:
        return text.lower() in {"确认", "yes", "y", "ok", "取消", "cancel", "no", "n", "不用", "算了"}
