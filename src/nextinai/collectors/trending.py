"""GitHub trending-style repository collector."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re
from typing import Any

import httpx


@dataclass(slots=True)
class TrendingQueryPlan:
    requested_window: str
    resolved_window: str | None
    source_mode: str
    source_label: str
    is_official: bool
    unsupported_reason: str | None = None


@dataclass(slots=True)
class TrendingQueryResult:
    plan: TrendingQueryPlan
    repositories: list["TrendingRepository"]


@dataclass(slots=True)
class TrendingRepository:
    full_name: str
    html_url: str
    description: str | None
    stars: int
    forks: int
    language: str | None
    topics: list[str]
    pushed_at: str | None
    created_at: str | None
    readme_excerpt: str | None
    partial: bool = False
    stars_in_period: str | None = None


class GitHubTrendingCollector:
    """Collect trending repositories from the official GitHub Trending page."""

    def __init__(self, token: str | None = None, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        headers = {
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "nextinai/0.2.0",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.Client(
            base_url="https://github.com",
            headers=headers,
            timeout=20.0,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def collect(self, window: str, limit: int) -> list[TrendingRepository]:
        return self.collect_with_metadata(window, limit).repositories

    def collect_with_metadata(self, window: str, limit: int) -> TrendingQueryResult:
        plan = self.build_query_plan(window)
        if plan.resolved_window is None:
            return TrendingQueryResult(plan=plan, repositories=[])
        since = plan.resolved_window
        response = self.client.get("/trending", params={"since": since})
        response.raise_for_status()
        repositories = self._parse_trending_page(response.text)[:limit]
        return TrendingQueryResult(plan=plan, repositories=repositories)

    def _fetch_readme_excerpt(self, full_name: str) -> str | None:
        response = self.client.get(f"/{full_name}/raw/HEAD/README.md")
        if response.status_code >= 400:
            return None
        text = response.text.strip()
        if not text:
            return None
        for line in text.splitlines():
            cleaned = line.strip().lstrip("#").strip()
            if cleaned:
                return cleaned[:240]
        return None

    @staticmethod
    @staticmethod
    def build_query_plan(window: str) -> TrendingQueryPlan:
        normalized = window.strip().lower()
        if normalized in {"daily", "1d", "today"}:
            return TrendingQueryPlan(
                requested_window=window,
                resolved_window="daily",
                source_mode="official_trending_page",
                source_label="GitHub 官方 Trending 页面（日榜）",
                is_official=True,
            )
        if normalized in {"weekly", "7d"}:
            return TrendingQueryPlan(
                requested_window=window,
                resolved_window="weekly",
                source_mode="official_trending_page",
                source_label="GitHub 官方 Trending 页面（周榜）",
                is_official=True,
            )
        if normalized in {"monthly", "30d"}:
            return TrendingQueryPlan(
                requested_window=window,
                resolved_window="monthly",
                source_mode="official_trending_page",
                source_label="GitHub 官方 Trending 页面（月榜）",
                is_official=True,
            )
        if re.fullmatch(r"\d+d", normalized):
            return TrendingQueryPlan(
                requested_window=window,
                resolved_window=None,
                source_mode="unsupported",
                source_label="当前未提供替代口径",
                is_official=False,
                unsupported_reason=(
                    "GitHub 官方 Trending 页面当前只稳定提供 daily、weekly、monthly 三种时间窗口，"
                    f"不直接支持 {window} 这样的自定义天数查询。"
                ),
            )
        raise ValueError(
            "热门榜时间窗口仅支持 daily、1d、7d、30d、weekly 或 monthly；"
            "如果要更细粒度窗口，需要明确采用非官方替代口径。"
        )

    def _parse_trending_page(self, html_text: str) -> list[TrendingRepository]:
        articles = re.findall(r"<article[^>]*class=\"Box-row\"[^>]*>(.*?)</article>", html_text, re.S)
        repositories: list[TrendingRepository] = []
        for article in articles:
            repository = self._parse_trending_article(article)
            if repository is not None:
                repositories.append(repository)
        return repositories

    def _parse_trending_article(self, article_html: str) -> TrendingRepository | None:
        repo_match = re.search(
            r"<h2[^>]*>.*?href=\"/([^\"/]+/[^\"/]+)\"",
            article_html,
            re.S,
        )
        if repo_match is None:
            return None
        full_name = html.unescape(repo_match.group(1))
        plain_text = self._clean_html_text(article_html) or ""
        description = self._extract_first(article_html, r"<p[^>]*>(.*?)</p>")
        description = self._clean_html_text(description)
        language = self._clean_html_text(
            self._extract_first(article_html, r'itemprop=\"programmingLanguage\">(.*?)</span>')
        )
        star_match = re.search(r'href=\"/[^\"]+/stargazers\"[^>]*>\s*([\d,]+)\s*</a>', article_html)
        fork_match = re.search(r'href=\"/[^\"]+/forks\"[^>]*>\s*([\d,]+)\s*</a>', article_html)
        stars_in_period_match = re.search(r'([\d,]+)\s+stars?\s+(today|this week|this month)', article_html, re.I)
        total_stars = star_match.group(1) if star_match else None
        total_forks = fork_match.group(1) if fork_match else None
        if total_stars is None or total_forks is None:
            counts_match = re.search(r"\b([\d,]+)\s+([\d,]+)\s+Built by\b", plain_text)
            if counts_match is not None:
                total_stars = total_stars or counts_match.group(1)
                total_forks = total_forks or counts_match.group(2)
        readme_excerpt = self._fetch_readme_excerpt(full_name)
        partial = not bool(description or readme_excerpt)
        return TrendingRepository(
            full_name=full_name,
            html_url=f"https://github.com/{full_name}",
            description=description,
            stars=self._parse_count(total_stars),
            forks=self._parse_count(total_forks),
            language=language,
            topics=[],
            pushed_at=None,
            created_at=None,
            readme_excerpt=readme_excerpt,
            partial=partial,
            stars_in_period=stars_in_period_match.group(1) if stars_in_period_match else None,
        )

    @staticmethod
    def _extract_first(text: str, pattern: str) -> str | None:
        match = re.search(pattern, text, re.S)
        if match is None:
            return None
        return match.group(1)

    @staticmethod
    def _clean_html_text(value: str | None) -> str | None:
        if not value:
            return None
        cleaned = re.sub(r"<[^>]+>", " ", value)
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or None

    @staticmethod
    def _parse_count(value: str | None) -> int:
        if not value:
            return 0
        return int(value.replace(",", ""))
