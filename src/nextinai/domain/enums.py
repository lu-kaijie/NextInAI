"""Shared enums across domain and storage."""

from enum import Enum


class SourceKind(str, Enum):
    GITHUB_REPOSITORY = "github_repository"
    GITHUB_TRENDING = "github_trending"
    AI_REPORT = "ai_report"


class EventSignal(str, Enum):
    RELEASE = "release"
    PULL_REQUEST = "pull_request"
    COMMIT = "commit"
    DOCUMENTATION = "documentation"
    TRENDING_SNAPSHOT = "trending_snapshot"
    REPORT_PUBLICATION = "report_publication"


class AnalysisKind(str, Enum):
    REPOSITORY_SUMMARY = "repository_summary"
    TRENDING_SUMMARY = "trending_summary"
    REPORT_INTERPRETATION = "report_interpretation"
    REPORT_DEEP_READING = "report_deep_reading"
    DIGEST = "digest"


class DeliveryChannel(str, Enum):
    EMAIL = "email"
    WEBHOOK = "webhook"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
