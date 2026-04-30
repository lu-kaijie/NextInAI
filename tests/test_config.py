from nextinai.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.data_dir.name == "data"
    assert settings.smtp_port == 587
    assert settings.ai_provider == "openai"
    assert settings.ai_model is None


def test_settings_support_standard_openai_env_names(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key == "test-key"
    assert settings.openai_base_url == "https://example.com/v1"
