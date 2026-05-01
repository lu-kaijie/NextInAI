"""Notification service for digest and report delivery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from nextinai.core.config import get_settings
from nextinai.core.datetime_utils import parse_datetime
from nextinai.core.logging import get_logger, log_event
from nextinai.domain.enums import DeliveryChannel, DeliveryStatus
from nextinai.notifiers.adapters import EmailNotificationAdapter, NotificationAdapter, WebhookNotificationAdapter
from nextinai.notifiers.models import DeliveryResult, NotificationMessage, NotificationTarget
from nextinai.services.contracts import NotificationDispatchRequest, NotificationService
from nextinai.services.digest_service import AgenticDigestService
from nextinai.storage.files import FileStorage, ensure_workspace


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


@dataclass(slots=True)
class NotificationContent:
    message: NotificationMessage
    content_hash: str


class AgenticNotificationService(NotificationService):
    """Send agent-generated digest or report content through configured channels."""

    def __init__(
        self,
        storage: FileStorage | None = None,
        digest_service: AgenticDigestService | None = None,
        adapters: dict[DeliveryChannel, NotificationAdapter] | None = None,
    ) -> None:
        self.settings = get_settings()
        self.logger = get_logger("notification")
        self.storage = storage or _build_storage()
        self.digest_service = digest_service or AgenticDigestService(storage=self.storage)
        self.adapters = adapters or {
            DeliveryChannel.EMAIL: EmailNotificationAdapter(self.settings),
            DeliveryChannel.WEBHOOK: WebhookNotificationAdapter(self.settings),
        }

    def send(
        self,
        channel: str,
        content_kind: str = "digest",
        scope: str = "daily",
        briefing_view: str = "flash",
        suppress_duplicates: bool = False,
        duplicate_window_hours: int = 24,
        report_title: str | None = None,
        target: str | None = None,
    ) -> str:
        log_event(
            self.logger,
            "开始发送通知",
            channel=channel,
            content_kind=content_kind,
            scope=scope,
            briefing_view=briefing_view,
            suppress_duplicates=suppress_duplicates,
            report_title=report_title,
            target=target,
        )
        request = NotificationDispatchRequest(
            channel=channel,
            content_kind=content_kind,
            scope=scope,
            briefing_view=briefing_view,
            suppress_duplicates=suppress_duplicates,
            duplicate_window_hours=duplicate_window_hours,
            report_title=report_title,
            target=target,
        )
        channel_enum = DeliveryChannel(request.channel)
        notification_target = self._resolve_target(channel_enum, request.target)
        content = self._build_content(request)
        if request.suppress_duplicates and self._should_suppress(content, notification_target, request):
            self._record_suppressed_delivery(request, content, notification_target)
            log_event(self.logger, "通知被抑制", channel=channel_enum.value, target=notification_target.destination)
            return (
                f"{channel_enum.value} 通知已抑制：目标={notification_target.destination}，"
                f"内容={content.message.title}"
            )
        adapter = self.adapters[channel_enum]
        result = adapter.deliver(content.message, notification_target)
        self._record_delivery(request, content, notification_target, result)
        log_event(
            self.logger,
            "通知发送完成",
            channel=channel_enum.value,
            target=notification_target.destination,
            status=result.status.value,
            title=content.message.title,
        )
        return (
            f"{channel_enum.value} 通知已处理：状态={result.status.value}，"
            f"目标={notification_target.destination}，内容={content.message.title}"
        )

    def _resolve_target(self, channel: DeliveryChannel, target: str | None) -> NotificationTarget:
        if channel is DeliveryChannel.EMAIL:
            destination = target or self.settings.default_notification_email
            if not destination:
                raise ValueError("未配置默认邮件目标，且本次未指定 --target。")
            return NotificationTarget(channel=channel, destination=str(destination))
        destination = target or self.settings.webhook_base_url
        if not destination:
            raise ValueError("未配置 Webhook 地址，且本次未指定 --target。")
        return NotificationTarget(channel=channel, destination=destination)

    def _build_content(self, request: NotificationDispatchRequest) -> NotificationContent:
        if request.content_kind == "digest":
            return self._build_digest_content(request.scope, request.briefing_view)
        if request.content_kind == "report":
            return self._build_report_content(request.report_title)
        raise ValueError("content kind 仅支持 digest 或 report。")

    def _build_digest_content(self, scope: str, briefing_view: str) -> NotificationContent:
        if briefing_view == "flash":
            digest = self._find_latest_digest(scope)
            if digest is None:
                self.digest_service.generate(scope)
                digest = self._find_latest_digest(scope)
            if digest is None:
                raise ValueError("未找到可发送的简报。")
            title = digest["title"]
            body = digest["markdown_body"]
            content_ref = digest["digest_key"]
            content_hash = digest["content_hash"]
            metadata = {"scope": digest["scope"], "created_at": digest["created_at"], "view": "flash"}
        else:
            briefing = self.digest_service.generate_briefing(scope, briefing_view)
            title = briefing.title
            body = briefing.content_markdown
            content_ref = briefing.briefing_id
            content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
            metadata = {"scope": scope, "view": briefing.view, "created_at": briefing.created_at}
        message = NotificationMessage(
            content_kind="digest",
            content_ref=content_ref,
            title=title,
            body=body,
            summary=self._extract_summary(body),
            metadata=metadata,
        )
        return NotificationContent(message=message, content_hash=content_hash)

    def _build_report_content(self, report_title: str | None) -> NotificationContent:
        analyses = [
            item
            for item in self.storage.load_collection("analysis_results")
            if item.get("analysis_kind") == "report_interpretation"
        ]
        if report_title:
            analyses = [item for item in analyses if item.get("title") == report_title]
        if not analyses:
            label = report_title or "最新报告"
            raise ValueError(f"未找到可发送的报告解读：{label}")
        published_at_by_fingerprint = {
            item.get("dedupe_fingerprint"): item.get("published_at", "")
            for item in self.storage.load_collection("content_items")
        }
        analyses.sort(
            key=lambda item: (
                published_at_by_fingerprint.get(str(item.get("source_ref", "")).removeprefix("report:"), ""),
                item.get("title", ""),
            ),
            reverse=True,
        )
        report = analyses[0]
        body = (
            f"# {report['title']}\n\n"
            f"## 事实摘要\n{report.get('factual_summary', '无')}\n\n"
            f"## 解读分析\n{report.get('interpreted_summary', '无')}\n"
        )
        source_ref = str(report["source_ref"])
        message = NotificationMessage(
            content_kind="report",
            content_ref=source_ref,
            title=f"NextInAI 报告解读：{report['title']}",
            body=body,
            summary=report.get("factual_summary", "无"),
            metadata={"source_ref": source_ref, "is_partial": bool(report.get("is_partial"))},
        )
        return NotificationContent(
            message=message,
            content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        )

    def _record_delivery(
        self,
        request: NotificationDispatchRequest,
        content: NotificationContent,
        target: NotificationTarget,
        result: DeliveryResult,
    ) -> None:
        deliveries = self.storage.load_collection("deliveries")
        deliveries.append(
            {
                "delivery_id": str(uuid4()),
                "channel": target.channel.value,
                "target": target.destination,
                "status": result.status.value,
                "content_kind": request.content_kind,
                "content_ref": content.message.content_ref,
                "content_hash": content.content_hash,
                "message_title": content.message.title,
                "scope": request.scope,
                "report_title": request.report_title,
                "detail": result.detail,
                "attempt_count": len(result.attempts),
                "attempts_json": [attempt.to_dict() for attempt in result.attempts],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.storage.save_collection("deliveries", deliveries)

    def _record_suppressed_delivery(
        self,
        request: NotificationDispatchRequest,
        content: NotificationContent,
        target: NotificationTarget,
    ) -> None:
        deliveries = self.storage.load_collection("deliveries")
        deliveries.append(
            {
                "delivery_id": str(uuid4()),
                "channel": target.channel.value,
                "target": target.destination,
                "status": DeliveryStatus.SUPPRESSED.value,
                "content_kind": request.content_kind,
                "content_ref": content.message.content_ref,
                "content_hash": content.content_hash,
                "message_title": content.message.title,
                "scope": request.scope,
                "report_title": request.report_title,
                "detail": f"duplicate_suppressed:{request.duplicate_window_hours}h",
                "attempt_count": 0,
                "attempts_json": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.storage.save_collection("deliveries", deliveries)

    def _should_suppress(
        self,
        content: NotificationContent,
        target: NotificationTarget,
        request: NotificationDispatchRequest,
    ) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=request.duplicate_window_hours)
        deliveries = self.storage.load_collection("deliveries")
        for item in reversed(deliveries):
            if item.get("channel") != target.channel.value:
                continue
            if item.get("target") != target.destination:
                continue
            if item.get("content_hash") != content.content_hash:
                continue
            if item.get("status") != DeliveryStatus.SUCCESS.value:
                continue
            created_at = item.get("created_at")
            if not created_at:
                continue
            if parse_datetime(created_at) >= cutoff:
                return True
        return False

    def _find_latest_digest(self, scope: str) -> dict[str, Any] | None:
        digests = [item for item in self.storage.load_collection("digests") if item.get("scope") == scope]
        if not digests:
            return None
        digests.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return digests[0]

    @staticmethod
    def _extract_summary(markdown: str) -> str:
        lines = [line.strip() for line in markdown.splitlines() if line.strip()]
        if len(lines) >= 2:
            return lines[1][:240]
        return lines[0][:240] if lines else "NextInAI 通知"
