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


class TrendingService:
    def get_trending(self, window: str, limit: int) -> str:
        raise NotImplementedError


class ReportService:
    def fetch_reports(self, source_group: str, progress_callback=None) -> str:
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
