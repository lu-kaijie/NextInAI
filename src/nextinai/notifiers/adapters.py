"""Notification adapters for email and webhook delivery."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Callable

import httpx

from nextinai.core.config import Settings
from nextinai.domain.enums import DeliveryChannel, DeliveryStatus
from nextinai.notifiers.models import DeliveryAttempt, DeliveryResult, NotificationMessage, NotificationTarget


class NotificationAdapter:
    """Abstract notification adapter."""

    channel: DeliveryChannel

    def deliver(self, message: NotificationMessage, target: NotificationTarget) -> DeliveryResult:
        raise NotImplementedError


class EmailNotificationAdapter(NotificationAdapter):
    """Deliver messages through SMTP email."""

    channel = DeliveryChannel.EMAIL

    def __init__(
        self,
        settings: Settings,
        smtp_factory: Callable[[str, int], smtplib.SMTP] | None = None,
    ) -> None:
        self.settings = settings
        self.smtp_factory = smtp_factory or smtplib.SMTP

    def deliver(self, message: NotificationMessage, target: NotificationTarget) -> DeliveryResult:
        if not self.settings.smtp_host:
            raise ValueError("未配置 SMTP_HOST，无法发送邮件通知。")

        email = EmailMessage()
        email["Subject"] = message.title
        email["From"] = self.settings.smtp_username or "nextinai@localhost"
        email["To"] = target.destination
        email.set_content(f"{message.summary}\n\n{message.body}")

        attempts: list[DeliveryAttempt] = []
        try:
            with self.smtp_factory(self.settings.smtp_host, self.settings.smtp_port) as client:
                if self.settings.smtp_username and self.settings.smtp_password:
                    client.starttls()
                    client.login(self.settings.smtp_username, self.settings.smtp_password)
                client.send_message(email)
            attempts.append(
                DeliveryAttempt(
                    attempt_number=1,
                    status=DeliveryStatus.SUCCESS,
                    detail=f"邮件已发送至 {target.destination}",
                )
            )
            return DeliveryResult(
                channel=self.channel,
                target=target.destination,
                status=DeliveryStatus.SUCCESS,
                detail=f"邮件已发送至 {target.destination}",
                attempts=attempts,
            )
        except Exception as exc:
            attempts.append(
                DeliveryAttempt(
                    attempt_number=1,
                    status=DeliveryStatus.FAILED,
                    detail=str(exc),
                )
            )
            return DeliveryResult(
                channel=self.channel,
                target=target.destination,
                status=DeliveryStatus.FAILED,
                detail=f"邮件发送失败：{exc}",
                attempts=attempts,
            )


class WebhookNotificationAdapter(NotificationAdapter):
    """Deliver messages to a webhook endpoint with retries."""

    channel = DeliveryChannel.WEBHOOK

    def __init__(
        self,
        settings: Settings,
        post_callable: Callable[..., httpx.Response] | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.settings = settings
        self.post_callable = post_callable
        self.max_attempts = max_attempts

    def deliver(self, message: NotificationMessage, target: NotificationTarget) -> DeliveryResult:
        attempts: list[DeliveryAttempt] = []
        payload = {
            "title": message.title,
            "summary": message.summary,
            "body": message.body,
            "content_kind": message.content_kind,
            "content_ref": message.content_ref,
            "metadata": message.metadata,
        }
        for attempt_number in range(1, self.max_attempts + 1):
            try:
                response = self._post(target.destination, payload)
                response.raise_for_status()
                attempts.append(
                    DeliveryAttempt(
                        attempt_number=attempt_number,
                        status=DeliveryStatus.SUCCESS,
                        detail=f"HTTP {response.status_code}",
                    )
                )
                return DeliveryResult(
                    channel=self.channel,
                    target=target.destination,
                    status=DeliveryStatus.SUCCESS,
                    detail=f"Webhook 投递成功，HTTP {response.status_code}",
                    attempts=attempts,
                )
            except Exception as exc:
                attempts.append(
                    DeliveryAttempt(
                        attempt_number=attempt_number,
                        status=DeliveryStatus.FAILED,
                        detail=str(exc),
                    )
                )
        return DeliveryResult(
            channel=self.channel,
            target=target.destination,
            status=DeliveryStatus.FAILED,
            detail=f"Webhook 投递失败，已重试 {self.max_attempts} 次。",
            attempts=attempts,
        )

    def _post(self, url: str, payload: dict[str, object]) -> httpx.Response:
        if self.post_callable is not None:
            return self.post_callable(url, json=payload, timeout=10.0)
        with httpx.Client() as client:
            return client.post(url, json=payload, timeout=10.0)
