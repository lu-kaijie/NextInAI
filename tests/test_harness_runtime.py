from nextinai.harness.models import RunContext, SessionState
from nextinai.harness.runtime import ExecutionEngine, FileSessionStateStore, ToolRegistry
from nextinai.storage.files import FileStorage


class EchoTool:
    name = "echo"
    description = "echo"
    input_schema = {}
    output_schema = {}
    requires_confirmation = False

    def execute(self, context, tool_input):
        return {"message": tool_input["message"], "echoed": True}


class DangerousTool:
    name = "dangerous"
    description = "dangerous"
    input_schema = {}
    output_schema = {}
    requires_confirmation = True

    def execute(self, context, tool_input):
        return {"message": "executed"}


def test_file_session_state_store_roundtrip(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    store = FileSessionStateStore(storage)
    state = SessionState(session_id="session-1", last_intent="query_intelligence", last_event_ids=["event-1"])

    store.save(state)
    loaded = store.load("session-1")

    assert loaded.session_id == "session-1"
    assert loaded.last_intent == "query_intelligence"
    assert loaded.last_event_ids == ["event-1"]


def test_execution_engine_records_run(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    registry = ToolRegistry()
    registry.register(EchoTool())
    engine = ExecutionEngine(tool_registry=registry, storage=storage)
    context = RunContext.create(trigger_type="cli", allowed_tools=["echo"])

    result = engine.execute_tool(context, "echo", {"message": "hello"}, user_input="say hello")

    rows = storage.load_collection("job_runs")
    assert result.output["message"] == "hello"
    assert rows[0]["tool_calls"][0]["tool_name"] == "echo"
    assert rows[0]["output_message"] == "hello"


def test_execution_engine_requires_confirmation_for_action_tool(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    registry = ToolRegistry()
    registry.register(DangerousTool())
    engine = ExecutionEngine(tool_registry=registry, storage=storage)
    context = RunContext.create(trigger_type="chat")

    result = engine.execute_tool(context, "dangerous", {"target": "mail"})

    assert result.output["status"] == "pending_confirmation"
    rows = storage.load_collection("job_runs")
    assert rows[0]["tool_calls"][0]["requires_confirmation"] is True
