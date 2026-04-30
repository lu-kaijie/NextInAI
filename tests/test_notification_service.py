from __future__ import annotations

import hashlib

import httpx

from nextinai.core.config import Settings
from nextinai.domain.enums import DeliveryChannel
from nextinai.notifiers.adapters import EmailNotificationAdapter, WebhookNotificationAdapter
from nextinai.services.notification_service import AgenticNotificationService
from nextinai.storage.files import FileStorage


class FakeSMTPClient:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.messages = []

    def __enter__(self) -> FakeSMTPClient:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def send_message(self, message) -> None:
        self.messages.append(message)


class FakeDigestService:
    def __init__(self, storage: FileStorage) -> None:
        self.storage = storage

    def generate(self, scope: str) -> str:
        markdown = "# NextInAI 情报简报\n\n这是摘要。\n\n## 重点\n- item"
        self.storage.save_collection(
            "digests",
            [
                {
                    "digest_key": "digest-1",
                    "title": "NextInAI 情报简报",
                    "scope": scope,
                    "markdown_body": markdown,
                    "pdf_path": None,
                    "metadata_json": {},
                    "content_hash": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                    "created_at": "2026-04-30T00:00:00+00:00",
                }
            ],
        )
        return markdown


def test_notification_service_sends_digest_via_email_and_records_delivery(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    smtp_client = FakeSMTPClient("smtp.example.com", 2525)
    settings = Settings(
        _env_file=None,
        smtp_host="smtp.example.com",
        smtp_port=2525,
        smtp_username="bot@example.com",
        smtp_password="secret",
    )
    adapter = EmailNotificationAdapter(settings, smtp_factory=lambda host, port: smtp_client)
    service = AgenticNotificationService(
        storage=storage,
        digest_service=FakeDigestService(storage),
        adapters={DeliveryChannel.EMAIL: adapter},
    )

    message = service.send(
        channel="email",
        content_kind="digest",
        scope="daily",
        briefing_view="flash",
        target="user@example.com",
    )

    deliveries = storage.load_collection("deliveries")
    assert "状态=success" in message
    assert len(deliveries) == 1
    assert deliveries[0]["channel"] == "email"
    assert deliveries[0]["status"] == "success"
    assert deliveries[0]["attempt_count"] == 1
    assert smtp_client.started_tls is True
    assert smtp_client.logged_in == ("bot@example.com", "secret")
    assert smtp_client.messages[0]["To"] == "user@example.com"
    assert smtp_client.messages[0]["Subject"] == "NextInAI 情报简报"


def test_notification_service_sends_report_via_email(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    storage.save_collection(
        "analysis_results",
        [
            {
                "analysis_kind": "report_interpretation",
                "source_ref": "report:openai-agents",
                "title": "OpenAI Agents Update",
                "factual_summary": "发布了新的 agent 更新。",
                "interpreted_summary": "对工具调用工作流有直接帮助。",
                "is_partial": False,
            }
        ],
    )
    smtp_client = FakeSMTPClient("smtp.example.com", 2525)
    settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_port=2525)
    adapter = EmailNotificationAdapter(settings, smtp_factory=lambda host, port: smtp_client)
    service = AgenticNotificationService(
        storage=storage,
        digest_service=FakeDigestService(storage),
        adapters={DeliveryChannel.EMAIL: adapter},
    )

    message = service.send(
        channel="email",
        content_kind="report",
        report_title="OpenAI Agents Update",
        target="reader@example.com",
    )

    deliveries = storage.load_collection("deliveries")
    assert "OpenAI Agents Update" in message
    assert deliveries[0]["content_kind"] == "report"
    body = smtp_client.messages[0].get_content()
    assert "事实摘要" in body
    assert "解读分析" in body


def test_notification_service_retries_webhook_and_records_attempts(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    digest_service = FakeDigestService(storage)
    calls = {"count": 0}

    def flaky_post(url: str, json: dict, timeout: float) -> httpx.Response:
        calls["count"] += 1
        request = httpx.Request("POST", url, json=json)
        if calls["count"] < 3:
            return httpx.Response(500, request=request)
        return httpx.Response(200, request=request)

    adapter = WebhookNotificationAdapter(
        Settings(_env_file=None, webhook_base_url="https://example.com/webhook"),
        post_callable=flaky_post,
        max_attempts=3,
    )
    service = AgenticNotificationService(
        storage=storage,
        digest_service=digest_service,
        adapters={DeliveryChannel.WEBHOOK: adapter},
    )

    message = service.send(
        channel="webhook",
        content_kind="digest",
        scope="daily",
        target="https://example.com/webhook",
    )

    deliveries = storage.load_collection("deliveries")
    assert calls["count"] == 3
    assert "状态=success" in message
    assert deliveries[0]["attempt_count"] == 3
    assert deliveries[0]["attempts_json"][0]["status"] == "failed"
    assert deliveries[0]["attempts_json"][2]["status"] == "success"


def test_notification_service_supports_non_flash_digest_view(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    digest_service = FakeDigestService(storage)

    class FakeBriefing:
        title = "NextInAI 深读简报"
        content_markdown = "# NextInAI 深读简报\n\n深读内容"
        briefing_id = "briefing-1"
        view = "deep"
        created_at = "2026-04-30T00:00:00+00:00"

    digest_service.generate_briefing = lambda scope, view: FakeBriefing()
    smtp_client = FakeSMTPClient("smtp.example.com", 2525)
    settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_port=2525)
    adapter = EmailNotificationAdapter(settings, smtp_factory=lambda host, port: smtp_client)
    service = AgenticNotificationService(
        storage=storage,
        digest_service=digest_service,
        adapters={DeliveryChannel.EMAIL: adapter},
    )

    message = service.send(
        channel="email",
        content_kind="digest",
        scope="daily",
        briefing_view="deep",
        target="reader@example.com",
    )

    assert "NextInAI 深读简报" in message
    assert smtp_client.messages[0]["Subject"] == "NextInAI 深读简报"


def test_notification_service_suppresses_duplicate_delivery(tmp_path) -> None:
    storage = FileStorage(tmp_path)
    smtp_client = FakeSMTPClient("smtp.example.com", 2525)
    settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_port=2525)
    adapter = EmailNotificationAdapter(settings, smtp_factory=lambda host, port: smtp_client)
    service = AgenticNotificationService(
        storage=storage,
        digest_service=FakeDigestService(storage),
        adapters={DeliveryChannel.EMAIL: adapter},
    )

    first = service.send(
        channel="email",
        content_kind="digest",
        scope="daily",
        target="reader@example.com",
        suppress_duplicates=True,
    )
    second = service.send(
        channel="email",
        content_kind="digest",
        scope="daily",
        target="reader@example.com",
        suppress_duplicates=True,
    )

    deliveries = storage.load_collection("deliveries")
    assert "状态=success" in first
    assert "通知已抑制" in second
    assert len(smtp_client.messages) == 1
    assert deliveries[-1]["status"] == "suppressed"
