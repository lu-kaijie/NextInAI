"""Service registry for CLI composition."""

from dataclasses import dataclass

from nextinai.services.contracts import (
    CapabilityService,
    DigestService,
    NotificationService,
    ReportService,
    SubscriptionService,
    TrendingService,
)
from nextinai.services.capabilities import UnifiedCapabilityService
from nextinai.services.digest_service import AgenticDigestService
from nextinai.services.report_agent import AgenticReportService
from nextinai.services.github_subscriptions import GitHubSubscriptionService
from nextinai.services.github_trending import GitHubTrendingService
from nextinai.services.notification_service import AgenticNotificationService
from nextinai.storage.files import FileStorage, ensure_workspace
from nextinai.core.config import get_settings


@dataclass(slots=True)
class ServiceRegistry:
    subscription_service: SubscriptionService
    trending_service: TrendingService
    report_service: ReportService
    digest_service: DigestService
    notification_service: NotificationService
    capability_service: CapabilityService


def build_service_registry(storage: FileStorage | None = None) -> ServiceRegistry:
    """Build a minimal service registry for the CLI layer."""

    if storage is None:
        settings = get_settings()
        ensure_workspace(settings)
        storage = FileStorage(settings.data_dir)
    subscription_service = GitHubSubscriptionService(storage=storage)
    report_service = AgenticReportService(storage=storage)
    digest_service = AgenticDigestService(storage=storage, subscription_service=subscription_service)
    notification_service = AgenticNotificationService(storage=storage, digest_service=digest_service)
    trending_service = GitHubTrendingService()
    capability_service = UnifiedCapabilityService(
        storage=storage,
        subscription_service=subscription_service,
        trending_service=trending_service,
        report_service=report_service,
        digest_service=digest_service,
        notification_service=notification_service,
    )
    return ServiceRegistry(
        subscription_service=subscription_service,
        trending_service=trending_service,
        report_service=report_service,
        digest_service=digest_service,
        notification_service=notification_service,
        capability_service=capability_service,
    )
