"""Unified intelligence agent for repository, trending, and report analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from openai import OpenAI

from nextinai.collectors.trending import TrendingRepository


@dataclass(slots=True)
class ReportInterpretation:
    factual_summary: str
    interpreted_summary: str
    evidence: list[str]
    is_partial: bool


@dataclass(slots=True)
class DeepReportReading:
    markdown_body: str
    summary: str
    evidence: list[str]
    is_partial: bool


@dataclass(slots=True)
class TrendingProjectAnalysis:
    purpose: str
    why_trending: str
    confidence: str


@dataclass(slots=True)
class DigestOverview:
    title: str
    summary: str
    highlights: list[str]


class IntelligenceAgent:
    """Unified agent interface for all core analysis paths."""

    def summarize_repository_updates(
        self, *, repository: str, hours: int, items: list[dict[str, Any]]
    ) -> str:
        raise NotImplementedError

    def analyze_trending_repository(self, repo: TrendingRepository) -> TrendingProjectAnalysis:
        raise NotImplementedError

    def interpret_report(
        self,
        *,
        title: str,
        source_name: str,
        url: str,
        summary_text: str | None,
        body_text: str | None,
    ) -> ReportInterpretation:
        raise NotImplementedError

    def deep_read_report(
        self,
        *,
        title: str,
        source_name: str,
        url: str,
        summary_text: str | None,
        body_text: str | None,
    ) -> DeepReportReading:
        raise NotImplementedError

    def translate_report_excerpt(self, *, title: str, source_name: str, excerpt_text: str) -> str:
        raise NotImplementedError

    def compose_digest_overview(
        self,
        *,
        scope: str,
        repo_summaries: list[str],
        trending_entries: list[str],
        report_entries: list[str],
        missing_sections: list[str],
    ) -> DigestOverview:
        raise NotImplementedError


class RuleBasedIntelligenceAgent(IntelligenceAgent):
    """Deterministic fallback agent for local-only operation."""

    def summarize_repository_updates(
        self, *, repository: str, hours: int, items: list[dict[str, Any]]
    ) -> str:
        if not items:
            return f"{repository} 在最近 {hours} 小时内没有新的仓库更新。"

        deduplicated = self._deduplicate_repository_items(items)
        grouped: dict[str, list[dict[str, Any]]] = {
            "新增功能": [],
            "主要改进": [],
            "问题修复": [],
        }
        for item in deduplicated:
            grouped[self._classify_repository_item(item)].append(item)

        overview = self._build_repository_overview(repository, hours, grouped)
        lines = [f"# {repository} 最近 {hours} 小时更新摘要", "", overview, ""]
        for section, section_items in grouped.items():
            lines.append(f"## {section}")
            if not section_items:
                lines.append("- 无")
                lines.append("")
                continue
            for item in section_items[:5]:
                lines.append(self._format_repository_change_line(item, section))
            lines.append("")
        return "\n".join(lines).strip()

    def analyze_trending_repository(self, repo: TrendingRepository) -> TrendingProjectAnalysis:
        purpose = self._infer_project_purpose(repo)
        why_trending = self._infer_trending_reason(repo)
        confidence = self._infer_trending_confidence(repo)
        return TrendingProjectAnalysis(
            purpose=purpose,
            why_trending=why_trending,
            confidence=confidence,
        )

    def interpret_report(
        self,
        *,
        title: str,
        source_name: str,
        url: str,
        summary_text: str | None,
        body_text: str | None,
    ) -> ReportInterpretation:
        content = (body_text or summary_text or "").strip()
        partial = not bool(body_text and body_text.strip())
        facts = self._build_factual_summary(title, source_name, summary_text, content, partial)
        interpretation = self._build_report_interpretation(title, source_name, content, partial)
        evidence = [url]
        if summary_text:
            evidence.append(summary_text[:160])
        return ReportInterpretation(
            factual_summary=facts,
            interpreted_summary=interpretation,
            evidence=evidence,
            is_partial=partial,
        )

    def deep_read_report(
        self,
        *,
        title: str,
        source_name: str,
        url: str,
        summary_text: str | None,
        body_text: str | None,
    ) -> DeepReportReading:
        content = (body_text or summary_text or "").strip()
        partial = not bool(body_text and body_text.strip())
        sections = self._segment_report_content(content)[:3] or [summary_text or "当前可读正文非常有限。"]
        summary = self._build_deep_report_summary(title, source_name, content, partial)
        lines = [
            f"# {title} 深度带读",
            "",
            "## 先说结论",
            summary,
            "",
            "## 这篇内容想解决什么问题",
            f"{source_name} 这篇内容想让外部更快理解《{title}》背后的重点。"
            "对使用者来说，真正要抓的是它改变了什么边界、释放了什么信号、以及哪些地方还只是方向描述。",
            "",
            "## 核心观点拆解",
            self._build_reader_takeaways(title, content, partial),
            "",
            "## 逐段带读",
        ]
        for index, section in enumerate(sections, start=1):
            lines.extend(
                [
                    f"### 第 {index} 段",
                    f"原文要点：{section}",
                    f"带读说明：{self._build_section_commentary(title, section, index)}",
                    "",
                ]
            )
        lines.extend(
            [
                "## 值得关注的技术 / 产品 / 商业信号",
                self._build_signal_commentary(title, content, partial),
                "",
                "## 我会保留判断的地方",
                "如果正文抓取不完整，或者原文大量使用宣传式表达而缺少可验证细节，就不能把文中说法直接等同为能力已经成熟落地。"
                "更稳妥的做法，是把这篇内容当成一手线索，再去追 API、代码、价格、评测或用户反馈。",
                "",
                "## 对实际使用者的启发",
                self._build_reader_takeaways(title, content, partial),
            ]
        )
        return DeepReportReading(
            markdown_body="\n".join(lines).strip(),
            summary=summary,
            evidence=[url, title],
            is_partial=partial,
        )

    def translate_report_excerpt(self, *, title: str, source_name: str, excerpt_text: str) -> str:
        if self._looks_like_chinese(excerpt_text):
            return excerpt_text.strip()
        return (
            f"以下是《{title}》正文摘录的中文译文（规则降级版，建议在已配置模型时查看更自然的译文）：\n\n"
            f"{excerpt_text.strip()}"
        )

    def compose_digest_overview(
        self,
        *,
        scope: str,
        repo_summaries: list[str],
        trending_entries: list[str],
        report_entries: list[str],
        missing_sections: list[str],
    ) -> DigestOverview:
        highlights: list[str] = []
        if repo_summaries:
            highlights.append(f"仓库更新 {len(repo_summaries)} 组")
        if trending_entries:
            highlights.append(f"热门项目 {len(trending_entries)} 条")
        if report_entries:
            highlights.append(f"报告解读 {len(report_entries)} 条")
        if missing_sections:
            highlights.append(f"缺失模块：{', '.join(missing_sections)}")
        summary = "；".join(highlights) if highlights else "当前窗口内暂无可生成简报的情报内容。"
        return DigestOverview(
            title=f"NextInAI 情报简报 ({scope})",
            summary=summary,
            highlights=highlights,
        )

    @staticmethod
    def _classify_repository_item(item: dict[str, Any]) -> str:
        text = f"{item.get('title', '')}\n{item.get('summary_text', '')}".lower()
        if any(keyword in text for keyword in ["fix", "bug", "hotfix", "error", "repair"]):
            return "问题修复"
        if any(keyword in text for keyword in ["docs", "doc", "readme", "documentation", "chore"]):
            return "主要改进"
        if item.get("signal_type") == "release" or any(
            keyword in text for keyword in ["feat", "feature", "new", "add", "introduce", "launch"]
        ):
            return "新增功能"
        return "主要改进"

    def _deduplicate_repository_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priorities = {"pull_request": 4, "release": 3, "documentation": 2, "commit": 1}
        deduplicated: dict[str, dict[str, Any]] = {}
        for item in sorted(items, key=lambda row: row.get("published_at") or "", reverse=True):
            key = self._normalize_repository_change_key(item.get("title", ""))
            existing = deduplicated.get(key)
            if existing is None:
                deduplicated[key] = item
                continue
            current_priority = priorities.get(item.get("signal_type", ""), 0)
            existing_priority = priorities.get(existing.get("signal_type", ""), 0)
            if current_priority > existing_priority:
                deduplicated[key] = item
        return list(deduplicated.values())

    @staticmethod
    def _normalize_repository_change_key(title: str) -> str:
        normalized = title.strip().lower()
        normalized = re.sub(r"\s*\(#\d+\)", "", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _build_repository_overview(self, repository: str, hours: int, grouped: dict[str, list[dict[str, Any]]]) -> str:
        highlights: list[str] = []
        if grouped["新增功能"]:
            highlights.append(f"新增功能 {len(grouped['新增功能'])} 项")
        if grouped["主要改进"]:
            highlights.append(f"主要改进 {len(grouped['主要改进'])} 项")
        if grouped["问题修复"]:
            highlights.append(f"问题修复 {len(grouped['问题修复'])} 项")
        summary = "；".join(highlights) if highlights else "没有可解读的有效更新。"
        notable = self._infer_repository_notable_takeaway(grouped)
        return f"这 {hours} 小时里，{repository} 主要有这些变化：{summary}。{notable}"

    def _infer_repository_notable_takeaway(self, grouped: dict[str, list[dict[str, Any]]]) -> str:
        titles = " ".join(item.get("title", "") for section in grouped.values() for item in section).lower()
        if "embedding" in titles:
            return "最值得注意的是能力边界在扩展，已经出现新的 Embeddings 接入。"
        if "release" in titles:
            return "这轮还有版本发布动作，说明部分改动已经进入可分发阶段。"
        if any(keyword in titles for keyword in ["docs", "readme", "documentation"]):
            return "其中一部分是文档和资料整理，信息价值低于真正的功能迭代。"
        return "整体看更像常规迭代，而不是方向性大改。"

    def _format_repository_change_line(self, item: dict[str, Any], section: str) -> str:
        normalized_title = self._humanize_repository_title(item)
        explanation = self._explain_repository_change(item, section)
        return f"- {normalized_title}。{explanation} 链接: {item['url']}"

    @staticmethod
    def _humanize_repository_title(item: dict[str, Any]) -> str:
        title = item.get("title", "").strip()
        title = re.sub(r"\s*\(#\d+\)", "", title)
        title = title.replace("feat(", "功能 ").replace("fix(", "修复 ").replace("chore(", "维护 ")
        title = title.replace("):", "：").replace(")", "")
        if title.startswith("release("):
            package_name = title[len("release("):].split(")", maxsplit=1)[0]
            version = title.split(":", maxsplit=1)[-1].strip()
            return f"{package_name} 发布 {version}"
        return title

    def _explain_repository_change(self, item: dict[str, Any], section: str) -> str:
        title = item.get("title", "").lower()
        summary_text = (item.get("summary_text") or "").lower()
        combined = f"{title}\n{summary_text}"
        if "perplexityembeddings" in combined or "embedding" in combined:
            return "这说明仓库在补充向量化或检索相关能力，不只是聊天调用封装。"
        if any(keyword in combined for keyword in ["docs", "readme", "x handle", "documentation"]):
            return "这更偏文档或对外信息整理，对核心能力影响较小。"
        if item.get("signal_type") == "release":
            return "这是版本发布信号，通常意味着相关改动已经收敛并可直接被下游使用。"
        if section == "问题修复":
            return "这属于稳定性修补，优先级通常高于普通维护项。"
        if section == "新增功能":
            return "这属于直接可感知的新能力扩展。"
        return "这更像对现有能力的维护或迭代优化。"

    @staticmethod
    def _infer_project_purpose(repo: TrendingRepository) -> str:
        if repo.description:
            if repo.partial:
                return f"从仓库描述看，主要是：{repo.description.strip()}"
            return repo.description.strip()
        if repo.readme_excerpt:
            if repo.partial:
                return f"从 README 摘要看，主要是：{repo.readme_excerpt.strip()}"
            return repo.readme_excerpt.strip()
        if repo.topics:
            return f"从 topic 看，主要与 {', '.join(repo.topics[:4])} 相关。"
        return "仓库描述信息不足，暂时无法准确判断其核心用途。"

    @staticmethod
    def _infer_trending_reason(repo: TrendingRepository) -> str:
        reasons: list[str] = []
        if repo.stars >= 5000:
            reasons.append("star 总量高")
        elif repo.stars >= 1000:
            reasons.append("star 表现较强")
        if repo.forks >= 500:
            reasons.append("fork 数较高")
        if repo.pushed_at and RuleBasedIntelligenceAgent._was_recently_pushed(repo.pushed_at):
            reasons.append("近期活跃更新")
        if repo.created_at and RuleBasedIntelligenceAgent._is_recent_project(repo.created_at):
            reasons.append("项目较新，容易获得集中关注")
        if repo.topics:
            reasons.append(f"topic 较明确：{', '.join(repo.topics[:3])}")
        if not reasons:
            return "能确认它进入了官方 Trending，但缺少更多稳定信号解释热度来源。"
        prefix = "综合可见信号看，" if not repo.partial else "结合当前可见的有限信号看，"
        return prefix + "；".join(reasons)

    @staticmethod
    def _infer_trending_confidence(repo: TrendingRepository) -> str:
        if repo.partial:
            if repo.description or repo.readme_excerpt:
                return "中"
            return "低"
        return "高"

    @staticmethod
    def _was_recently_pushed(pushed_at: str) -> bool:
        pushed_time = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        return pushed_time >= datetime.now(timezone.utc) - timedelta(days=7)

    @staticmethod
    def _is_recent_project(created_at: str) -> bool:
        created_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return created_time >= datetime.now(timezone.utc) - timedelta(days=30)

    @staticmethod
    def _build_factual_summary(
        title: str, source_name: str, summary_text: str | None, content: str, partial: bool
    ) -> str:
        excerpt = (summary_text or content or "未能提取到足够正文").strip().replace("\n", " ")
        excerpt = excerpt[:240]
        suffix = "当前仅基于部分内容。" if partial else "当前基于已抓取正文。"
        return f"{source_name} 发布了《{title}》。已提取事实摘要：{excerpt}。{suffix}"

    @staticmethod
    def _build_report_interpretation(title: str, source_name: str, content: str, partial: bool) -> str:
        lowered = f"{title}\n{content}".lower()
        themes: list[str] = []
        if any(keyword in lowered for keyword in ["agent", "workflow", "automation", "tool"]):
            themes.append("更偏向 agent 能力或工作流自动化")
        if any(keyword in lowered for keyword in ["model", "gpt", "llm", "inference"]):
            themes.append("对模型能力或推理体验有直接影响")
        if any(keyword in lowered for keyword in ["safety", "policy", "security", "risk"]):
            themes.append("包含安全、治理或风险相关信号")
        if any(keyword in lowered for keyword in ["benchmark", "eval", "performance", "latency"]):
            themes.append("涉及性能、评测或实际可用性改进")
        if not themes:
            themes.append("更像一则需要持续跟踪的产品/研究动态")
        partial_suffix = "由于正文不完整，这部分判断需要后续复核。" if partial else ""
        return f"从 NextInAI agent 的角度看，这条更新 {source_name} { '；'.join(themes) }。{partial_suffix}".strip()

    @staticmethod
    def _segment_report_content(content: str) -> list[str]:
        if not content:
            return []
        parts = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s+", content) if part.strip()]
        compact: list[str] = []
        current = ""
        for part in parts:
            if len(current) + len(part) <= 180:
                current = f"{current} {part}".strip()
            else:
                if current:
                    compact.append(current)
                current = part
        if current:
            compact.append(current)
        return compact[:5]

    @staticmethod
    def _build_deep_report_summary(title: str, source_name: str, content: str, partial: bool) -> str:
        lowered = f"{title}\n{content}".lower()
        points: list[str] = [f"这篇《{title}》最值得看的，不是表面消息本身，而是 {source_name} 想把什么方向推到台前。"]
        if any(keyword in lowered for keyword in ["agent", "workflow", "automation", "tool"]):
            points.append("它释放的是 agent 或工作流能力继续成型的信号。")
        if any(keyword in lowered for keyword in ["model", "gpt", "llm", "inference"]):
            points.append("它也会影响你对模型能力和落地方式的判断。")
        if any(keyword in lowered for keyword in ["policy", "safety", "security", "risk"]):
            points.append("同时还带有安全或治理层面的背景。")
        if partial:
            points.append("但当前正文抓取不完整，所以部分判断只能先保守处理。")
        return "".join(points)

    @staticmethod
    def _build_section_commentary(title: str, section: str, index: int) -> str:
        lowered = f"{title}\n{section}".lower()
        if any(keyword in lowered for keyword in ["announce", "introduce", "launch", "release", "introducing"]):
            return "这一段通常在回答“他们这次到底推出了什么”，阅读时要把品牌表述和真正可用的交付边界分开。"
        if any(keyword in lowered for keyword in ["benchmark", "eval", "performance", "latency", "speed"]):
            return "这里更像是在证明效果，但要特别留意有没有只挑对自己有利的指标，以及是否缺少真实使用条件。"
        if any(keyword in lowered for keyword in ["policy", "safety", "security", "risk"]):
            return "这一段重点不只是表态，而是反映团队当前最在意的风险面在哪里。"
        return f"第 {index} 段更像是在为核心主张铺垫背景。读这一段的关键，是判断它在整篇叙事里承担什么作用，而不是只记住表面措辞。"

    @staticmethod
    def _build_signal_commentary(title: str, content: str, partial: bool) -> str:
        lowered = f"{title}\n{content}".lower()
        signals: list[str] = []
        if any(keyword in lowered for keyword in ["api", "sdk", "platform", "tool"]):
            signals.append("它可能意味着接入层或平台层在扩展，后续值得继续看 API、SDK 或控制台是否同步更新。")
        if any(keyword in lowered for keyword in ["enterprise", "business", "customer", "production"]):
            signals.append("它也可能在释放商业化或生产落地信号，不只是研究展示。")
        if any(keyword in lowered for keyword in ["benchmark", "eval", "latency", "performance"]):
            signals.append("如果文中重点强调评测或性能，这往往意味着团队正在争夺“真实可用性”而不是单纯模型叙事。")
        if not signals:
            signals.append("更稳妥的判断是：它提供了一条值得跟踪的一手线索，但是否重要还要看后续产品、代码或社区反馈能否跟上。")
        if partial:
            signals.append("由于正文不完整，这些信号强度只能先按中低置信度看待。")
        return " ".join(signals)

    @staticmethod
    def _build_reader_takeaways(title: str, content: str, partial: bool) -> str:
        lowered = f"{title}\n{content}".lower()
        takeaways: list[str] = []
        if any(keyword in lowered for keyword in ["agent", "workflow", "automation"]):
            takeaways.append("如果你在做 agent，重点要看它改变的是能力上限、工作流组织方式，还是单纯把旧能力包装得更易用。")
        if any(keyword in lowered for keyword in ["model", "llm", "inference", "benchmark"]):
            takeaways.append("如果你关心模型选型，这篇内容更适合和独立评测、社区试用结果一起交叉验证。")
        if any(keyword in lowered for keyword in ["api", "sdk", "platform", "tool"]):
            takeaways.append("如果你偏工程落地，先盯住有没有 API、SDK、文档或价格层面的对应动作。")
        if not takeaways:
            takeaways.append("对大多数使用者来说，更实际的做法是先把它当成方向信号，再决定要不要继续追代码、产品页或用户案例。")
        if partial:
            takeaways.append("由于当前正文抓取不完整，不建议仅凭这份带读直接做采购或架构决策。")
        return " ".join(takeaways)

    @staticmethod
    def _looks_like_chinese(text: str) -> bool:
        if not text:
            return False
        chinese_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
        letters = sum(1 for char in text if char.isalpha())
        return chinese_chars > 0 and chinese_chars >= max(letters // 3, 20)


class OpenAIIntelligenceAgent(IntelligenceAgent):
    """LLM-backed unified analysis agent."""

    def __init__(self, api_key: str, model: str | None, base_url: str | None = None) -> None:
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.fallback = RuleBasedIntelligenceAgent()

    def summarize_repository_updates(
        self, *, repository: str, hours: int, items: list[dict[str, Any]]
    ) -> str:
        if not self.model or not items:
            return self.fallback.summarize_repository_updates(repository=repository, hours=hours, items=items)
        prepared_items = self.fallback._deduplicate_repository_items(items)
        prompt = (
            "你是 NextInAI 的 GitHub 更新分析 agent。"
            "你的目标不是罗列 commit，而是帮助用户快速理解“这段时间到底更新了什么、是否值得关注”。"
            "请输出中文 Markdown，必须包含："
            "1. 一段 2-3 句的总体判断；"
            "2. 固定分成“新增功能 / 主要改进 / 问题修复”三段；"
            "3. 每条都要写清楚具体变更含义，少贴原始标题，多做解释；"
            "4. 对明显重复的 PR/commit/release 只保留一条代表性信息；"
            "5. 不要要求用户自己点链接看，不要只贴链接。"
            f"\n仓库：{repository}\n时间窗口：最近 {hours} 小时\n更新：{prepared_items[:16]}"
        )
        text = self._complete(prompt)
        return text or self.fallback.summarize_repository_updates(repository=repository, hours=hours, items=items)

    def analyze_trending_repository(self, repo: TrendingRepository) -> TrendingProjectAnalysis:
        if not self.model:
            return self.fallback.analyze_trending_repository(repo)
        prompt = (
            "你是 NextInAI 的热门项目分析 agent。"
            "基于给定仓库元数据，用中文输出三行："
            "purpose=... / why_trending=... / confidence=..."
            f"\n仓库数据：{repo}"
        )
        text = self._complete(prompt)
        if not text:
            return self.fallback.analyze_trending_repository(repo)
        parsed = self._parse_key_value_block(text)
        return TrendingProjectAnalysis(
            purpose=parsed.get("purpose") or self.fallback.analyze_trending_repository(repo).purpose,
            why_trending=parsed.get("why_trending") or self.fallback.analyze_trending_repository(repo).why_trending,
            confidence=self._normalize_confidence(
                parsed.get("confidence"),
                self.fallback.analyze_trending_repository(repo).confidence,
            ),
        )

    def interpret_report(
        self,
        *,
        title: str,
        source_name: str,
        url: str,
        summary_text: str | None,
        body_text: str | None,
    ) -> ReportInterpretation:
        content = (body_text or summary_text or "").strip()
        if not self.model or not content:
            return self.fallback.interpret_report(
                title=title,
                source_name=source_name,
                url=url,
                summary_text=summary_text,
                body_text=body_text,
            )
        prompt = (
            "你是 NextInAI 的报告解读 agent。"
            "请基于给定来源内容，输出三行："
            "factual_summary=... / interpreted_summary=... / is_partial=true|false。"
            "事实摘要只能写可从来源直接确认的内容；解读分析单独写这条内容为什么值得 AI/agent 用户关注。"
            f"\n来源：{source_name}\n标题：{title}\n链接：{url}\n内容：\n{content[:6000]}"
        )
        text = self._complete(prompt)
        if not text:
            return self.fallback.interpret_report(
                title=title,
                source_name=source_name,
                url=url,
                summary_text=summary_text,
                body_text=body_text,
            )
        parsed = self._parse_key_value_block(text)
        fallback = self.fallback.interpret_report(
            title=title,
            source_name=source_name,
            url=url,
            summary_text=summary_text,
            body_text=body_text,
        )
        return ReportInterpretation(
            factual_summary=parsed.get("factual_summary") or fallback.factual_summary,
            interpreted_summary=parsed.get("interpreted_summary") or fallback.interpreted_summary,
            evidence=[url, title],
            is_partial=(parsed.get("is_partial", "").lower() == "true") if parsed.get("is_partial") else fallback.is_partial,
        )

    def deep_read_report(
        self,
        *,
        title: str,
        source_name: str,
        url: str,
        summary_text: str | None,
        body_text: str | None,
    ) -> DeepReportReading:
        content = (body_text or summary_text or "").strip()
        if not self.model or not content:
            return self.fallback.deep_read_report(
                title=title,
                source_name=source_name,
                url=url,
                summary_text=summary_text,
                body_text=body_text,
            )
        prompt = (
            "你是 NextInAI 的 AI 报告深度带读 agent。"
            "请直接输出中文 Markdown，不要输出 JSON，不要写额外前言。"
            "你的角色像老师或专家带读，不是普通摘要器。"
            "必须包含："
            "先说结论；这篇内容想解决什么问题；核心观点拆解；逐段带读（至少 3 段，每段都含“原文要点”和“带读说明”）；"
            "值得关注的技术/产品/商业信号；我会保留判断的地方；对实际使用者的启发。"
            "要求："
            "必须有评论、解释、判断依据和保留意见；"
            "篇幅明显长于摘要；"
            "如果正文不完整，要明确说明限制。"
            f"\n来源：{source_name}\n标题：{title}\n链接：{url}\n内容：\n{content[:10000]}"
        )
        markdown = self._complete(prompt)
        if not markdown:
            return self.fallback.deep_read_report(
                title=title,
                source_name=source_name,
                url=url,
                summary_text=summary_text,
                body_text=body_text,
            )
        return DeepReportReading(
            markdown_body=markdown.strip(),
            summary=self._extract_deep_read_summary(markdown, title),
            evidence=[url, title],
            is_partial=not bool(body_text and body_text.strip()),
        )

    def translate_report_excerpt(self, *, title: str, source_name: str, excerpt_text: str) -> str:
        if self.fallback._looks_like_chinese(excerpt_text):
            return excerpt_text.strip()
        if not self.model or not excerpt_text.strip():
            return self.fallback.translate_report_excerpt(
                title=title,
                source_name=source_name,
                excerpt_text=excerpt_text,
            )
        translated_chunks: list[str] = []
        for index, chunk in enumerate(self._chunk_translation_text(excerpt_text), start=1):
            prompt = (
                "你是 NextInAI 的全文翻译 agent。"
                "请把下面这段文章正文翻译成自然、流畅、适合中文读者阅读的中文。"
                "要求："
                "1. 忠实原意，不增删核心信息；"
                "2. 语言自然，不要机械直译；"
                "3. 保留专有名词、产品名、模型名；"
                "4. 尽量保留原文段落结构；"
                "5. 直接输出译文，不要加说明、不要加括号注释。"
                f"\n来源：{source_name}\n标题：{title}\n这是第 {index} 段正文：\n{chunk}"
            )
            translated = self._complete(prompt)
            if not translated:
                translated_chunks = []
                break
            translated_chunks.append(translated.strip())
        if not translated_chunks:
            return self.fallback.translate_report_excerpt(
                title=title,
                source_name=source_name,
                excerpt_text=excerpt_text,
            )
        return "\n\n".join(chunk for chunk in translated_chunks if chunk).strip()

    def compose_digest_overview(
        self,
        *,
        scope: str,
        repo_summaries: list[str],
        trending_entries: list[str],
        report_entries: list[str],
        missing_sections: list[str],
    ) -> DigestOverview:
        if not self.model:
            return self.fallback.compose_digest_overview(
                scope=scope,
                repo_summaries=repo_summaries,
                trending_entries=trending_entries,
                report_entries=report_entries,
                missing_sections=missing_sections,
            )
        prompt = (
            "你是 NextInAI 的 digest 编排 agent。"
            "请根据输入内容输出三行：title=... / summary=... / highlights=条目1 | 条目2 | 条目3。"
            f"\nscope={scope}\nrepo_summaries={repo_summaries[:5]}\ntrending_entries={trending_entries[:5]}"
            f"\nreport_entries={report_entries[:5]}\nmissing_sections={missing_sections}"
        )
        text = self._complete(prompt)
        if not text:
            return self.fallback.compose_digest_overview(
                scope=scope,
                repo_summaries=repo_summaries,
                trending_entries=trending_entries,
                report_entries=report_entries,
                missing_sections=missing_sections,
            )
        parsed = self._parse_key_value_block(text)
        fallback = self.fallback.compose_digest_overview(
            scope=scope,
            repo_summaries=repo_summaries,
            trending_entries=trending_entries,
            report_entries=report_entries,
            missing_sections=missing_sections,
        )
        highlights = [item.strip() for item in (parsed.get("highlights") or "").split("|") if item.strip()]
        return DigestOverview(
            title=parsed.get("title") or fallback.title,
            summary=parsed.get("summary") or fallback.summary,
            highlights=highlights or fallback.highlights,
        )

    def _complete(self, prompt: str) -> str:
        try:
            response = self.client.responses.create(model=self.model, input=prompt)
            return (getattr(response, "output_text", "") or "").strip()
        except Exception:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = response.choices[0].message.content
                return (content or "").strip()
            except Exception:
                return ""

    @staticmethod
    def _normalize_confidence(value: str | None, fallback: str) -> str:
        if not value:
            return fallback
        normalized = value.strip().lower()
        if normalized in {"高", "high", "strong", "0.8", "0.9", "1", "1.0"}:
            return "高"
        if normalized in {"低", "low", "weak", "0.2", "0.3", "0.4"}:
            return "低"
        if normalized in {"中", "medium", "moderate", "0.5", "0.6", "0.7"}:
            return "中"
        if "高" in value:
            return "高"
        if "低" in value:
            return "低"
        if "中" in value:
            return "中"
        return fallback

    @staticmethod
    def _parse_key_value_block(text: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in text.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", maxsplit=1)
            result[key.strip()] = value.strip()
        return result

    @staticmethod
    def _chunk_translation_text(text: str, limit: int = 2800) -> list[str]:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs:
            return [text[:limit]]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= limit:
                current = candidate
                continue
            if current:
                chunks.append(current)
            if len(paragraph) <= limit:
                current = paragraph
                continue
            start = 0
            while start < len(paragraph):
                piece = paragraph[start : start + limit]
                chunks.append(piece.strip())
                start += limit
            current = ""
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _extract_deep_read_summary(markdown: str, title: str) -> str:
        for line in markdown.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped and stripped != title:
                return stripped[:120]
        return f"{title} 的深度带读已生成。"
