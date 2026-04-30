"""Agent-centric service for AI report collection and interpretation."""

from __future__ import annotations

import hashlib
from typing import Any

from nextinai.agents import IntelligenceAgent, OpenAIIntelligenceAgent, RuleBasedIntelligenceAgent
from nextinai.collectors.reports import DEFAULT_REPORT_SOURCES, CollectedReportItem, ReportSource, ReportSourceCollector
from nextinai.core.config import get_settings
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
        self.storage = storage or _build_storage()
        self.collector = collector or ReportSourceCollector()
        self.sources = sources or DEFAULT_REPORT_SOURCES
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
            if progress_callback is not None:
                progress_callback(f"开始抓取来源：{source.name}")
            try:
                items = self.collector.collect(source, progress_callback=progress_callback)
            except Exception as exc:
                report_skips.append({"source": source.name, "reason": str(exc)})
                skipped += 1
                if progress_callback is not None:
                    progress_callback(f"来源抓取失败：{source.name}，原因：{exc}")
                continue

            if progress_callback is not None:
                progress_callback(f"来源抓取完成：{source.name}，获得 {len(items)} 篇候选文章")
            for item in items:
                fingerprint = self._build_fingerprint(item)
                source_ref = f"report:{fingerprint}"
                is_duplicate_content = fingerprint in content_index
                if is_duplicate_content and source_ref in analysis_index:
                    report_skips.append({"source": source.name, "title": item.title, "reason": "duplicate"})
                    skipped += 1
                    if progress_callback is not None:
                        progress_callback(f"[{source.name}] 跳过重复文章：{item.title}")
                    continue
                if not item.summary_text and not item.body_text:
                    report_skips.append({"source": source.name, "title": item.title, "reason": "unreadable"})
                    skipped += 1
                    if progress_callback is not None:
                        progress_callback(f"[{source.name}] 跳过不可读文章：{item.title}")
                    continue

                if not is_duplicate_content:
                    content_items.append(self._build_content_record(item, fingerprint))
                    content_index.add(fingerprint)
                    created += 1
                    titles.append(item.title)

                if source_ref in analysis_index:
                    if progress_callback is not None:
                        progress_callback(f"[{source.name}] 已有解读，跳过：{item.title}")
                    continue
                if progress_callback is not None:
                    progress_callback(f"[{source.name}] 正在解读：{item.title}")
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
                if progress_callback is not None:
                    progress_callback(f"[{source.name}] 解读完成：{item.title}")

        self.storage.save_collection("content_items", content_items)
        self.storage.save_collection("analysis_results", analysis_results)
        self.storage.save_collection("report_skips", report_skips)

        titles_preview = "；".join(titles[:5]) if titles else "无新报告"
        return (
            f"报告采集完成：新增 {created} 条，解读 {interpreted} 条，跳过 {skipped} 条。"
            f"本轮重点：{titles_preview}"
        )

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
