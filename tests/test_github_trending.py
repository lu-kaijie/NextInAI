from datetime import datetime, timedelta, timezone

from nextinai.agents import ReportInterpretation, TrendingProjectAnalysis
from nextinai.collectors.trending import GitHubTrendingCollector, TrendingRepository
from nextinai.services.github_trending import GitHubTrendingService


class FakeTrendingCollector:
    def __init__(self, repositories):
        self.repositories = repositories
        self.calls = []

    def collect(self, window: str, limit: int):
        self.calls.append((window, limit))
        return self.repositories[:limit]


class FakeIntelligenceAgent:
    def summarize_repository_updates(self, *, repository, hours, items):
        raise AssertionError("not used")

    def analyze_trending_repository(self, repo):
        return TrendingProjectAnalysis(
            purpose=f"purpose:{repo.full_name}",
            why_trending="why:because",
            confidence="高" if not repo.partial else "中",
        )

    def interpret_report(self, **kwargs):
        return ReportInterpretation("fact", "interp", [], False)


def test_trending_service_formats_ranked_report() -> None:
    now = datetime.now(timezone.utc)
    collector = FakeTrendingCollector(
        [
            TrendingRepository(
                full_name="openai/gpt-oss",
                html_url="https://github.com/openai/gpt-oss",
                description="Open-source GPT models for real-world apps.",
                stars=12345,
                forks=900,
                language="Python",
                topics=["ai", "llm", "agents"],
                pushed_at=now.isoformat(),
                created_at=(now - timedelta(days=5)).isoformat(),
                readme_excerpt="README excerpt",
                partial=False,
            )
        ]
    )
    service = GitHubTrendingService(collector=collector, agent=FakeIntelligenceAgent())

    report = service.get_trending("daily", 10)

    assert "GitHub 热门项目榜" in report
    assert "openai/gpt-oss" in report
    assert "purpose:openai/gpt-oss" in report
    assert "why:because" in report
    assert "官方 Trending 页面" in report


def test_trending_service_marks_partial_results() -> None:
    now = datetime.now(timezone.utc)
    collector = FakeTrendingCollector(
        [
            TrendingRepository(
                full_name="someone/unknown-ai",
                html_url="https://github.com/someone/unknown-ai",
                description=None,
                stars=12,
                forks=1,
                language=None,
                topics=[],
                pushed_at=(now - timedelta(days=40)).isoformat(),
                created_at=(now - timedelta(days=90)).isoformat(),
                readme_excerpt=None,
                partial=True,
            )
        ]
    )
    service = GitHubTrendingService(collector=collector, agent=FakeIntelligenceAgent())

    report = service.get_trending("7d", 10)

    assert "可信度: 中" in report


def test_trending_service_shows_stars_in_period() -> None:
    now = datetime.now(timezone.utc)
    collector = FakeTrendingCollector(
        [
            TrendingRepository(
                full_name="someone/active-ai",
                html_url="https://github.com/someone/active-ai",
                description="Active AI project.",
                stars=88,
                forks=7,
                language="Python",
                topics=["ai"],
                pushed_at=now.isoformat(),
                created_at=(now - timedelta(days=180)).isoformat(),
                readme_excerpt="README excerpt",
                partial=False,
                stars_in_period="1,234 stars today",
            )
        ]
    )
    service = GitHubTrendingService(collector=collector, agent=FakeIntelligenceAgent())

    report = service.get_trending("daily", 10)

    assert "1,234 stars today" in report


def test_trending_collector_prefers_repo_link_over_sponsor_link_and_parses_counts() -> None:
    collector = GitHubTrendingCollector(
        client=type(
            "DummyClient",
            (),
            {"get": lambda self, path, **kwargs: type("Resp", (), {"status_code": 404, "text": "", "raise_for_status": lambda self: None})()},
        )()
    )
    article_html = """
    <article class="Box-row">
      <a href="/sponsors/mattpocock">Sponsor</a>
      <h2 class="h3 lh-condensed">
        <a href="/mattpocock/skills">mattpocock / skills</a>
      </h2>
      <p>Skills for Real Engineers. Straight from my .claude directory.</p>
      <span itemprop="programmingLanguage">Shell</span>
      <a href="/mattpocock/skills/stargazers">46,744</a>
      <a href="/mattpocock/skills/forks">3,799</a>
      Built by
      7,280 stars today
    </article>
    """

    repository = collector._parse_trending_article(article_html)

    assert repository is not None
    assert repository.full_name == "mattpocock/skills"
    assert repository.stars == 46744
    assert repository.forks == 3799
    assert repository.stars_in_period == "7,280"
