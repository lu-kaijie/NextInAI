"""Agent-centric service for AI report collection and interpretation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from nextinai.agents import IntelligenceAgent, OpenAIIntelligenceAgent, RuleBasedIntelligenceAgent
from nextinai.collectors.reports import (
    DEFAULT_REPORT_SOURCES,
    CollectedReportItem,
    ManualUrlImportError,
    ReportSource,
    ReportSourceCollector,
)
from nextinai.core.config import get_settings
from nextinai.core.logging import build_progress_callback, get_logger, log_error, log_event
from nextinai.digests.exporters import DigestExporter
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
        selected_sources = self._select_sources_for_fetch(source_group)
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

            report_skips = [
                item
                for item in report_skips
                if not (item.get("source") == source.name and not item.get("title"))
            ]

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
                    progress(f"[{source.name}] 已有概览解读，跳过：{item.title}")
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
            f"报告采集完成：新增 {created} 条，概览解读 {interpreted} 条，跳过 {skipped} 条。"
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

    def import_report_url(self, url: str, progress_callback=None) -> dict[str, str | bool | None]:
        progress = build_progress_callback(self.logger, progress_callback)
        progress(f"开始导入文章 URL：{url}")
        try:
            normalized_url = self.collector.normalize_article_url(url)
        except ManualUrlImportError as exc:
            self._record_report_skip(source="手动导入", reason=exc.message, url=url)
            raise ValueError(exc.message) from exc

        content_items = self.storage.load_collection("content_items")
        analysis_results = self.storage.load_collection("analysis_results")
        existing = self._find_content_by_normalized_url(normalized_url, content_items=content_items)
        if existing is not None:
            report_id = f"report:{existing['dedupe_fingerprint']}"
            if not self._should_refresh_existing_content(existing):
                progress(f"命中已有缓存：{existing.get('title') or normalized_url}")
                if not self._find_overview_analysis(report_id, analysis_results=analysis_results):
                    progress("已有正文但缺少概览解读，正在补生成...")
                    self._append_overview_analysis(existing, analysis_results)
                    self.storage.save_collection("analysis_results", analysis_results)
                detail = self.get_report_detail(report_id)
                if detail is None:
                    raise ValueError("命中已有内容，但未能重新读取导入结果。")
                return detail
            progress("命中旧缓存但正文缺失或质量较差，准备重新抓取正文...")

        try:
            item = self.collector.import_url(normalized_url, progress_callback=progress)
        except ManualUrlImportError as exc:
            self._record_report_skip(source="手动导入", reason=exc.message, url=normalized_url)
            raise ValueError(exc.message) from exc

        fingerprint = existing["dedupe_fingerprint"] if existing is not None else self._build_fingerprint(item)
        record = self._build_content_record(item, fingerprint)
        if existing is not None:
            for index, row in enumerate(content_items):
                if row.get("dedupe_fingerprint") == existing["dedupe_fingerprint"]:
                    content_items[index] = record
                    break
            report_id = f"report:{fingerprint}"
            analysis_results = [
                row
                for row in analysis_results
                if not (
                    row.get("source_ref") == report_id
                    and row.get("analysis_kind") == AnalysisKind.REPORT_INTERPRETATION.value
                )
            ]
            self._delete_related_analysis("deep_report_readings", report_id)
            self._delete_related_analysis("report_excerpt_translations", report_id)
        else:
            content_items.append(record)
        self._append_overview_analysis(record, analysis_results)
        self.storage.save_collection("content_items", content_items)
        self.storage.save_collection("analysis_results", analysis_results)
        progress(f"导入完成：{item.title}")
        detail = self.get_report_detail(f"report:{fingerprint}")
        if detail is None:
            raise ValueError("导入完成，但未能读取文章详情。")
        return detail

    def list_sources(
        self,
        source_group: str | None = None,
        source_category: str | None = None,
    ) -> list[dict[str, str | int | bool | None]]:
        content_items = self.storage.load_collection("content_items")
        report_skips = self.storage.load_collection("report_skips")
        rows: list[dict[str, str | int | bool | None]] = []
        for source in self.sources:
            if source_group is not None and source.group != source_group and source_group != "default":
                continue
            if source_category is not None and source.category != source_category:
                continue
            matched = [
                item
                for item in content_items
                if item.get("source_kind") == SourceKind.AI_REPORT.value and item.get("source_key") == source.name
            ]
            issues = [
                item
                for item in report_skips
                if item.get("source") == source.name and item.get("reason") not in {"duplicate"}
            ]
            latest = max((item.get("published_at") or "" for item in matched), default=None)
            rows.append(
                {
                    "source_name": source.name,
                    "group": source.group,
                    "category": source.category,
                    "kind": source.kind,
                    "url": source.url,
                    "description": source.description,
                    "default_enabled": source.default_enabled,
                    "report_count": len(matched),
                    "latest_published_at": latest,
                    "issue_count": len(issues),
                    "last_issue": issues[-1].get("reason") if issues else None,
                }
            )
        rows.sort(key=lambda item: (str(item.get("category") or ""), str(item.get("source_name") or "")))
        return rows

    def list_reports(
        self,
        source_name: str | None = None,
        limit: int = 10,
        source_category: str | None = None,
    ) -> list[dict[str, str | bool | None]]:
        analysis_index = {
            row.get("source_ref"): row
            for row in self.storage.load_collection("analysis_results")
            if row.get("analysis_kind") == AnalysisKind.REPORT_INTERPRETATION.value
        }
        deep_reading_index = {
            row.get("source_ref"): row
            for row in self.storage.load_collection("deep_report_readings")
        }
        rows = []
        for item in self.storage.load_collection("content_items"):
            if item.get("source_kind") != SourceKind.AI_REPORT.value:
                continue
            if source_name is not None and item.get("source_key") != source_name:
                continue
            category = self._resolve_source_category(item)
            if source_category is not None and category != source_category:
                continue
            rows.append(item)
        rows.sort(key=lambda item: (item.get("published_at") or "", item.get("title") or ""), reverse=True)

        reports: list[dict[str, str | bool | None]] = []
        for item in rows[:limit]:
            report_id = f"report:{item['dedupe_fingerprint']}"
            analysis = analysis_index.get(report_id) or {}
            deep_reading = deep_reading_index.get(report_id) or {}
            summary = (
                analysis.get("interpreted_summary")
                or analysis.get("factual_summary")
                or item.get("summary_text")
                or "暂无概览摘要"
            )
            reports.append(
                {
                    "report_id": report_id,
                    "source_name": item.get("source_key"),
                    "source_category": category,
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "published_at": item.get("published_at"),
                    "overview_summary": summary,
                    "factual_summary": analysis.get("factual_summary"),
                    "interpreted_summary": analysis.get("interpreted_summary"),
                    "summary": summary,
                    "has_analysis": bool(analysis),
                    "is_partial": bool(item.get("partial")),
                    "deep_reading_ready": bool(deep_reading),
                    "deep_reading_generated_at": deep_reading.get("generated_at"),
                }
            )
        return reports

    def get_report_detail(self, report_id: str) -> dict[str, str | bool | None] | None:
        content = self._find_content_by_report_id(report_id)
        if content is None:
            return None
        analysis = self._find_overview_analysis(report_id) or {}
        deep_reading = self._find_deep_reading(report_id) or {}
        excerpt_translation = self._find_excerpt_translation(report_id) or {}
        metadata = content.get("metadata_json") or {}
        resolved_category = self._resolve_source_category(content)
        overview_summary = (
            analysis.get("interpreted_summary")
            or analysis.get("factual_summary")
            or content.get("summary_text")
            or "暂无概览摘要"
        )
        can_deep_read = bool(content.get("body_text")) and not bool(content.get("partial"))
        deep_read_block_reason = None if can_deep_read else "当前未获取到完整正文，为避免误导，暂不生成详细解读。"
        return {
            "report_id": report_id,
            "source_name": str(content.get("source_key") or ""),
            "source_category": resolved_category,
            "title": str(content.get("title") or ""),
            "url": str(content.get("url") or ""),
            "published_at": content.get("published_at"),
            "summary_text": content.get("summary_text"),
            "body_text": content.get("body_text"),
            "overview_summary": overview_summary,
            "factual_summary": analysis.get("factual_summary"),
            "interpreted_summary": analysis.get("interpreted_summary"),
            "has_analysis": bool(analysis),
            "is_partial": bool(content.get("partial")),
            "can_deep_read": can_deep_read,
            "deep_read_block_reason": deep_read_block_reason,
            "deep_reading_ready": bool(deep_reading),
            "deep_reading_markdown": deep_reading.get("markdown_body"),
            "deep_reading_summary": deep_reading.get("summary"),
            "deep_reading_generated_at": deep_reading.get("generated_at"),
            "localized_excerpt_text": excerpt_translation.get("translated_text"),
            "localized_excerpt_generated_at": excerpt_translation.get("generated_at"),
            "full_translation_text": excerpt_translation.get("translated_text"),
            "full_translation_generated_at": excerpt_translation.get("generated_at"),
        }

    def generate_deep_report_reading(self, report_id: str, force: bool = False) -> dict[str, str | bool | None]:
        detail = self.get_report_detail(report_id)
        if detail is None:
            raise ValueError("未找到可深读的报告。")
        if not detail.get("can_deep_read"):
            raise ValueError(str(detail.get("deep_read_block_reason") or "当前无法生成详细解读。"))
        if detail.get("deep_reading_ready") and not force:
            return detail

        deep_report_readings = self.storage.load_collection("deep_report_readings")
        content = self._find_content_by_report_id(report_id)
        if content is None:
            raise ValueError("未找到可深读的报告正文。")
        deep_reading = self.agent.deep_read_report(
            title=str(content.get("title") or ""),
            source_name=str(content.get("source_key") or ""),
            url=str(content.get("url") or ""),
            summary_text=content.get("summary_text"),
            body_text=content.get("body_text"),
        )
        record = {
            "analysis_kind": AnalysisKind.REPORT_DEEP_READING.value,
            "source_ref": report_id,
            "title": content.get("title"),
            "summary": deep_reading.summary,
            "markdown_body": deep_reading.markdown_body,
            "evidence_json": deep_reading.evidence,
            "is_partial": deep_reading.is_partial,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": self._build_deep_reading_hash(content),
        }
        replaced = False
        for index, item in enumerate(deep_report_readings):
            if item.get("source_ref") == report_id:
                deep_report_readings[index] = record
                replaced = True
                break
        if not replaced:
            deep_report_readings.append(record)
        self.storage.save_collection("deep_report_readings", deep_report_readings)
        log_event(self.logger, "报告深度带读已生成", report_id=report_id, force=force)
        refreshed = self.get_report_detail(report_id)
        if refreshed is None:
            raise ValueError("深度带读生成后未能重新读取报告详情。")
        return refreshed

    def generate_report_excerpt_translation(
        self,
        report_id: str,
        force: bool = False,
    ) -> dict[str, str | bool | None]:
        detail = self.get_report_detail(report_id)
        if detail is None:
            raise ValueError("未找到报告详情。")
        body_text = str(detail.get("body_text") or "").strip()
        if not body_text:
            return detail
        if detail.get("localized_excerpt_text") and not force:
            return detail

        content = self._find_content_by_report_id(report_id)
        if content is None:
            raise ValueError("未找到报告正文。")
        translated_text = self.agent.translate_report_excerpt(
            title=str(content.get("title") or ""),
            source_name=str(content.get("source_key") or ""),
            excerpt_text=body_text,
        )
        records = self.storage.load_collection("report_excerpt_translations")
        record = {
            "source_ref": report_id,
            "title": content.get("title"),
            "translated_text": translated_text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content_hash": self._build_excerpt_hash(content),
        }
        replaced = False
        for index, item in enumerate(records):
            if item.get("source_ref") == report_id:
                records[index] = record
                replaced = True
                break
        if not replaced:
            records.append(record)
        self.storage.save_collection("report_excerpt_translations", records)
        refreshed = self.get_report_detail(report_id)
        if refreshed is None:
            raise ValueError("正文全文翻译生成后未能重新读取详情。")
        return refreshed

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
        source_category: str | None = None,
    ) -> dict[str, str]:
        reports = self.list_reports(source_name=source_name, limit=limit, source_category=source_category)
        title = self._build_summary_title(source_name, source_category)
        markdown = self._render_report_summary_markdown(title, reports)
        slug = self._build_export_slug({"title": title})
        exported: dict[str, str] = {}
        if "md" in formats:
            path = self.exporter.export_markdown(markdown, self.report_output_dir / f"{slug}.md")
            exported["md"] = str(path)
        if "pdf" in formats:
            path = self.exporter.export_pdf(markdown, self.report_output_dir / f"{slug}.pdf")
            exported["pdf"] = str(path)
        return exported

    def _select_sources_for_fetch(self, source_group: str) -> list[ReportSource]:
        if source_group == "default":
            defaults = [source for source in self.sources if source.default_enabled]
            if defaults:
                return defaults
        return [source for source in self.sources if source.group == source_group or source.category == source_group]

    def _find_content_by_report_id(self, report_id: str) -> dict[str, Any] | None:
        fingerprint = report_id.removeprefix("report:")
        return next(
            (
                item
                for item in self.storage.load_collection("content_items")
                if item.get("source_kind") == SourceKind.AI_REPORT.value
                and item.get("dedupe_fingerprint") == fingerprint
            ),
            None,
        )

    def _find_overview_analysis(
        self,
        report_id: str,
        *,
        analysis_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        rows = analysis_results if analysis_results is not None else self.storage.load_collection("analysis_results")
        return next(
            (
                item
                for item in rows
                if item.get("analysis_kind") == AnalysisKind.REPORT_INTERPRETATION.value
                and item.get("source_ref") == report_id
            ),
            None,
        )

    def _find_deep_reading(self, report_id: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.storage.load_collection("deep_report_readings")
                if item.get("source_ref") == report_id
            ),
            None,
        )

    def _find_excerpt_translation(self, report_id: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.storage.load_collection("report_excerpt_translations")
                if item.get("source_ref") == report_id
            ),
            None,
        )

    def _resolve_source_category(self, content: dict[str, Any]) -> str:
        metadata = content.get("metadata_json") or {}
        category = metadata.get("category")
        if category:
            return str(category)
        source_name = str(content.get("source_key") or "")
        for source in self.sources:
            if source.name == source_name:
                return source.category
        return ""

    @staticmethod
    def _build_fingerprint(item: CollectedReportItem) -> str:
        normalized_url = item.metadata_json.get("normalized_url") or ReportSourceCollector.normalize_article_url(item.url)
        return hashlib.sha256(f"{normalized_url}|{item.title}".encode("utf-8")).hexdigest()

    @staticmethod
    def _build_content_record(item: CollectedReportItem, fingerprint: str) -> dict[str, Any]:
        normalized_url = item.metadata_json.get("normalized_url") or ReportSourceCollector.normalize_article_url(item.url)
        return {
            "source_kind": SourceKind.AI_REPORT.value,
            "source_key": item.source_name,
            "signal_type": EventSignal.REPORT_PUBLICATION.value,
            "title": item.title,
            "url": item.url,
            "normalized_url": normalized_url,
            "external_id": None,
            "published_at": item.published_at,
            "summary_text": item.summary_text,
            "body_text": item.body_text,
            "metadata_json": item.metadata_json,
            "dedupe_fingerprint": fingerprint,
            "partial": item.partial,
        }

    @staticmethod
    def _build_deep_reading_hash(content: dict[str, Any]) -> str:
        raw = f"{content.get('title')}|{content.get('url')}|{content.get('summary_text')}|{content.get('body_text')}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _build_excerpt_hash(content: dict[str, Any]) -> str:
        raw = f"{content.get('title')}|{content.get('url')}|{content.get('body_text')}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _render_report_markdown(detail: dict[str, str | bool | None]) -> str:
        if detail.get("deep_reading_markdown"):
            lines = [
                str(detail["deep_reading_markdown"]).strip(),
                "",
                "## 报告元信息",
                f"- 来源: {detail['source_name']}",
                f"- 分类: {detail.get('source_category') or '未分类'}",
                f"- 发布时间: {detail.get('published_at') or '未知'}",
                f"- 链接: {detail['url']}",
            ]
            if detail.get("full_translation_text"):
                lines.extend(["", "## 全文翻译", str(detail["full_translation_text"]).strip()])
            return "\n".join(lines).strip()
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
            lines.extend(["", "## 原文正文", str(body_text)])
        if detail.get("full_translation_text"):
            lines.extend(["", "## 全文翻译", str(detail["full_translation_text"])])
        return "\n".join(lines).strip()

    def _append_overview_analysis(self, content: dict[str, Any], analysis_results: list[dict[str, Any]]) -> None:
        report_id = f"report:{content['dedupe_fingerprint']}"
        interpretation = self.agent.interpret_report(
            title=str(content.get("title") or ""),
            source_name=str(content.get("source_key") or ""),
            url=str(content.get("url") or ""),
            summary_text=content.get("summary_text"),
            body_text=content.get("body_text"),
        )
        analysis_results.append(
            {
                "analysis_kind": AnalysisKind.REPORT_INTERPRETATION.value,
                "source_ref": report_id,
                "title": content.get("title"),
                "factual_summary": interpretation.factual_summary,
                "interpreted_summary": interpretation.interpreted_summary,
                "evidence_json": interpretation.evidence,
                "is_partial": interpretation.is_partial,
            }
        )

    def _record_report_skip(
        self,
        *,
        source: str,
        reason: str,
        title: str | None = None,
        url: str | None = None,
    ) -> None:
        report_skips = self.storage.load_collection("report_skips")
        report_skips.append({"source": source, "title": title, "url": url, "reason": reason})
        self.storage.save_collection("report_skips", report_skips)

    def _delete_related_analysis(self, collection_name: str, report_id: str) -> None:
        rows = [item for item in self.storage.load_collection(collection_name) if item.get("source_ref") != report_id]
        self.storage.save_collection(collection_name, rows)

    def _should_refresh_existing_content(self, content: dict[str, Any]) -> bool:
        body_text = str(content.get("body_text") or "")
        if not body_text.strip():
            return True
        if bool(content.get("partial")):
            return True
        if self._looks_like_legacy_truncated_body(body_text):
            return True
        return ReportSourceCollector.looks_like_low_quality_body(body_text)

    @staticmethod
    def _looks_like_legacy_truncated_body(body_text: str) -> bool:
        trimmed = body_text.strip()
        if len(trimmed) in {4000, 12000}:
            tail = trimmed[-80:]
            if not any(tail.endswith(symbol) for symbol in ("。", "！", "？", ".", "!", "?", "\"", "'", "”")):
                return True
        return False

    def _find_content_by_normalized_url(
        self,
        normalized_url: str,
        *,
        content_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        rows = content_items if content_items is not None else self.storage.load_collection("content_items")
        return next(
            (
                item
                for item in rows
                if item.get("source_kind") == SourceKind.AI_REPORT.value
                and self._resolve_normalized_url(item) == normalized_url
            ),
            None,
        )

    @staticmethod
    def _resolve_normalized_url(content: dict[str, Any]) -> str:
        stored = content.get("normalized_url")
        if stored:
            return str(stored)
        metadata = content.get("metadata_json") or {}
        if metadata.get("normalized_url"):
            return str(metadata["normalized_url"])
        return ReportSourceCollector.normalize_article_url(str(content.get("url") or ""))

    @staticmethod
    def _build_export_slug(detail: dict[str, str | bool | None]) -> str:
        title = str(detail.get("title") or "report")
        normalized = "".join(char.lower() if char.isalnum() else "-" for char in title)
        normalized = "-".join(part for part in normalized.split("-") if part)
        return f"report-{normalized}"

    @staticmethod
    def _build_summary_title(source_name: str | None, source_category: str | None) -> str:
        if source_name:
            return f"{source_name} 报告速览"
        if source_category:
            return f"{source_category} 报告速览"
        return "全部来源 报告速览"

    @staticmethod
    def _render_report_summary_markdown(
        title: str,
        reports: list[dict[str, str | bool | None]],
    ) -> str:
        lines = [f"# {title}", ""]
        if not reports:
            lines.append("当前没有可导出的报告概览。")
            return "\n".join(lines)
        for index, report in enumerate(reports, start=1):
            lines.extend(
                [
                    f"## {index}. {report['title']}",
                    f"- 来源: {report['source_name']}",
                    f"- 分类: {report.get('source_category') or '未分类'}",
                    f"- 发布时间: {report.get('published_at') or '未知'}",
                    f"- 快速概览: {report.get('overview_summary') or report.get('summary') or '暂无'}",
                    f"- 已生成详细解读: {'是' if report.get('deep_reading_ready') else '否'}",
                    f"- 链接: {report.get('url') or '无'}",
                    "",
                ]
            )
        return "\n".join(lines).strip()
