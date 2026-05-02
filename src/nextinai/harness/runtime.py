"""Minimal runtime contracts and implementations for the harness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from nextinai.harness.models import AgentRun, RunContext, SessionState, ToolCallRecord
from nextinai.core.logging import get_logger, log_error, log_event
from nextinai.storage.files import FileStorage


class Tool(Protocol):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    requires_confirmation: bool

    def execute(self, context: RunContext, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute the tool against the provided context."""


class ToolRegistry:
    """Registry for controlled harness tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"未注册工具：{name}")
        return self._tools[name]

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def list_allowed(self, context: RunContext) -> list[Tool]:
        if not context.allowed_tools:
            return self.list_all()
        return [tool for tool in self._tools.values() if tool.name in context.allowed_tools]


class SessionStateStore(Protocol):
    def load(self, session_id: str) -> SessionState:
        """Load or initialize a session state."""

    def save(self, state: SessionState) -> None:
        """Persist a session state."""

    def clear(self, session_id: str) -> None:
        """Delete a session state."""


class FileSessionStateStore:
    """Session state store backed by local JSON files."""

    def __init__(self, storage: FileStorage) -> None:
        self.storage = storage

    def load(self, session_id: str) -> SessionState:
        rows = self.storage.load_collection("session_states")
        for row in rows:
            if row.get("session_id") == session_id:
                return SessionState.from_dict(row)
        return SessionState(session_id=session_id)

    def save(self, state: SessionState) -> None:
        rows = self.storage.load_collection("session_states")
        updated = False
        for index, row in enumerate(rows):
            if row.get("session_id") == state.session_id:
                rows[index] = state.to_dict()
                updated = True
                break
        if not updated:
            rows.append(state.to_dict())
        self.storage.save_collection("session_states", rows)

    def clear(self, session_id: str) -> None:
        rows = self.storage.load_collection("session_states")
        rows = [row for row in rows if row.get("session_id") != session_id]
        self.storage.save_collection("session_states", rows)


@dataclass(slots=True)
class ExecutionResult:
    output: dict[str, Any]
    tool_call: ToolCallRecord
    agent_run: AgentRun


@dataclass(slots=True)
class ToolValidationError(ValueError):
    error_type: str
    message: str
    field: str | None = None
    provided_value: Any = None
    allowed_values: list[Any] | None = None
    retryable: bool = True

    def to_output(self) -> dict[str, Any]:
        return {
            "status": "validation_error",
            "error": {
                "error_type": self.error_type,
                "message": self.message,
                "field": self.field,
                "provided_value": self.provided_value,
                "allowed_values": self.allowed_values or [],
                "retryable": self.retryable,
            },
        }


class ExecutionEngine:
    """Execute tools under a shared run context and record an AgentRun."""

    def __init__(self, *, tool_registry: ToolRegistry, storage: FileStorage) -> None:
        self.tool_registry = tool_registry
        self.storage = storage
        self.logger = get_logger("execution")

    def execute_tool(
        self,
        context: RunContext,
        tool_name: str,
        tool_input: dict[str, Any],
        *,
        confirmed: bool = False,
        user_input: str | None = None,
    ) -> ExecutionResult:
        tool = self.tool_registry.get(tool_name)
        log_event(
            self.logger,
            "准备执行工具",
            run_id=context.run_id,
            session_id=context.session_id,
            tool=tool_name,
            confirmed=confirmed,
        )
        if context.allowed_tools and tool_name not in context.allowed_tools:
            raise PermissionError(f"当前上下文不允许执行工具：{tool_name}")

        try:
            self._validate_tool_input(tool, tool_input)
        except ToolValidationError as exc:
            output = exc.to_output()
            tool_call = ToolCallRecord(
                tool_name=tool_name,
                tool_input=tool_input,
                requires_confirmation=tool.requires_confirmation,
            )
            tool_call.finalize(output=output, error=exc.message)
            agent_run = AgentRun(
                run_id=context.run_id,
                trigger_type=context.trigger_type,
                session_id=context.session_id,
                actor_id=context.actor_id,
                intent=context.intent,
                user_input=user_input,
                tool_calls=[tool_call],
                metadata={"allowed_tools": context.allowed_tools, **context.metadata},
            )
            agent_run.finalize(output_message=exc.message, error=exc.message)
            self.record_run(agent_run)
            log_error(self.logger, "工具参数校验失败", run_id=context.run_id, tool=tool_name, error=exc.message)
            return ExecutionResult(output=output, tool_call=tool_call, agent_run=agent_run)

        tool_call = ToolCallRecord(
            tool_name=tool_name,
            tool_input=tool_input,
            requires_confirmation=tool.requires_confirmation,
        )
        agent_run = AgentRun(
            run_id=context.run_id,
            trigger_type=context.trigger_type,
            session_id=context.session_id,
            actor_id=context.actor_id,
            intent=context.intent,
            user_input=user_input,
            tool_calls=[tool_call],
            metadata={"allowed_tools": context.allowed_tools, **context.metadata},
        )

        if tool.requires_confirmation and not confirmed:
            output = {
                "status": "pending_confirmation",
                "tool_name": tool_name,
                "tool_input": tool_input,
            }
            tool_call.finalize(output=output)
            agent_run.finalize(output_message="等待用户确认动作执行。")
            self.record_run(agent_run)
            log_event(self.logger, "工具进入待确认状态", run_id=context.run_id, tool=tool_name)
            return ExecutionResult(output=output, tool_call=tool_call, agent_run=agent_run)

        try:
            output = tool.execute(context, tool_input)
        except Exception as exc:
            tool_call.finalize(error=str(exc))
            agent_run.finalize(error=str(exc))
            self.record_run(agent_run)
            log_error(self.logger, "工具执行失败", run_id=context.run_id, tool=tool_name, error=exc)
            raise

        tool_call.finalize(output=output)
        agent_run.finalize(output_message=output.get("message"))
        self.record_run(agent_run)
        log_event(self.logger, "工具执行完成", run_id=context.run_id, tool=tool_name)
        return ExecutionResult(output=output, tool_call=tool_call, agent_run=agent_run)

    def _validate_tool_input(self, tool: Tool, tool_input: dict[str, Any]) -> None:
        if not isinstance(tool_input, dict):
            raise ToolValidationError(
                error_type="invalid_type",
                message="工具输入必须是对象。",
                provided_value=tool_input,
                retryable=False,
            )
        for field_name, raw_schema in tool.input_schema.items():
            optional, schema = self._parse_schema(raw_schema)
            if field_name not in tool_input or tool_input[field_name] is None:
                if optional:
                    continue
                raise ToolValidationError(
                    error_type="missing_required_field",
                    message=f"缺少必填参数：{field_name}",
                    field=field_name,
                )
            self._validate_field(field_name, tool_input[field_name], schema)

    @staticmethod
    def _parse_schema(raw_schema: Any) -> tuple[bool, str]:
        schema = str(raw_schema).strip()
        optional = False
        if schema.startswith("optional "):
            optional = True
            schema = schema[len("optional ") :].strip()
        return optional, schema

    def _validate_field(self, field_name: str, value: Any, schema: str) -> None:
        if schema == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ToolValidationError(
                    error_type="invalid_type",
                    message=f"参数 {field_name} 必须是整数。",
                    field=field_name,
                    provided_value=value,
                )
            return
        if schema == "str":
            if not isinstance(value, str) or not value.strip():
                raise ToolValidationError(
                    error_type="invalid_type",
                    message=f"参数 {field_name} 必须是非空字符串。",
                    field=field_name,
                    provided_value=value,
                )
            return
        if schema == "dict":
            if not isinstance(value, dict):
                raise ToolValidationError(
                    error_type="invalid_type",
                    message=f"参数 {field_name} 必须是对象。",
                    field=field_name,
                    provided_value=value,
                )
            return
        if schema == "list":
            if not isinstance(value, list):
                raise ToolValidationError(
                    error_type="invalid_type",
                    message=f"参数 {field_name} 必须是列表。",
                    field=field_name,
                    provided_value=value,
                )
            return
        if schema == "list[str]":
            if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ToolValidationError(
                    error_type="invalid_type",
                    message=f"参数 {field_name} 必须是非空字符串列表。",
                    field=field_name,
                    provided_value=value,
                )
            return
        if schema.startswith("list[") and schema.endswith("]"):
            if not isinstance(value, list) or not value:
                raise ToolValidationError(
                    error_type="invalid_type",
                    message=f"参数 {field_name} 必须是非空列表。",
                    field=field_name,
                    provided_value=value,
                )
            allowed_values = [item.strip() for item in schema[5:-1].split("|") if item.strip()]
            for item in value:
                if item not in allowed_values:
                    raise ToolValidationError(
                        error_type="unsupported_parameter",
                        message=f"参数 {field_name} 包含不支持的值：{item}",
                        field=field_name,
                        provided_value=item,
                        allowed_values=allowed_values,
                    )
            return
        if schema == "owner/name":
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value.strip()):
                raise ToolValidationError(
                    error_type="invalid_format",
                    message=f"参数 {field_name} 必须是 owner/name 格式。",
                    field=field_name,
                    provided_value=value,
                )
            return
        if "|" in schema:
            allowed_values = [item.strip() for item in schema.split("|") if item.strip()]
            if value not in allowed_values:
                raise ToolValidationError(
                    error_type="unsupported_parameter",
                    message=f"参数 {field_name} 不支持值 {value!r}。",
                    field=field_name,
                    provided_value=value,
                    allowed_values=allowed_values,
                )
            return

    def record_run(self, agent_run: AgentRun) -> None:
        rows = self.storage.load_collection("job_runs")
        rows.append(agent_run.to_dict())
        self.storage.save_collection("job_runs", rows)
