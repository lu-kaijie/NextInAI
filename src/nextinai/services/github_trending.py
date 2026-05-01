"""Trending repository service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nextinai.agents import IntelligenceAgent, OpenAIIntelligenceAgent, RuleBasedIntelligenceAgent
from nextinai.collectors.trending import GitHubTrendingCollector, TrendingRepository
from nextinai.core.config import get_settings
from nextinai.core.logging import get_logger, log_event
from nextinai.services.contracts import TrendingService


class GitHubTrendingService(TrendingService):
    """Produce first-version trending repository reports."""

    def __init__(
        self,
        collector: GitHubTrendingCollector | None = None,
        agent: IntelligenceAgent | None = None,
    ) -> None:
        settings = get_settings()
        self.logger = get_logger("trending")
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

    def get_trending(self, window: str, limit: int) -> str:
        log_event(self.logger, "开始获取热门榜", window=window, limit=limit)
        repositories = self.collector.collect(window, limit)
        if not repositories:
            log_event(self.logger, "热门榜为空", window=window, limit=limit)
            return f"在时间窗口 {window} 内没有获取到可用的热门仓库结果。"

        lines = [
            f"# GitHub 热门项目榜 ({window})",
            "",
            "口径说明：结果直接对齐 GitHub 官方 Trending 页面。",
            "",
        ]
        for index, repo in enumerate(repositories, start=1):
            lines.extend(self._format_repository(index, repo))
        log_event(self.logger, "热门榜生成完成", window=window, count=len(repositories))
        return "\n".join(lines).strip()

    def _format_repository(self, index: int, repo: TrendingRepository) -> list[str]:
        analysis = self.agent.analyze_trending_repository(repo)
        return [
            f"## {index}. {repo.full_name}",
            f"- 链接: {repo.html_url}",
            f"- 这是做什么的: {analysis.purpose}",
            f"- 为什么上榜: {analysis.why_trending}",
            f"- 基础数据: stars={repo.stars}, forks={repo.forks}, language={repo.language or '未知'}",
            f"- 趋势热度: {repo.stars_in_period or '官方页面未展示'}",
            f"- 可信度: {analysis.confidence}",
            "",
        ]
