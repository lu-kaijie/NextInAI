"""Agent-centric service for AI report collection and interpretation."""

from __future__ import annotations

import hashlib
from typing import Any

from nextinai.agents import IntelligenceAgent, OpenAIIntelligenceAgent, RuleBasedIntelligenceAgent
from nextinai.collectors.reports import DEFAULT_REPORT_SOURCES, CollectedReportItem, ReportSource, ReportSourceCollector
from nextinai.core.config import get_settings
from nextinai.digests.exporters import DigestExporter
from nextinai.core.logging import build_progress_callback, get_logger, log_error, log_event
from nextinai.domain.enums import AnalysisKind, EventSignal, SourceKind
from nextinai.services.contracts import ReportService
from nextinai.storage.files import FileStorage, ensure_workspace


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


class AgenticReportService(ReportService):
    """Collect reports and interpret them through a dedicated agent."""

    def __init__(
        self,
        storage: FileStorage | None = None,
        collector: ReportSourceCollector | None = None,
        agent: IntelligenceAgent | None = None,
        sources: list[ReportSource] | None = None,
    ) -> None:
        settings = get_settings()
        self.logger = get_logger("reports")
        self.storage = storage or _build_storage()
        self.collector = collector or ReportSourceCollector()
        self.sources = sources or DEFAULT_REPORT_SOURCES
        self.exporter = DigestExporter()
        self.report_output_dir = settings.report_output_dir
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

    def fetch_reports(self, source_group: str, progress_callback=None) -> str:
        selected_sources = [source for source in self.sources if source.group == source_group]
        if not selected_sources:
            raise ValueError(f"未找到来源组：{source_group}")
        progress = build_progress_callback(self.logger, progress_callback)
        log_event(self.logger, "开始抓取报告来源组", source_group=source_group, source_count=len(selected_sources))

        content_items = self.storage.load_collection("content_items")
        analysis_results = self.storage.load_collection("analysis_results")
        report_skips = self.storage.load_collection("report_skips")
        content_index = {item["dedupe_fingerprint"] for item in content_items}
        analysis_index = {item["source_ref"] for item in analysis_results}

        created = 0
        interpreted = 0
        skipped = 0
        titles: list[str] = []
        for source in selected_sources:
            progress(f"开始抓取来源：{source.name}")
            try:
                items = self.collector.collect(source, progress_callback=progress)
            except Exception as exc:
                report_skips.append({"source": source.name, "reason": str(exc)})
                skipped += 1
                log_error(self.logger, "来源抓取失败", source=source.name, error=exc)
                progress(f"来源抓取失败：{source.name}，原因：{exc}")
                continue

            progress(f"来源抓取完成：{source.name}，获得 {len(items)} 篇候选文章")
            for item in items:
                fingerprint = self._build_fingerprint(item)
                source_ref = f"report:{fingerprint}"
                is_duplicate_content = fingerprint in content_index
                if is_duplicate_content and source_ref in analysis_index:
                    report_skips.append({"source": source.name, "title": item.title, "reason": "duplicate"})
                    skipped += 1
                    progress(f"[{source.name}] 跳过重复文章：{item.title}")
                    continue
                if not item.summary_text and not item.body_text:
                    report_skips.append({"source": source.name, "title": item.title, "reason": "unreadable"})
                    skipped += 1
                    progress(f"[{source.name}] 跳过不可读文章：{item.title}")
                    continue

                if not is_duplicate_content:
                    content_items.append(self._build_content_record(item, fingerprint))
                    content_index.add(fingerprint)
                    created += 1
                    titles.append(item.title)

                if source_ref in analysis_index:
                    progress(f"[{source.name}] 已有解读，跳过：{item.title}")
                    continue
                progress(f"[{source.name}] 正在解读：{item.title}")
                interpretation = self.agent.interpret_report(
                    title=item.title,
                    source_name=item.source_name,
                    url=item.url,
                    summary_text=item.summary_text,
                    body_text=item.body_text,
                )
                analysis_results.append(
                    {
                        "analysis_kind": AnalysisKind.REPORT_INTERPRETATION.value,
                        "source_ref": source_ref,
                        "title": item.title,
                        "factual_summary": interpretation.factual_summary,
                        "interpreted_summary": interpretation.interpreted_summary,
                        "evidence_json": interpretation.evidence,
                        "is_partial": interpretation.is_partial,
                    }
                )
                analysis_index.add(source_ref)
                interpreted += 1
                progress(f"[{source.name}] 解读完成：{item.title}")

        self.storage.save_collection("content_items", content_items)
        self.storage.save_collection("analysis_results", analysis_results)
        self.storage.save_collection("report_skips", report_skips)

        titles_preview = "；".join(titles[:5]) if titles else "无新报告"
        summary = (
            f"报告采集完成：新增 {created} 条，解读 {interpreted} 条，跳过 {skipped} 条。"
            f"本轮重点：{titles_preview}"
        )
        log_event(
            self.logger,
            "报告抓取完成",
            source_group=source_group,
            created=created,
            interpreted=interpreted,
            skipped=skipped,
        )
        return summary

    def list_sources(self, source_group: str | None = None) -> list[dict[str, str | int | None]]:
        content_items = self.storage.load_collection("content_items")
        rows: list[dict[str, str | int | None]] = []
        for source in self.sources:
            if source_group is not None and source.group != source_group:
                continue
            matched = [
                item
                for item in content_items
                if item.get("source_kind") == SourceKind.AI_REPORT.value and item.get("source_key") == source.name
            ]
            latest = max((item.get("published_at") or "" for item in matched), default=None)
            rows.append(
                {
                    "source_name": source.name,
                    "group": source.group,
                    "kind": source.kind,
                    "url": source.url,
                    "report_count": len(matched),
                    "latest_published_at": latest,
                }
            )
        return rows

    def list_reports(self, source_name: str | None = None, limit: int = 10) -> list[dict[str, str | bool | None]]:
        analysis_index = {
            row.get("source_ref"): row
            for row in self.storage.load_collection("analysis_results")
            if row.get("analysis_kind") == AnalysisKind.REPORT_INTERPRETATION.value
        }
        rows = [
            item
            for item in self.storage.load_collection("content_items")
            if item.get("source_kind") == SourceKind.AI_REPORT.value
            and (source_name is None or item.get("source_key") == source_name)
        ]
        rows.sort(key=lambda item: (item.get("published_at") or "", item.get("title") or ""), reverse=True)
        reports: list[dict[str, str | bool | None]] = []
        for item in rows[:limit]:
            report_id = f"report:{item['dedupe_fingerprint']}"
            analysis = analysis_index.get(report_id)
            reports.append(
                {
                    "report_id": report_id,
                    "source_name": item.get("source_key"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "published_at": item.get("published_at"),
                    "summary": (analysis or {}).get("factual_summary") or item.get("summary_text"),
                    "has_analysis": analysis is not None,
                    "is_partial": bool(item.get("partial")),
                }
            )
        return reports

    def get_report_detail(self, report_id: str) -> dict[str, str | bool | None] | None:
        fingerprint = report_id.removeprefix("report:")
        content = next(
            (
                item
                for item in self.storage.load_collection("content_items")
                if item.get("source_kind") == SourceKind.AI_REPORT.value
                and item.get("dedupe_fingerprint") == fingerprint
            ),
            None,
        )
        if content is None:
            return None
        analysis = next(
            (
                item
                for item in self.storage.load_collection("analysis_results")
                if item.get("analysis_kind") == AnalysisKind.REPORT_INTERPRETATION.value
                and item.get("source_ref") == report_id
            ),
            None,
        )
        return {
            "report_id": report_id,
            "source_name": str(content.get("source_key") or ""),
            "title": str(content.get("title") or ""),
            "url": str(content.get("url") or ""),
            "published_at": content.get("published_at"),
            "summary_text": content.get("summary_text"),
            "body_text": content.get("body_text"),
            "factual_summary": (analysis or {}).get("factual_summary"),
            "interpreted_summary": (analysis or {}).get("interpreted_summary"),
            "has_analysis": analysis is not None,
            "is_partial": bool(content.get("partial")),
        }

    def export_report(self, report_id: str, formats: list[str]) -> dict[str, str]:
        detail = self.get_report_detail(report_id)
        if detail is None:
            raise ValueError("未找到可导出的报告。")
        markdown = self._render_report_markdown(detail)
        slug = self._build_export_slug(detail)
        exported: dict[str, str] = {}
        if "md" in formats:
            path = self.exporter.export_markdown(markdown, self.report_output_dir / f"{slug}.md")
            exported["md"] = str(path)
        if "pdf" in formats:
            path = self.exporter.export_pdf(markdown, self.report_output_dir / f"{slug}.pdf")
            exported["pdf"] = str(path)
        return exported

    def export_report_summary(
        self,
        source_name: str | None,
        limit: int,
        formats: list[str],
    ) -> dict[str, str]:
        reports = self.list_reports(source_name=source_name, limit=limit)
        title = f"{source_name or 'all-sources'}-report-summary"
        markdown = self._render_report_summary_markdown(source_name, reports)
        slug = self._build_export_slug({"title": title})
        exported: dict[str, str] = {}
        if "md" in formats:
            path = self.exporter.export_markdown(markdown, self.report_output_dir / f"{slug}.md")
            exported["md"] = str(path)
        if "pdf" in formats:
            path = self.exporter.export_pdf(markdown, self.report_output_dir / f"{slug}.pdf")
            exported["pdf"] = str(path)
        return exported

    @staticmethod
    def _build_fingerprint(item: CollectedReportItem) -> str:
        return hashlib.sha256(f"{item.source_name}|{item.url}|{item.title}".encode("utf-8")).hexdigest()

    @staticmethod
    def _build_content_record(item: CollectedReportItem, fingerprint: str) -> dict[str, Any]:
        return {
            "source_kind": SourceKind.AI_REPORT.value,
            "source_key": item.source_name,
            "signal_type": EventSignal.REPORT_PUBLICATION.value,
            "title": item.title,
            "url": item.url,
            "external_id": None,
            "published_at": item.published_at,
            "summary_text": item.summary_text,
            "body_text": item.body_text,
            "metadata_json": item.metadata_json,
            "dedupe_fingerprint": fingerprint,
            "partial": item.partial,
        }

    @staticmethod
    def _render_report_markdown(detail: dict[str, str | bool | None]) -> str:
        lines = [
            f"# {detail['title']}",
            "",
            f"- 来源: {detail['source_name']}",
            f"- 发布时间: {detail.get('published_at') or '未知'}",
            f"- 链接: {detail['url']}",
            "",
            "## 事实摘要",
            str(detail.get("factual_summary") or detail.get("summary_text") or "暂无"),
            "",
            "## 解读分析",
            str(detail.get("interpreted_summary") or "暂无"),
        ]
        body_text = detail.get("body_text")
        if body_text:
            lines.extend(["", "## 正文摘录", str(body_text)])
        return "\n".join(lines).strip()

    @staticmethod
    def _build_export_slug(detail: dict[str, str | bool | None]) -> str:
        title = str(detail.get("title") or "report")
        normalized = "".join(char.lower() if char.isalnum() else "-" for char in title)
        normalized = "-".join(part for part in normalized.split("-") if part)
        return f"report-{normalized}"

    @staticmethod
    def _render_report_summary_markdown(
        source_name: str | None,
        reports: list[dict[str, str | bool | None]],
    ) -> str:
        title = f"{source_name or '全部来源'} 报告摘要"
        lines = [f"# {title}", ""]
        if not reports:
            lines.append("当前没有可导出的报告摘要。")
            return "\n".join(lines)
        for index, report in enumerate(reports, start=1):
            lines.extend(
                [
                    f"## {index}. {report['title']}",
                    f"- 来源: {report['source_name']}",
                    f"- 发布时间: {report.get('published_at') or '未知'}",
                    f"- 事实摘要: {report.get('summary') or '暂无'}",
                    f"- 链接: {report.get('url') or '无'}",
                    "",
                ]
            )
        return "\n".join(lines).strip()
