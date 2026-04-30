"""Stub implementations for non-GitHub services."""

from nextinai.services.contracts import (
    NotificationService,
)


class StubNotificationService(NotificationService):
    def send(
        self,
        channel: str,
        content_kind: str = "digest",
        scope: str = "daily",
        report_title: str | None = None,
        target: str | None = None,
    ) -> str:
        return (
            f"通知发送命令骨架已就绪，后续将实现 {channel} 渠道的真实投递。"
            f" content_kind={content_kind}, scope={scope}, report_title={report_title}, target={target}"
        )
