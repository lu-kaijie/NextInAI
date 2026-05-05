"""Service contracts and DTOs used by the CLI layer."""

from dataclasses import dataclass


@dataclass(slots=True)
class SubscriptionRecord:
    repository: str
    lookback_hours: int
    refresh_minutes: int


@dataclass(slots=True)
class NotificationDispatchRequest:
    channel: str
    content_kind: str = "digest"
    scope: str = "daily"
    briefing_view: str = "flash"
    suppress_duplicates: bool = False
    duplicate_window_hours: int = 24
    report_title: str | None = None
    target: str | None = None


class SubscriptionService:
    def add_subscription(self, repository: str, lookback_hours: int, refresh_minutes: int) -> str:
        raise NotImplementedError

    def list_subscriptions(self) -> list[dict[str, int | str]]:
        raise NotImplementedError

    def sync_subscriptions(self, repository: str | None = None) -> dict[str, int | list[str]]:
        raise NotImplementedError

    def summarize_repository(self, repository: str, hours: int = 24) -> str:
        raise NotImplementedError

    def export_repository_summary(self, repository: str, hours: int, formats: list[str]) -> dict[str, str]:
        raise NotImplementedError


class TrendingService:
    def get_trending(self, window: str, limit: int) -> str:
        raise NotImplementedError

    def export_trending(self, window: str, limit: int, formats: list[str]) -> dict[str, str]:
        raise NotImplementedError


class ReportService:
    def fetch_reports(
        self,
        source_group: str,
        progress_callback=None,
        source_role: str | None = None,
    ) -> str:
        raise NotImplementedError

    def import_report_url(self, url: str, progress_callback=None) -> dict[str, str | bool | None]:
        raise NotImplementedError

    def list_sources(
        self,
        source_group: str | None = None,
        source_category: str | None = None,
        source_role: str | None = None,
    ) -> list[dict[str, str | int | bool | None]]:
        raise NotImplementedError

    def list_reports(
        self,
        source_name: str | None = None,
        limit: int = 10,
        source_category: str | None = None,
        source_role: str | None = None,
    ) -> list[dict[str, str | bool | None]]:
        raise NotImplementedError

    def list_daily_news(
        self,
        source_name: str | None = None,
        limit: int = 10,
        source_category: str | None = None,
        window: str = "daily",
    ) -> list[dict[str, str | bool | None]]:
        raise NotImplementedError

    def get_report_detail(self, report_id: str) -> dict[str, str | bool | None] | None:
        raise NotImplementedError

    def generate_deep_report_reading(self, report_id: str, force: bool = False) -> dict[str, str | bool | None]:
        raise NotImplementedError

    def generate_report_excerpt_translation(
        self,
        report_id: str,
        force: bool = False,
    ) -> dict[str, str | bool | None]:
        raise NotImplementedError

    def export_report(self, report_id: str, formats: list[str]) -> dict[str, str]:
        raise NotImplementedError

    def export_report_summary(
        self,
        source_name: str | None,
        limit: int,
        formats: list[str],
        source_category: str | None = None,
        source_role: str | None = None,
    ) -> dict[str, str]:
        raise NotImplementedError


class DigestService:
    def generate(self, scope: str) -> str:
        raise NotImplementedError

    def export(self, scope: str, formats: list[str]) -> dict[str, str]:
        raise NotImplementedError


class NotificationService:
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
        raise NotImplementedError


class CapabilityService:
    def get_trending_events(self, window: str, limit: int = 10) -> list[dict[str, object]]:
        raise NotImplementedError

    def get_repo_update_events(self, repository: str, hours: int = 24) -> list[dict[str, object]]:
        raise NotImplementedError

    def get_report_events(
        self,
        source_name: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        raise NotImplementedError

    def get_event_detail(self, event_id: str) -> dict[str, object] | None:
        raise NotImplementedError

    def render_briefing_preview(self, scope: str, view: str, events: list[dict[str, object]]) -> str:
        raise NotImplementedError

    def list_delivery_tasks(self) -> list[dict[str, object]]:
        raise NotImplementedError

    def create_delivery_task(
        self,
        *,
        channel: str,
        target: str,
        scope: str,
        view: str,
        schedule: str | None,
    ) -> dict[str, object]:
        raise NotImplementedError

    def delete_delivery_task(self, task_id: str) -> bool:
        raise NotImplementedError

    def add_subscription(self, repository: str, lookback_hours: int, refresh_minutes: int) -> str:
        raise NotImplementedError

    def list_subscriptions(self) -> list[dict[str, int | str]]:
        raise NotImplementedError

    def sync_subscriptions(self, repository: str | None = None) -> dict[str, int | list[str]]:
        raise NotImplementedError

    def summarize_repository(self, repository: str, hours: int = 24) -> str:
        raise NotImplementedError

    def export_repository_summary(self, repository: str, hours: int, formats: list[str]) -> dict[str, str]:
        raise NotImplementedError

    def get_trending_markdown(self, window: str, limit: int) -> str:
        raise NotImplementedError

    def export_trending(self, window: str, limit: int, formats: list[str]) -> dict[str, str]:
        raise NotImplementedError

    def fetch_reports(
        self,
        source_group: str,
        progress_callback=None,
        source_role: str | None = None,
    ) -> str:
        raise NotImplementedError

    def import_report_url(self, url: str, progress_callback=None) -> dict[str, str | bool | None]:
        raise NotImplementedError

    def list_report_sources(
        self,
        source_group: str | None = None,
        source_category: str | None = None,
        source_role: str | None = None,
    ) -> list[dict[str, str | int | bool | None]]:
        raise NotImplementedError

    def list_reports(
        self,
        source_name: str | None = None,
        limit: int = 10,
        source_category: str | None = None,
        source_role: str | None = None,
    ) -> list[dict[str, str | bool | None]]:
        raise NotImplementedError

    def list_daily_news(
        self,
        source_name: str | None = None,
        limit: int = 10,
        source_category: str | None = None,
        window: str = "daily",
    ) -> list[dict[str, str | bool | None]]:
        raise NotImplementedError

    def get_report_detail(self, report_id: str) -> dict[str, str | bool | None] | None:
        raise NotImplementedError

    def generate_deep_report_reading(self, report_id: str, force: bool = False) -> dict[str, str | bool | None]:
        raise NotImplementedError

    def generate_report_excerpt_translation(
        self,
        report_id: str,
        force: bool = False,
    ) -> dict[str, str | bool | None]:
        raise NotImplementedError

    def export_report(self, report_id: str, formats: list[str]) -> dict[str, str]:
        raise NotImplementedError

    def export_report_summary(
        self,
        source_name: str | None,
        limit: int,
        formats: list[str],
        source_category: str | None = None,
        source_role: str | None = None,
    ) -> dict[str, str]:
        raise NotImplementedError

    def generate_digest(self, scope: str) -> str:
        raise NotImplementedError

    def export_digest(self, scope: str, formats: list[str]) -> dict[str, str]:
        raise NotImplementedError

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
        raise NotImplementedError
