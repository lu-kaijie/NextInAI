from nextinai.services.github_subscriptions import GitHubSubscriptionService


def test_add_subscription_requires_owner_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NEXTINAI_DATA_DIR", str(tmp_path / "data"))

    service = GitHubSubscriptionService()

    try:
        service.add_subscription("invalid-repo", 24, 60)
    except ValueError as exc:
        assert "owner/name" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid repository")


def test_add_subscription_persists_and_normalizes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NEXTINAI_DATA_DIR", str(tmp_path / "data"))

    service = GitHubSubscriptionService()
    saved = service.add_subscription("OpenAI/GPT-OSS", 24, 60)

    rows = service.list_subscriptions()

    assert saved == "openai/gpt-oss"
    assert rows == [
        {
            "repository": "openai/gpt-oss",
            "lookback_hours": 24,
            "refresh_minutes": 60,
        }
    ]
