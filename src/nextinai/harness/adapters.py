"""Adapters that lift existing collectors and services into event-layer objects."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from nextinai.agents.intelligence import IntelligenceAgent, OpenAIIntelligenceAgent, RuleBasedIntelligenceAgent
from nextinai.collectors.trending import GitHubTrendingCollector, TrendingRepository
from nextinai.core.config import get_settings
from nextinai.core.datetime_utils import parse_datetime
from nextinai.domain.enums import AnalysisKind, SourceKind
from nextinai.harness.models import Briefing, DeliveryTask, IntelligenceEvent, SourceItem, SourceReference
from nextinai.services.github_subscriptions import validate_repository
from nextinai.storage.files import FileStorage, ensure_workspace


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


class IntelligenceEventAdapter:
    """Build structured events from existing module outputs."""

    def __init__(
        self,
        *,
        storage: FileStorage | None = None,
        collector: GitHubTrendingCollector | None = None,
        agent: IntelligenceAgent | None = None,
    ) -> None:
        settings = get_settings()
        self.storage = storage or _build_storage()
        self.collector = collector or GitHubTrendingCollector(token=settings.github_token)
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

    def get_repo_update_events(self, repository: str, hours: int = 24) -> list[IntelligenceEvent]:
        normalized = validate_repository(repository)
        window_start = datetime.now(timezone.utc) - timedelta(hours=hours)
        rows = [
            row
            for row in self.storage.load_collection("content_items")
            if row.get("source_kind") == SourceKind.GITHUB_REPOSITORY.value
            and row.get("source_key") == normalized
            and self._is_in_window(row.get("published_at"), window_start)
        ]
        grouped = self._group_repository_rows(rows)
        events = [self._build_repo_event(normalized, group_rows) for group_rows in grouped.values()]
        return sorted(events, key=lambda item: item.importance_score, reverse=True)

    def get_report_events(self, *, source_name: str | None = None, limit: int = 10) -> list[IntelligenceEvent]:
        content_rows = [
            row
            for row in self.storage.load_collection("content_items")
            if row.get("source_kind") == SourceKind.AI_REPORT.value
            and (source_name is None or row.get("source_key") == source_name)
        ]
        analysis_rows = {
            row.get("source_ref"): row
            for row in self.storage.load_collection("analysis_results")
            if row.get("analysis_kind") == AnalysisKind.REPORT_INTERPRETATION.value
        }
        events: list[IntelligenceEvent] = []
        for row in content_rows:
            source_ref = f"report:{row.get('dedupe_fingerprint')}"
            analysis = analysis_rows.get(source_ref)
            events.append(self._build_report_event(row, analysis))
        events.sort(key=lambda item: (item.importance_score, item.happened_at or ""), reverse=True)
        return events[:limit]

    def get_trending_events(self, window: str, limit: int = 10) -> list[IntelligenceEvent]:
        repositories = self.collector.collect(window, limit)
        return [self._build_trending_event(window, repo) for repo in repositories]

    def persist_events(self, events: list[IntelligenceEvent]) -> int:
        existing = self.storage.load_collection("events")
        index = {row.get("event_id"): row for row in existing}
        created = 0
        for event in events:
            payload = event.to_dict()
            if event.event_id not in index:
                existing.append(payload)
                index[event.event_id] = payload
                created += 1
            else:
                index[event.event_id].update(payload)
        self.storage.save_collection("events", existing)
        return created

    @staticmethod
    def _is_in_window(value: str | None, window_start: datetime) -> bool:
        if not value:
            return False
        return parse_datetime(value) >= window_start

    @staticmethod
    def _normalize_repository_key(title: str) -> str:
        normalized = title.strip().lower()
        normalized = re.sub(r"\s*\(#\d+\)", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _group_repository_rows(self, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = self._normalize_repository_key(str(row.get("title", "")))
            grouped.setdefault(key, []).append(row)
        return grouped

    def _build_repo_event(self, repository: str, rows: list[dict[str, Any]]) -> IntelligenceEvent:
        rows.sort(key=lambda item: item.get("published_at") or "", reverse=True)
        latest = rows[0]
        tags = [repository, latest.get("signal_type", "unknown")]
        summary = self._describe_repository_change(latest, len(rows))
        rationale = self._build_repo_rationale(latest)
        novelty_score = 0.82
        relevance_score = 0.88
        impact_score = 0.74 if latest.get("signal_type") == "release" else 0.66
        heat_score = min(0.95, 0.55 + 0.08 * len(rows))
        confidence_score = 0.86
        return IntelligenceEvent(
            event_id=self._build_event_id("repo", repository, self._normalize_repository_key(latest["title"])),
            event_type="change_event",
            subject=repository,
            title=latest["title"],
            summary=summary,
            rationale=rationale,
            source_refs=[
                SourceReference(
                    source_kind=str(row["source_kind"]),
                    source_key=str(row["source_key"]),
                    content_ref=row.get("dedupe_fingerprint"),
                    url=row.get("url"),
                )
                for row in rows
            ],
            tags=[tag for tag in tags if tag],
            novelty_score=novelty_score,
            relevance_score=relevance_score,
            impact_score=impact_score,
            heat_score=heat_score,
            confidence_score=confidence_score,
            importance_score=self._combine_score(
                novelty=novelty_score,
                relevance=relevance_score,
                impact=impact_score,
                heat=heat_score,
                confidence=confidence_score,
            ),
            happened_at=latest.get("published_at"),
            metadata={
                "source_item_count": len(rows),
                "source_item_ids": [row.get("dedupe_fingerprint") for row in rows],
                "merge_strategy": "same_subject_same_change_nearby_window",
            },
        )

    def _build_report_event(
        self, content_row: dict[str, Any], analysis_row: dict[str, Any] | None
    ) -> IntelligenceEvent:
        title = str(content_row.get("title") or "Untitled report")
        interpreted = (analysis_row or {}).get("interpreted_summary") or content_row.get("summary_text") or "暂无解读"
        factual = (analysis_row or {}).get("factual_summary") or content_row.get("summary_text") or "暂无事实摘要"
        confidence_score = 0.88 if analysis_row else 0.62
        novelty_score = 0.8
        relevance_score = 0.72
        impact_score = 0.7
        heat_score = 0.58
        return IntelligenceEvent(
            event_id=self._build_event_id("report", str(content_row.get("source_key")), title),
            event_type="insight_event",
            subject=str(content_row.get("source_key")),
            title=title,
            summary=interpreted,
            rationale=factual,
            source_refs=[
                SourceReference(
                    source_kind=str(content_row.get("source_kind")),
                    source_key=str(content_row.get("source_key")),
                    content_ref=content_row.get("dedupe_fingerprint"),
                    analysis_ref=(analysis_row or {}).get("source_ref"),
                    url=content_row.get("url"),
                )
            ],
            tags=[str(content_row.get("source_key"))],
            novelty_score=novelty_score,
            relevance_score=relevance_score,
            impact_score=impact_score,
            heat_score=heat_score,
            confidence_score=confidence_score,
            importance_score=self._combine_score(
                novelty=novelty_score,
                relevance=relevance_score,
                impact=impact_score,
                heat=heat_score,
                confidence=confidence_score,
            ),
            happened_at=content_row.get("published_at"),
            metadata={"partial": bool(content_row.get("partial")), "has_analysis": analysis_row is not None},
        )

    def _build_trending_event(self, window: str, repo: TrendingRepository) -> IntelligenceEvent:
        analysis = self.agent.analyze_trending_repository(repo)
        heat_value = self._parse_heat(repo.stars_in_period)
        confidence_score = 0.9 if not repo.partial else 0.68
        novelty_score = 0.72
        relevance_score = 0.68
        impact_score = 0.76
        heat_score = heat_value
        return IntelligenceEvent(
            event_id=self._build_event_id("trending", window, repo.full_name),
            event_type="trend_event",
            subject=repo.full_name,
            title=repo.full_name,
            summary=analysis.purpose,
            rationale=analysis.why_trending,
            source_refs=[
                SourceReference(
                    source_kind=SourceKind.GITHUB_TRENDING.value,
                    source_key=window,
                    url=repo.html_url,
                )
            ],
            tags=[repo.language or "unknown", window],
            novelty_score=novelty_score,
            relevance_score=relevance_score,
            impact_score=impact_score,
            heat_score=heat_score,
            confidence_score=confidence_score,
            importance_score=self._combine_score(
                novelty=novelty_score,
                relevance=relevance_score,
                impact=impact_score,
                heat=heat_score,
                confidence=confidence_score,
            ),
            happened_at=utc_now().isoformat(),
            metadata={
                "stars": repo.stars,
                "forks": repo.forks,
                "language": repo.language,
                "stars_in_period": repo.stars_in_period,
                "confidence_label": analysis.confidence,
            },
        )

    @staticmethod
    def _combine_score(
        *, novelty: float, relevance: float, impact: float, heat: float, confidence: float
    ) -> float:
        return round(
            novelty * 0.3 + relevance * 0.25 + impact * 0.2 + heat * 0.15 + confidence * 0.1,
            4,
        )

    @staticmethod
    def _build_event_id(prefix: str, subject: str, title: str) -> str:
        digest = hashlib.sha256(f"{prefix}|{subject}|{title}".encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}"

    @staticmethod
    def _describe_repository_change(row: dict[str, Any], source_count: int) -> str:
        title = str(row.get("title") or "Untitled change")
        signal = str(row.get("signal_type") or "change")
        if signal == "release":
            return f"{title} 已进入发布阶段，说明这一波改动已经具备可分发价值。"
        if signal == "pull_request":
            return f"{title} 是一条已合并改动信号，代表仓库在最近窗口内落地了新的实现。"
        if signal == "documentation":
            return f"{title} 主要是文档整理信号，本身优先级通常低于功能更新，但能反映方向变化。"
        if source_count > 1:
            return f"{title} 在同一时间窗内被多条来源共同指向，说明这不是单点噪音，而是一波连续变化。"
        return f"{title} 是最近窗口内值得关注的一条仓库更新。"

    @staticmethod
    def _build_repo_rationale(row: dict[str, Any]) -> str:
        summary_text = (row.get("summary_text") or "").strip()
        if summary_text:
            return summary_text[:300]
        return "当前缺少更长正文，只能基于标题和信号类型做事件化归纳。"

    @staticmethod
    def _parse_heat(value: str | None) -> float:
        if not value:
            return 0.55
        digits = re.sub(r"[^\d]", "", value)
        if not digits:
            return 0.55
        numeric = int(digits)
        if numeric >= 5000:
            return 0.95
        if numeric >= 1000:
            return 0.85
        if numeric >= 300:
            return 0.75
        return 0.65


class BriefingViewBuilder:
    """Render shared briefing views from event objects."""

    def build_briefing(self, *, scope: str, view: str, events: list[IntelligenceEvent]) -> Briefing:
        normalized = view.strip().lower()
        if normalized == "flash":
            return self.build_flash_briefing(scope=scope, events=events)
        if normalized == "deep":
            return self.build_deep_briefing(scope=scope, events=events)
        if normalized == "conversation":
            return self.build_conversation_briefing(scope=scope, events=events)
        raise ValueError("briefing view 仅支持 flash、deep 或 conversation。")

    def build_flash_briefing(self, *, scope: str, events: list[IntelligenceEvent]) -> Briefing:
        top_events = events[:5]
        title = f"NextInAI 快讯简报 ({scope})"
        summary = "；".join(event.title for event in top_events) if top_events else "当前没有可关注事件。"
        lines = [f"# {title}", "", summary, ""]
        for index, event in enumerate(top_events, start=1):
            lines.extend(
                [
                    f"## {index}. {event.title}",
                    f"- 事件类型: {event.event_type}",
                    f"- 为什么值得看: {event.summary}",
                    f"- 进一步判断: {event.rationale}",
                    f"- 关注度评分: {event.importance_score}",
                    "",
                ]
            )
        return Briefing(
            briefing_id=f"briefing_{hashlib.sha256(title.encode('utf-8')).hexdigest()[:16]}",
            scope=scope,
            view="flash",
            title=title,
            summary=summary,
            event_ids=[event.event_id for event in top_events],
            content_markdown="\n".join(lines).strip(),
            metadata={"suggested_actions": ["继续深读第 1 个", "生成完整简报", "创建定时推送任务"]},
        )

    def build_deep_briefing(self, *, scope: str, events: list[IntelligenceEvent]) -> Briefing:
        top_events = events[:8]
        title = f"NextInAI 深读简报 ({scope})"
        summary = (
            f"本次深读覆盖 {len(top_events)} 个重点事件，优先解释它们的上下文、判断边界和后续关注点。"
            if top_events
            else "当前没有可进入深读的事件。"
        )
        lines = [f"# {title}", "", summary, ""]
        for index, event in enumerate(top_events, start=1):
            lines.extend(
                [
                    f"## {index}. {event.title}",
                    f"- 事件类型: {event.event_type}",
                    f"- 主题对象: {event.subject}",
                    f"- 先讲结论: {event.summary}",
                    f"- 判断依据: {event.rationale}",
                    f"- 评分拆解: novelty={event.novelty_score}, relevance={event.relevance_score}, impact={event.impact_score}, heat={event.heat_score}, confidence={event.confidence_score}",
                    f"- 判断边界: {self._build_confidence_boundary(event)}",
                    f"- 建议继续关注: {self._build_next_watch(event)}",
                    f"- 来源线索:",
                ]
            )
            for ref in event.source_refs[:5]:
                lines.append(f"  - {ref.source_kind} / {ref.source_key} / {ref.url or '(无链接)'}")
            lines.append("")
        return Briefing(
            briefing_id=f"briefing_{hashlib.sha256(title.encode('utf-8')).hexdigest()[:16]}",
            scope=scope,
            view="deep",
            title=title,
            summary=summary,
            event_ids=[event.event_id for event in top_events],
            content_markdown="\n".join(lines).strip(),
            metadata={"suggested_actions": ["展开第 1 个来源", "生成快讯版", "创建定时深读推送"]},
        )

    def build_conversation_briefing(self, *, scope: str, events: list[IntelligenceEvent]) -> Briefing:
        top_events = events[:6]
        title = f"NextInAI 对话视图 ({scope})"
        summary = "这一视图强调后续追问和动作衔接。" if top_events else "当前没有可对话展开的事件。"
        lines = [f"# {title}", "", summary, "", "## 可直接继续说的话", ""]
        for index, event in enumerate(top_events, start=1):
            lines.extend(
                [
                    f"### 事件 {index}: {event.title}",
                    f"- 一句话概览: {event.summary}",
                    f"- 可追问: “第 {index} 个详细讲讲”",
                    f"- 可生成: “把第 {index} 个整理成简报”",
                    f"- 可动作: “把这份简报发到邮箱”",
                    "",
                ]
            )
        return Briefing(
            briefing_id=f"briefing_{hashlib.sha256(title.encode('utf-8')).hexdigest()[:16]}",
            scope=scope,
            view="conversation",
            title=title,
            summary=summary,
            event_ids=[event.event_id for event in top_events],
            content_markdown="\n".join(lines).strip(),
            metadata={"suggested_actions": ["第 1 个详细讲讲", "生成深读简报", "发到邮箱"]},
        )

    @staticmethod
    def _build_confidence_boundary(event: IntelligenceEvent) -> str:
        if event.confidence_score >= 0.85:
            return "当前判断置信度较高，主要风险不是方向错，而是细节仍可能补充。"
        if event.confidence_score >= 0.7:
            return "当前判断大体可信，但仍有部分推断成分，适合继续看原始来源确认。"
        return "当前判断推断成分较多，建议只把它当作候选信号，而不是定论。"

    @staticmethod
    def _build_next_watch(event: IntelligenceEvent) -> str:
        if event.event_type == "change_event":
            return "继续看后续 release、PR 合并和文档补齐，确认这是不是一次持续演进。"
        if event.event_type == "trend_event":
            return "继续看热度能否延续，以及项目是否很快出现更明确的用例、演示或生态响应。"
        return "继续看是否出现二次传播、官方后续说明或落地案例，确认洞察是否会转成更大信号。"


class MigrationGuide:
    """Describe how current modules map into the harness event pipeline."""

    @staticmethod
    def direct_reuse_items() -> list[dict[str, str]]:
        return [
            {
                "capability": "add_subscription",
                "current_entry": "GitHubSubscriptionService.add_subscription",
                "reuse_level": "direct",
                "note": "已直接暴露为 action tool。",
            },
            {
                "capability": "deliver_briefing",
                "current_entry": "AgenticNotificationService.send",
                "reuse_level": "direct",
                "note": "当前通过 action tool 调用，后续只需增强 briefing 引用语义。",
            },
            {
                "capability": "report_fetch",
                "current_entry": "AgenticReportService.fetch_reports",
                "reuse_level": "collector_reuse",
                "note": "抓取和落盘继续保留，查询由 event adapter 读取结构化结果。",
            },
            {
                "capability": "trending_query",
                "current_entry": "GitHubTrendingCollector.collect",
                "reuse_level": "adapter_required",
                "note": "原 CLI 文本输出已降级，主路径改为 event adapter -> tool。",
            },
            {
                "capability": "repo_update_query",
                "current_entry": "GitHubSubscriptionService.summarize_repository",
                "reuse_level": "adapter_required",
                "note": "保留给 CLI 验收，agent 主路径改为 content_items -> event merge -> tool。",
            },
        ]

    @staticmethod
    def event_pipeline_steps() -> list[str]:
        return [
            "collector/service 采集或更新原始内容",
            "content_items / analysis_results 落盘",
            "IntelligenceEventAdapter 将模块输出提升为事件级对象",
            "ToolRegistry 暴露查询、生成、动作 tool",
            "AssistantAgent / chat shell / future web 复用统一 runtime",
        ]


def utc_now() -> datetime:
    """Return the current UTC datetime."""

    return datetime.now(timezone.utc)
