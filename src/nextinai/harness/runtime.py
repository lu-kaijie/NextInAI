"""Minimal runtime contracts and implementations for the harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from nextinai.harness.models import AgentRun, RunContext, SessionState, ToolCallRecord
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


class ExecutionEngine:
    """Execute tools under a shared run context and record an AgentRun."""

    def __init__(self, *, tool_registry: ToolRegistry, storage: FileStorage) -> None:
        self.tool_registry = tool_registry
        self.storage = storage

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
        if context.allowed_tools and tool_name not in context.allowed_tools:
            raise PermissionError(f"当前上下文不允许执行工具：{tool_name}")

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
            return ExecutionResult(output=output, tool_call=tool_call, agent_run=agent_run)

        try:
            output = tool.execute(context, tool_input)
        except Exception as exc:
            tool_call.finalize(error=str(exc))
            agent_run.finalize(error=str(exc))
            self.record_run(agent_run)
            raise

        tool_call.finalize(output=output)
        agent_run.finalize(output_message=output.get("message"))
        self.record_run(agent_run)
        return ExecutionResult(output=output, tool_call=tool_call, agent_run=agent_run)

    def record_run(self, agent_run: AgentRun) -> None:
        rows = self.storage.load_collection("job_runs")
        rows.append(agent_run.to_dict())
        self.storage.save_collection("job_runs", rows)
