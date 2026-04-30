"""Service registry for CLI composition."""

from dataclasses import dataclass

from nextinai.services.contracts import (
    DigestService,
    NotificationService,
    ReportService,
    SubscriptionService,
    TrendingService,
)
from nextinai.services.digest_service import AgenticDigestService
from nextinai.services.report_agent import AgenticReportService
from nextinai.services.github_subscriptions import GitHubSubscriptionService
from nextinai.services.github_trending import GitHubTrendingService
from nextinai.services.notification_service import AgenticNotificationService


@dataclass(slots=True)
class ServiceRegistry:
    subscription_service: SubscriptionService
    trending_service: TrendingService
    report_service: ReportService
    digest_service: DigestService
    notification_service: NotificationService


def build_service_registry() -> ServiceRegistry:
    """Build a minimal service registry for the CLI layer."""

    return ServiceRegistry(
        subscription_service=GitHubSubscriptionService(),
        trending_service=GitHubTrendingService(),
        report_service=AgenticReportService(),
        digest_service=AgenticDigestService(),
        notification_service=AgenticNotificationService(),
    )
