import json
from pathlib import Path

from nextinai.core.config import Settings
from nextinai.storage.files import FileStorage, ensure_workspace


def test_workspace_initialization_creates_default_json_files(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        report_output_dir=tmp_path / "artifacts" / "reports",
    )

    ensure_workspace(settings)

    subscriptions_file = settings.data_dir / "subscriptions.json"
    events_file = settings.data_dir / "events.json"
    assert subscriptions_file.exists()
    assert events_file.exists()
    assert json.loads(subscriptions_file.read_text(encoding="utf-8")) == []


def test_file_storage_roundtrip(tmp_path: Path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection("subscriptions", [{"repository": "openai/gpt-oss", "lookback_hours": 24}])

    loaded = storage.load_collection("subscriptions")

    assert loaded == [{"repository": "openai/gpt-oss", "lookback_hours": 24}]
