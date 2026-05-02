"""Core runtime and domain models for the intelligence harness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO format."""

    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class SourceReference:
    source_kind: str
    source_key: str
    content_ref: str | None = None
    analysis_ref: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SourceItem:
    item_id: str
    source_kind: str
    source_key: str
    signal_type: str
    title: str
    url: str
    published_at: str | None
    summary_text: str | None
    body_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    dedupe_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IntelligenceEvent:
    event_id: str
    event_type: str
    subject: str
    title: str
    summary: str
    rationale: str
    source_refs: list[SourceReference] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    novelty_score: float = 0.0
    relevance_score: float = 0.0
    impact_score: float = 0.0
    heat_score: float = 0.0
    confidence_score: float = 0.0
    importance_score: float = 0.0
    happened_at: str | None = None
    related_event_ids: list[str] = field(default_factory=list)
    briefing_ids: list[str] = field(default_factory=list)
    delivery_task_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_refs"] = [ref.to_dict() for ref in self.source_refs]
        return payload


@dataclass(slots=True)
class Briefing:
    briefing_id: str
    scope: str
    view: str
    title: str
    summary: str
    event_ids: list[str]
    content_markdown: str
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DeliveryTask:
    task_id: str
    channel: str
    target: str
    scope: str
    view: str
    schedule: str | None
    enabled: bool = True
    filters: dict[str, Any] = field(default_factory=dict)
    last_run_at: str | None = None
    last_delivery_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolCallRecord:
    tool_name: str
    tool_input: dict[str, Any]
    tool_output: dict[str, Any] | None = None
    requires_confirmation: bool = False
    status: str = "success"
    error: str | None = None
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None

    def finalize(self, *, output: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.tool_output = output
        self.error = error
        self.status = "failed" if error else "success"
        self.finished_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgentRun:
    run_id: str
    trigger_type: str
    session_id: str | None
    actor_id: str | None
    intent: str | None
    user_input: str | None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    output_message: str | None = None
    status: str = "success"
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None

    def finalize(self, *, output_message: str | None = None, error: str | None = None) -> None:
        self.output_message = output_message
        self.error = error
        self.status = "failed" if error else "success"
        self.finished_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tool_calls"] = [call.to_dict() for call in self.tool_calls]
        return payload


@dataclass(slots=True)
class RunContext:
    run_id: str
    trigger_type: str
    session_id: str | None
    actor_id: str | None
    intent: str | None
    model_config: dict[str, Any]
    allowed_tools: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        trigger_type: str,
        session_id: str | None = None,
        actor_id: str | None = None,
        intent: str | None = None,
        model_config: dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "RunContext":
        return cls(
            run_id=str(uuid4()),
            trigger_type=trigger_type,
            session_id=session_id,
            actor_id=actor_id,
            intent=intent,
            model_config=model_config or {},
            allowed_tools=allowed_tools or [],
            metadata=metadata or {},
        )


@dataclass(slots=True)
class SessionState:
    session_id: str
    last_intent: str | None = None
    last_query: dict[str, Any] = field(default_factory=dict)
    last_event_ids: list[str] = field(default_factory=list)
    last_briefing_id: str | None = None
    last_subject: str | None = None
    pending_action: str | None = None
    pending_tool_name: str | None = None
    pending_tool_input: dict[str, Any] | None = None
    reference_map: dict[str, str] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionState":
        return cls(
            session_id=payload["session_id"],
            last_intent=payload.get("last_intent"),
            last_query=dict(payload.get("last_query") or {}),
            last_event_ids=list(payload.get("last_event_ids") or []),
            last_briefing_id=payload.get("last_briefing_id"),
            last_subject=payload.get("last_subject"),
            pending_action=payload.get("pending_action"),
            pending_tool_name=payload.get("pending_tool_name"),
            pending_tool_input=payload.get("pending_tool_input"),
            reference_map=dict(payload.get("reference_map") or {}),
            updated_at=payload.get("updated_at") or utc_now_iso(),
        )


@dataclass(slots=True)
class AssistantResponse:
    message: str
    referenced_event_ids: list[str] = field(default_factory=list)
    referenced_briefing_id: str | None = None
    suggested_next_actions: list[str] = field(default_factory=list)
    pending_confirmation: bool = False
    confirmation_prompt: str | None = None
    raw_outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
