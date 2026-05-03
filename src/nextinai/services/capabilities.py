"""Unified capability layer shared by chat and web surfaces."""

from __future__ import annotations

from typing import Any

from nextinai.core.logging import get_logger, log_event
from nextinai.harness.adapters import BriefingViewBuilder, IntelligenceEventAdapter
from nextinai.harness.models import IntelligenceEvent
from nextinai.services.contracts import (
    CapabilityService,
    DigestService,
    NotificationService,
    ReportService,
    SubscriptionService,
    TrendingService,
)
from nextinai.services.task_store import DeliveryTaskStore
from nextinai.storage.files import FileStorage


class UnifiedCapabilityService(CapabilityService):
    """Expose a single capability-oriented interface for chat and web."""

    def __init__(
        self,
        *,
        storage: FileStorage,
        subscription_service: SubscriptionService,
        trending_service: TrendingService,
        report_service: ReportService,
        digest_service: DigestService,
        notification_service: NotificationService,
        event_adapter: IntelligenceEventAdapter | None = None,
        briefing_builder: BriefingViewBuilder | None = None,
        task_store: DeliveryTaskStore | None = None,
    ) -> None:
        self.logger = get_logger("capability")
        self.storage = storage
        self.subscription_service = subscription_service
        self.trending_service = trending_service
        self.report_service = report_service
        self.digest_service = digest_service
        self.notification_service = notification_service
        self.event_adapter = event_adapter or IntelligenceEventAdapter(storage=storage)
        self.briefing_builder = briefing_builder or BriefingViewBuilder()
        self.task_store = task_store or DeliveryTaskStore(storage)

    def get_trending_events(self, window: str, limit: int = 10) -> list[dict[str, Any]]:
        log_event(self.logger, "查询热门事件", window=window, limit=limit)
        return self._persist_and_serialize(self.event_adapter.get_trending_events(window, limit))

    def get_repo_update_events(self, repository: str, hours: int = 24) -> list[dict[str, Any]]:
        log_event(self.logger, "查询仓库更新事件", repository=repository, hours=hours)
        return self._persist_and_serialize(self.event_adapter.get_repo_update_events(repository, hours))

    def get_report_events(self, source_name: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        log_event(self.logger, "查询报告事件", source_name=source_name, limit=limit)
        return self._persist_and_serialize(self.event_adapter.get_report_events(source_name=source_name, limit=limit))

    def get_event_detail(self, event_id: str) -> dict[str, Any] | None:
        log_event(self.logger, "查询事件详情", event_id=event_id)
        return next(
            (row for row in self.storage.load_collection("events") if row.get("event_id") == event_id),
            None,
        )

    def render_briefing_preview(self, scope: str, view: str, events: list[dict[str, Any]]) -> str:
        log_event(self.logger, "生成简报预览", scope=scope, view=view, event_count=len(events))
        briefing = self.briefing_builder.build_briefing(
            scope=scope,
            view=view,
            events=[self._event_from_dict(item) for item in events],
        )
        return briefing.content_markdown

    def list_delivery_tasks(self) -> list[dict[str, Any]]:
        log_event(self.logger, "列出推送任务")
        return self.task_store.list_tasks()

    def create_delivery_task(
        self,
        *,
        channel: str,
        target: str,
        scope: str,
        view: str,
        schedule: str | None,
    ) -> dict[str, Any]:
        log_event(self.logger, "创建推送任务", channel=channel, target=target, scope=scope, view=view, schedule=schedule)
        return self.task_store.create_task(
            channel=channel,
            target=target,
            scope=scope,
            view=view,
            schedule=schedule,
        ).to_dict()

    def delete_delivery_task(self, task_id: str) -> bool:
        log_event(self.logger, "删除推送任务", task_id=task_id)
        return self.task_store.delete_task(task_id)

    def add_subscription(self, repository: str, lookback_hours: int, refresh_minutes: int) -> str:
        log_event(self.logger, "能力层新增订阅", repository=repository)
        return self.subscription_service.add_subscription(repository, lookback_hours, refresh_minutes)

    def list_subscriptions(self) -> list[dict[str, int | str]]:
        return self.subscription_service.list_subscriptions()

    def sync_subscriptions(self, repository: str | None = None) -> dict[str, int | list[str]]:
        log_event(self.logger, "能力层同步订阅", repository=repository)
        return self.subscription_service.sync_subscriptions(repository)

    def summarize_repository(self, repository: str, hours: int = 24) -> str:
        return self.subscription_service.summarize_repository(repository, hours)

    def export_repository_summary(self, repository: str, hours: int, formats: list[str]) -> dict[str, str]:
        log_event(self.logger, "导出仓库摘要", repository=repository, hours=hours, formats=",".join(formats))
        return self.subscription_service.export_repository_summary(repository, hours, formats)

    def get_trending_markdown(self, window: str, limit: int) -> str:
        return self.trending_service.get_trending(window, limit)

    def export_trending(self, window: str, limit: int, formats: list[str]) -> dict[str, str]:
        log_event(self.logger, "导出热门榜", window=window, limit=limit, formats=",".join(formats))
        return self.trending_service.export_trending(window, limit, formats)

    def fetch_reports(self, source_group: str, progress_callback=None) -> str:
        log_event(self.logger, "抓取报告来源组", source_group=source_group)
        return self.report_service.fetch_reports(source_group, progress_callback=progress_callback)

    def import_report_url(self, url: str, progress_callback=None) -> dict[str, str | bool | None]:
        log_event(self.logger, "导入单篇报告 URL", url=url)
        return self.report_service.import_report_url(url, progress_callback=progress_callback)

    def list_report_sources(
        self,
        source_group: str | None = None,
        source_category: str | None = None,
    ) -> list[dict[str, str | int | bool | None]]:
        return self.report_service.list_sources(source_group, source_category)

    def list_reports(
        self,
        source_name: str | None = None,
        limit: int = 10,
        source_category: str | None = None,
    ) -> list[dict[str, str | bool | None]]:
        return self.report_service.list_reports(
            source_name=source_name,
            limit=limit,
            source_category=source_category,
        )

    def get_report_detail(self, report_id: str) -> dict[str, str | bool | None] | None:
        return self.report_service.get_report_detail(report_id)

    def generate_deep_report_reading(self, report_id: str, force: bool = False) -> dict[str, str | bool | None]:
        log_event(self.logger, "生成报告深度带读", report_id=report_id, force=force)
        return self.report_service.generate_deep_report_reading(report_id, force=force)

    def generate_report_excerpt_translation(
        self,
        report_id: str,
        force: bool = False,
    ) -> dict[str, str | bool | None]:
        log_event(self.logger, "生成报告正文摘录译文", report_id=report_id, force=force)
        return self.report_service.generate_report_excerpt_translation(report_id, force=force)

    def export_report(self, report_id: str, formats: list[str]) -> dict[str, str]:
        log_event(self.logger, "导出报告详情", report_id=report_id, formats=",".join(formats))
        return self.report_service.export_report(report_id, formats)

    def export_report_summary(
        self,
        source_name: str | None,
        limit: int,
        formats: list[str],
        source_category: str | None = None,
    ) -> dict[str, str]:
        log_event(
            self.logger,
            "导出报告摘要",
            source_name=source_name,
            source_category=source_category,
            limit=limit,
            formats=",".join(formats),
        )
        return self.report_service.export_report_summary(
            source_name,
            limit,
            formats,
            source_category=source_category,
        )

    def generate_digest(self, scope: str) -> str:
        log_event(self.logger, "生成简报", scope=scope)
        return self.digest_service.generate(scope)

    def export_digest(self, scope: str, formats: list[str]) -> dict[str, str]:
        log_event(self.logger, "导出简报", scope=scope, formats=",".join(formats))
        return self.digest_service.export(scope, formats)

    def send_notification(
        self,
        *,
        channel: str,
        content_kind: str = "digest",
        scope: str = "daily",
        briefing_view: str = "flash",
        report_title: str | None = None,
        target: str | None = None,
    ) -> str:
        log_event(self.logger, "发送通知", channel=channel, content_kind=content_kind, scope=scope, briefing_view=briefing_view)
        return self.notification_service.send(
            channel=channel,
            content_kind=content_kind,
            scope=scope,
            briefing_view=briefing_view,
            report_title=report_title,
            target=target,
        )

    def _persist_and_serialize(self, events: list[IntelligenceEvent]) -> list[dict[str, Any]]:
        self.event_adapter.persist_events(events)
        return [event.to_dict() for event in events]

    @staticmethod
    def _event_from_dict(payload: dict[str, Any]) -> IntelligenceEvent:
        from nextinai.harness.tools import _event_from_dict

        return _event_from_dict(payload)
