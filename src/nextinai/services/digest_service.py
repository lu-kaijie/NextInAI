"""Digest generation service built on the unified intelligence agent."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nextinai.agents import DigestOverview, IntelligenceAgent, OpenAIIntelligenceAgent, RuleBasedIntelligenceAgent
from nextinai.core.config import get_settings
from nextinai.core.datetime_utils import parse_datetime
from nextinai.digests.exporters import DigestExporter
from nextinai.digests.models import DigestDocument, DigestSection
from nextinai.domain.enums import SourceKind
from nextinai.harness.adapters import BriefingViewBuilder, IntelligenceEventAdapter
from nextinai.harness.models import Briefing
from nextinai.services.contracts import DigestService
from nextinai.services.github_subscriptions import GitHubSubscriptionService
from nextinai.storage.files import FileStorage, ensure_workspace


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


class AgenticDigestService(DigestService):
    """Generate periodic digest documents from collected intelligence."""

    def __init__(
        self,
        storage: FileStorage | None = None,
        agent: IntelligenceAgent | None = None,
        subscription_service: GitHubSubscriptionService | None = None,
    ) -> None:
        settings = get_settings()
        self.storage = storage or _build_storage()
        if agent is not None:
            self.agent = agent
        elif settings.ai_provider == "openai" and settings.openai_api_key:
            self.agent = OpenAIIntelligenceAgent(
                settings.openai_api_key,
                settings.ai_model,
                settings.openai_base_url,
            )
        else:
            self.agent = RuleBasedIntelligenceAgent()
        self.subscription_service = subscription_service or GitHubSubscriptionService(
            storage=self.storage,
            agent=self.agent,
        )
        self.event_adapter = IntelligenceEventAdapter(storage=self.storage, agent=self.agent)
        self.briefing_builder = BriefingViewBuilder()
        self.exporter = DigestExporter()
        self.report_output_dir = settings.report_output_dir

    def generate(self, scope: str) -> str:
        window_start = self._resolve_window_start(scope)
        event_briefing = self._build_event_briefing(scope, window_start, view="flash")
        repo_summaries = self._build_repo_summaries(window_start)
        trending_entries = self._load_trending_entries(window_start)
        report_entries = self._load_report_entries()

        sections = [
            DigestSection(
                title="GitHub 仓库更新",
                entries=[f"```md\n{item}\n```" for item in repo_summaries],
                unavailable_reason=None if repo_summaries else "当前窗口内没有可用仓库更新",
            ),
            DigestSection(
                title="热门 GitHub 项目",
                entries=trending_entries,
                unavailable_reason=None if trending_entries else "当前窗口内没有可用热门榜结果",
            ),
            DigestSection(
                title="AI 报告解读",
                entries=report_entries,
                unavailable_reason=None if report_entries else "当前窗口内没有可用报告解读",
            ),
        ]
        missing_sections = [section.title for section in sections if section.unavailable_reason]
        overview = self.agent.compose_digest_overview(
            scope=scope,
            repo_summaries=repo_summaries,
            trending_entries=trending_entries,
            report_entries=report_entries,
            missing_sections=missing_sections,
        )
        document = DigestDocument(
            title=overview.title,
            scope=scope,
            summary=overview.summary,
            highlights=overview.highlights,
            sections=[
                DigestSection(
                    title="事件快讯视图",
                    entries=[event_briefing.content_markdown],
                    unavailable_reason=None if event_briefing.event_ids else "当前窗口内没有可汇总的事件",
                ),
                *sections,
            ],
        )
        markdown = document.to_markdown()
        self._store_digest(scope, markdown, document)
        return markdown

    def export(self, scope: str, formats: list[str]) -> dict[str, str]:
        digest = self._find_latest_digest(scope)
        if digest is None:
            markdown = self.generate(scope)
            digest = self._find_latest_digest(scope)
            if digest is None:
                raise ValueError("未找到可导出的简报。")
        markdown_body = digest["markdown_body"]
        slug = self._build_slug(scope, digest["title"])
        exported: dict[str, str] = {}
        if "md" in formats:
            md_path = self.exporter.export_markdown(
                markdown_body,
                self.report_output_dir / f"{slug}.md",
            )
            exported["md"] = str(md_path)
        if "pdf" in formats:
            pdf_path = self.exporter.export_pdf(
                markdown_body,
                self.report_output_dir / f"{slug}.pdf",
            )
            exported["pdf"] = str(pdf_path)
            digest["pdf_path"] = str(pdf_path)
            self._persist_digest_update(digest)
        return exported

    @staticmethod
    def _resolve_window_start(scope: str) -> datetime:
        normalized = scope.strip().lower()
        if normalized in {"daily", "1d", "today"}:
            return datetime.now(timezone.utc) - timedelta(days=1)
        if normalized.endswith("d") and normalized[:-1].isdigit():
            return datetime.now(timezone.utc) - timedelta(days=int(normalized[:-1]))
        raise ValueError("digest scope 仅支持 daily、1d 或 Nd 格式，例如 7d。")

    def _build_repo_summaries(self, window_start: datetime) -> list[str]:
        subscriptions = self.storage.load_collection("subscriptions")
        hours = max(1, int((datetime.now(timezone.utc) - window_start).total_seconds() // 3600))
        summaries: list[str] = []
        for item in subscriptions:
            summary = self.subscription_service.summarize_repository(item["repository"], hours)
            if "没有新的仓库更新" in summary:
                continue
            summaries.append(summary)
        return summaries

    def _load_trending_entries(self, window_start: datetime) -> list[str]:
        content_items = self.storage.load_collection("content_items")
        entries: list[str] = []
        for item in content_items:
            if item.get("source_kind") != SourceKind.GITHUB_TRENDING.value:
                continue
            published_at = item.get("published_at")
            if not published_at or parse_datetime(published_at) < window_start:
                continue
            reason = (item.get("metadata_json") or {}).get("why_trending", "无原因说明")
            entries.append(f"- {item['title']}\n  链接: {item['url']}\n  上榜原因: {reason}")
        return entries[:10]

    def _load_report_entries(self) -> list[str]:
        analysis_results = self.storage.load_collection("analysis_results")
        entries: list[str] = []
        for item in analysis_results:
            if item.get("analysis_kind") != "report_interpretation":
                continue
            partial_mark = "（部分解读）" if item.get("is_partial") else ""
            entries.append(
                f"- {item['title']} {partial_mark}\n"
                f"  事实摘要: {item.get('factual_summary', '')}\n"
                f"  解读分析: {item.get('interpreted_summary', '')}"
            )
        return entries[:10]

    def generate_briefing(self, scope: str, view: str = "flash") -> Briefing:
        window_start = self._resolve_window_start(scope)
        return self._build_event_briefing(scope, window_start, view=view)

    def _build_event_briefing(self, scope: str, window_start: datetime, view: str) -> Briefing:
        hours = max(1, int((datetime.now(timezone.utc) - window_start).total_seconds() // 3600))
        subscriptions = self.storage.load_collection("subscriptions")
        events = []
        for item in subscriptions:
            events.extend(self.event_adapter.get_repo_update_events(item["repository"], hours))
        events.extend(self.event_adapter.get_report_events(limit=5))
        events.sort(key=lambda item: (item.importance_score, item.happened_at or ""), reverse=True)
        return self.briefing_builder.build_briefing(scope=scope, view=view, events=events[:8])

    def _store_digest(self, scope: str, markdown: str, document: DigestDocument) -> None:
        digests = self.storage.load_collection("digests")
        digest_key = hashlib.sha256(f"{scope}|{document.title}|{markdown}".encode("utf-8")).hexdigest()
        digests.append(
            {
                "digest_key": digest_key,
                "title": document.title,
                "scope": scope,
                "markdown_body": markdown,
                "pdf_path": None,
                "metadata_json": {"highlights": document.highlights},
                "content_hash": digest_key,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.storage.save_collection("digests", digests)

    def _find_latest_digest(self, scope: str) -> dict | None:
        digests = [item for item in self.storage.load_collection("digests") if item.get("scope") == scope]
        if not digests:
            return None
        digests.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return digests[0]

    def _persist_digest_update(self, updated_digest: dict) -> None:
        digests = self.storage.load_collection("digests")
        for index, item in enumerate(digests):
            if item.get("digest_key") == updated_digest.get("digest_key"):
                digests[index] = updated_digest
                break
        self.storage.save_collection("digests", digests)

    @staticmethod
    def _build_slug(scope: str, title: str) -> str:
        normalized = "".join(ch.lower() if ch.isalnum() else "-" for ch in title)
        normalized = "-".join(part for part in normalized.split("-") if part)
        return f"{scope}-{normalized}"
