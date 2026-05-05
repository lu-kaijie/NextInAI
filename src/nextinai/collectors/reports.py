"""Collectors for AI report and announcement sources."""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html import unescape
import re
from typing import Any
from xml.etree import ElementTree

from urllib.parse import parse_qsl, urljoin, urlparse, urlunparse, urlencode

import httpx


BODY_TEXT_LIMIT = 50000
MIN_ARTICLE_TEXT_LENGTH = 120
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
}


@dataclass(slots=True)
class ReportSource:
    name: str
    group: str
    kind: str
    url: str
    source_role: str = "daily_news"
    trusted: bool = True
    category: str = "其他来源"
    default_enabled: bool = True
    description: str | None = None
    article_path_prefix: str | None = None
    exclude_path_prefixes: tuple[str, ...] = ()


@dataclass(slots=True)
class CollectedReportItem:
    source_name: str
    title: str
    url: str
    published_at: str | None
    summary_text: str | None
    body_text: str | None
    metadata_json: dict[str, Any]
    partial: bool
    fulltext_status: str = ""
    fulltext_reason: str | None = None


class ManualUrlImportError(ValueError):
    """Structured failure raised while importing a single article URL."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


DEFAULT_REPORT_SOURCES = [
    ReportSource(
        "OpenAI News",
        "company",
        "feed",
        "https://openai.com/news/rss.xml",
        source_role="daily_news",
        category="AI 公司",
        description="OpenAI 官方新闻、产品发布与研究更新。",
    ),
    ReportSource(
        "Anthropic News",
        "company",
        "webpage_index",
        "https://www.anthropic.com/news",
        source_role="daily_news",
        category="AI 公司",
        description="Anthropic 官方新闻与模型、政策动态。",
        article_path_prefix="/news/",
    ),
    ReportSource(
        "Anthropic Research",
        "company",
        "webpage_index",
        "https://www.anthropic.com/research",
        source_role="research_report",
        category="AI 公司",
        description="Anthropic 官方研究文章与评测、agent、安全研究内容。",
        article_path_prefix="/research/",
        exclude_path_prefixes=("/research/team/",),
    ),
    ReportSource(
        "Anthropic Economic Futures",
        "company",
        "webpage_index",
        "https://www.anthropic.com/economic-futures",
        source_role="research_report",
        category="AI 公司",
        description="Anthropic 经济未来栏目，关注 AI 对经济与工作的影响。",
        article_path_prefix="/economic-futures/",
    ),
    ReportSource(
        "Google DeepMind Blog",
        "company",
        "feed",
        "https://deepmind.google/blog/rss.xml",
        source_role="daily_news",
        category="AI 公司",
        description="Google DeepMind 官方研究与产品博客。",
    ),
    ReportSource(
        "Meta AI Blog",
        "company",
        "feed",
        "https://ai.meta.com/blog/rss/",
        source_role="daily_news",
        category="AI 公司",
        description="Meta AI 官方博客与研究动态。",
    ),
    ReportSource(
        "Meta AI Research",
        "company",
        "webpage_index",
        "https://ai.meta.com/research/",
        source_role="research_report",
        category="AI 公司",
        default_enabled=False,
        description="Meta AI 官方研究页面，覆盖模型、论文和研究项目。",
        article_path_prefix="/research/",
        exclude_path_prefixes=("/research/publications/", "/research/tools/", "/research/models-and-analyses/"),
    ),
    ReportSource(
        "Cohere Blog",
        "company",
        "feed",
        "https://cohere.com/blog/rss.xml",
        source_role="daily_news",
        category="AI 公司",
        description="Cohere 官方博客与企业 AI 更新。",
    ),
    ReportSource(
        "Cohere Research",
        "company",
        "webpage_index",
        "https://cohere.com/research",
        source_role="research_report",
        category="AI 公司",
        description="Cohere Research 论文、研究结果与实验性研究内容。",
        article_path_prefix="/research/papers/",
    ),
    ReportSource(
        "Hugging Face Blog",
        "open-source",
        "feed",
        "https://huggingface.co/blog/feed.xml",
        source_role="daily_news",
        category="开源与平台",
        description="Hugging Face 模型、工具链与社区博客。",
    ),
    ReportSource(
        "LangChain Blog",
        "open-source",
        "feed",
        "https://blog.langchain.dev/rss/",
        source_role="daily_news",
        category="开源与平台",
        description="LangChain 官方博客与 agent / framework 更新。",
    ),
    ReportSource(
        "Weights & Biases Reports",
        "open-source",
        "feed",
        "https://wandb.ai/site/rss.xml",
        source_role="daily_news",
        category="开源与平台",
        description="Weights & Biases 平台、实验管理与评测内容。",
    ),
    ReportSource(
        "Hacker News AI",
        "community",
        "feed",
        "https://hnrss.org/newest?q=AI",
        source_role="daily_news",
        category="社区与论坛",
        description="Hacker News 中标题包含 AI 的近期项目与讨论。",
    ),
    ReportSource(
        "Reddit Artificial",
        "community",
        "feed",
        "https://www.reddit.com/r/artificial/.rss",
        source_role="daily_news",
        category="社区与论坛",
        default_enabled=False,
        description="Reddit r/artificial 社区关于 AI 产品、模型和行业新闻的讨论流。",
    ),
    ReportSource(
        "Product Hunt",
        "community",
        "feed",
        "https://www.producthunt.com/feed",
        source_role="daily_news",
        category="社区与论坛",
        default_enabled=False,
        description="Product Hunt 新品发布流，可用于补充新工具和 AI 产品动态。",
    ),
    ReportSource(
        "LessWrong AI",
        "community",
        "feed",
        "https://www.lesswrong.com/feed.xml?view=curated-rss",
        source_role="daily_news",
        category="社区与论坛",
        description="LessWrong AI 相关精选文章与讨论。",
    ),
    ReportSource(
        "Latent Space",
        "community",
        "feed",
        "https://www.latent.space/feed",
        source_role="daily_news",
        category="社区与论坛",
        description="Latent Space 对 AI 产品、工程与趋势的深度内容。",
    ),
    ReportSource(
        "Simon Willison Weblog AI",
        "community",
        "feed",
        "https://feeds.feedburner.com/simonwillison",
        source_role="daily_news",
        category="社区与论坛",
        description="Simon Willison 关于 LLM 工程与工具生态的高频更新。",
    ),
]


@dataclass(slots=True)
class ArticleFetchResult:
    title: str | None
    body_text: str | None
    published_at: str | None
    fulltext_status: str
    fulltext_reason: str | None


class ReportSourceCollector:
    """Fetch and parse configured AI report sources."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        feed_timeout: float = 12.0,
        article_timeout: float = 8.0,
        max_entries_per_source: int = 5,
    ) -> None:
        self._owns_client = client is None
        self.feed_timeout = feed_timeout
        self.article_timeout = article_timeout
        self.max_entries_per_source = max_entries_per_source
        self.client = client or httpx.Client(
            timeout=feed_timeout,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            http2=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def collect(self, source: ReportSource, progress_callback=None) -> list[CollectedReportItem]:
        if source.kind == "webpage_index":
            response = self.client.get(source.url, timeout=self.feed_timeout)
            response.raise_for_status()
            return self._parse_webpage_index(source, response.text, progress_callback=progress_callback)
        if source.kind != "feed":
            raise ValueError(f"暂不支持的来源类型：{source.kind}")
        response = self.client.get(source.url, timeout=self.feed_timeout)
        response.raise_for_status()
        return self._parse_feed(source, response.text, progress_callback=progress_callback)

    def import_url(self, url: str, progress_callback=None) -> CollectedReportItem:
        normalized_url = self.normalize_article_url(url)
        if progress_callback is not None:
            progress_callback(f"[手动导入] URL 校验通过：{normalized_url}")
        try:
            response = self.client.get(normalized_url, timeout=self.article_timeout)
        except httpx.HTTPError as exc:
            raise ManualUrlImportError("network_error", f"页面访问失败：{exc}") from exc
        final_url = self.normalize_article_url(str(response.url))
        if response.status_code in {401, 403}:
            raise ManualUrlImportError("access_denied", f"页面拒绝访问：HTTP {response.status_code}")
        if response.status_code == 404:
            raise ManualUrlImportError("not_found", "页面不存在或已被移除。")
        if response.status_code >= 400:
            raise ManualUrlImportError("http_error", f"页面访问失败：HTTP {response.status_code}")

        if progress_callback is not None:
            progress_callback(f"[手动导入] 已获取页面：{final_url}")
        title = self._extract_html_title(response.text) or self._build_title_from_url(final_url)
        article_html = self._extract_article_html(response.text)
        body_text = self._extract_body_text(response.text, article_html=article_html)
        if not body_text:
            raise ManualUrlImportError("empty_body", "页面可访问，但未提取到有效正文。")
        if len(body_text.strip()) < MIN_ARTICLE_TEXT_LENGTH:
            raise ManualUrlImportError("body_too_short", "正文过短，暂时不适合生成解读和全文翻译。")
        published_at = self._extract_html_publish_date(article_html or response.text)
        domain = urlparse(final_url).netloc or "手动导入"
        summary = self._extract_meta_description(response.text) or body_text[:320]
        return CollectedReportItem(
            source_name=domain,
            title=title.strip(),
            url=final_url,
            published_at=published_at,
            summary_text=self._clean_text(summary),
            body_text=body_text,
            metadata_json={
                "group": "manual",
                "category": "手动导入",
                "default_enabled": False,
                "description": "用户手动输入 URL 导入",
                "source_url": final_url,
                "original_url": url.strip(),
                "normalized_url": final_url,
                "import_kind": "manual_url",
                "source_role": "research_report",
            },
            partial=article_html is None,
            fulltext_status="partial" if article_html is None else "full",
            fulltext_reason="页面可访问，但未识别到明确的 article/main 结构，正文完整性可能受影响。" if article_html is None else None,
        )

    @staticmethod
    def normalize_article_url(url: str) -> str:
        candidate = url.strip()
        if not candidate:
            raise ManualUrlImportError("invalid_url", "请输入有效的文章 URL。")
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ManualUrlImportError("invalid_url", "URL 必须以 http:// 或 https:// 开头，且包含域名。")
        filtered_query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid", "ref", "ref_src"}
        ]
        normalized_path = parsed.path or "/"
        if normalized_path != "/" and normalized_path.endswith("/"):
            normalized_path = normalized_path.rstrip("/")
        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                normalized_path,
                "",
                urlencode(filtered_query, doseq=True),
                "",
            )
        )

    def fetch_article_body(self, url: str) -> ArticleFetchResult:
        response = self.client.get(url, timeout=self.article_timeout)
        return self._build_article_fetch_result(response.text, response.status_code)

    def fetch_article_details(self, url: str) -> ArticleFetchResult:
        response = self.client.get(url, timeout=self.article_timeout)
        return self._build_article_fetch_result(response.text, response.status_code)

    def _parse_feed(self, source: ReportSource, xml_text: str, progress_callback=None) -> list[CollectedReportItem]:
        root = ElementTree.fromstring(xml_text)
        items: list[CollectedReportItem] = []
        entries = self._iter_feed_entries(root)[: self.max_entries_per_source]
        total = len(entries)
        for index, entry in enumerate(entries, start=1):
            title = self._find_text(entry, ["title"]) or "Untitled report"
            url = self._extract_entry_url(entry)
            if not url:
                continue
            if progress_callback is not None:
                progress_callback(f"[{source.name}] 正在抓取第 {index}/{total} 篇：{title.strip()}")
            summary = self._find_text(entry, ["description", "summary", "content"])
            body_text = None
            partial = True
            fulltext_status = "partial"
            fulltext_reason = "正文抓取未完成，当前使用摘要或索引信息降级展示。"
            try:
                article = self.fetch_article_body(url)
                body_text = article.body_text
                partial = article.fulltext_status != "full"
                fulltext_status = article.fulltext_status
                fulltext_reason = article.fulltext_reason
                if progress_callback is not None:
                    status = "正文已抓取" if body_text else "正文为空，使用摘要降级"
                    progress_callback(f"[{source.name}] 第 {index}/{total} 篇完成：{status}")
            except Exception as exc:
                partial = True
                fulltext_status = "failed"
                fulltext_reason = f"正文抓取失败：{exc}"
                if progress_callback is not None:
                    progress_callback(f"[{source.name}] 第 {index}/{total} 篇跳过正文抓取：{exc}")
            items.append(
                CollectedReportItem(
                    source_name=source.name,
                    title=title.strip(),
                    url=url,
                    published_at=self._find_text(entry, ["pubDate", "published", "updated"]),
                    summary_text=self._clean_text(summary),
                    body_text=self._clean_text(body_text),
                    metadata_json={
                        "source_url": source.url,
                        "group": source.group,
                        "category": source.category,
                        "default_enabled": source.default_enabled,
                        "description": source.description,
                        "source_role": source.source_role,
                    },
                    partial=partial,
                    fulltext_status=fulltext_status,
                    fulltext_reason=fulltext_reason,
                )
            )
        return items

    def _parse_webpage_index(self, source: ReportSource, html_text: str, progress_callback=None) -> list[CollectedReportItem]:
        article_urls = self._extract_webpage_urls(source, html_text)[: self.max_entries_per_source]
        items: list[CollectedReportItem] = []
        total = len(article_urls)
        for index, article_url in enumerate(article_urls, start=1):
            slug = article_url.rstrip("/").split("/")[-1].replace("-", " ").strip()
            title_hint = slug.title() or "Untitled report"
            if progress_callback is not None:
                progress_callback(f"[{source.name}] 正在抓取第 {index}/{total} 篇：{title_hint}")
            article = self.fetch_article_details(article_url)
            clean_title = (article.title or title_hint).replace("\\", "").strip()
            body_text = article.body_text
            partial = article.fulltext_status != "full"
            if progress_callback is not None:
                status = "正文已抓取" if body_text else "正文为空，使用标题降级"
                progress_callback(f"[{source.name}] 第 {index}/{total} 篇完成：{status}")
            items.append(
                CollectedReportItem(
                    source_name=source.name,
                    title=clean_title,
                    url=article_url,
                    published_at=article.published_at,
                    summary_text=body_text[:320] if body_text else clean_title,
                    body_text=self._clean_text(body_text),
                    metadata_json={
                        "source_url": source.url,
                        "group": source.group,
                        "category": source.category,
                        "default_enabled": source.default_enabled,
                        "description": source.description,
                        "source_role": source.source_role,
                    },
                    partial=partial,
                    fulltext_status=article.fulltext_status,
                    fulltext_reason=article.fulltext_reason,
                )
            )
        return items

    def _build_article_fetch_result(self, html_text: str, status_code: int) -> ArticleFetchResult:
        if status_code in {401, 403}:
            return ArticleFetchResult(
                title=self._extract_html_title(html_text),
                body_text=None,
                published_at=None,
                fulltext_status="restricted",
                fulltext_reason=f"站点拒绝访问正文：HTTP {status_code}",
            )
        if status_code == 404:
            return ArticleFetchResult(
                title=self._extract_html_title(html_text),
                body_text=None,
                published_at=None,
                fulltext_status="failed",
                fulltext_reason="文章页面不存在或已被移除。",
            )
        if status_code >= 400:
            return ArticleFetchResult(
                title=self._extract_html_title(html_text),
                body_text=None,
                published_at=None,
                fulltext_status="failed",
                fulltext_reason=f"正文抓取失败：HTTP {status_code}",
            )
        title = self._extract_html_title(html_text)
        article_html = self._extract_article_html(html_text)
        text = self._extract_body_text(html_text, article_html=article_html)
        summary = self._extract_meta_description(html_text)
        if summary and text:
            text = f"{summary} {text}"
        published_at = self._extract_html_publish_date(article_html or html_text)
        if text:
            return ArticleFetchResult(
                title=title,
                body_text=text[:BODY_TEXT_LIMIT],
                published_at=published_at,
                fulltext_status="full" if article_html else "partial",
                fulltext_reason=None if article_html else "页面可访问，但未识别到明确的 article/main 结构，正文完整性可能受影响。",
            )
        return ArticleFetchResult(
            title=title,
            body_text=None,
            published_at=published_at,
            fulltext_status="partial",
            fulltext_reason="页面可访问，但未提取到有效正文。",
        )

    @staticmethod
    def _iter_feed_entries(root: ElementTree.Element) -> list[ElementTree.Element]:
        rss_items = root.findall(".//item")
        if rss_items:
            return rss_items
        atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        return atom_entries

    @staticmethod
    def _find_text(entry: ElementTree.Element, tags: list[str]) -> str | None:
        for tag in tags:
            value = entry.findtext(tag)
            if value:
                return value
            atom_value = entry.findtext(f"{{http://www.w3.org/2005/Atom}}{tag}")
            if atom_value:
                return atom_value
            namespaced = entry.findtext(f".//{{*}}{tag}")
            if namespaced:
                return namespaced
        return None

    @staticmethod
    def _extract_entry_url(entry: ElementTree.Element) -> str | None:
        link_text = entry.findtext("link")
        if link_text:
            return link_text.strip()
        atom_link = entry.find("{http://www.w3.org/2005/Atom}link")
        if atom_link is not None:
            return atom_link.attrib.get("href")
        return None

    @staticmethod
    def _strip_html(value: str) -> str:
        text = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", "", value, flags=re.S | re.I)
        for token in [
            "<p>",
            "</p>",
            "<br>",
            "<br/>",
            "<br />",
            "</div>",
            "</section>",
            "</article>",
            "</main>",
            "</li>",
            "</ul>",
            "</ol>",
            "</h1>",
            "</h2>",
            "</h3>",
            "</h4>",
            "</h5>",
            "</h6>",
        ]:
            text = text.replace(token, "\n")
        while "<" in text and ">" in text:
            start = text.find("<")
            end = text.find(">", start)
            if end == -1:
                break
            text = text[:start] + text[end + 1 :]
        return unescape(text)

    @staticmethod
    def _extract_webpage_urls(source: ReportSource, html_text: str) -> list[str]:
        prefix = source.article_path_prefix or "/"
        matches = re.findall(r'href="([^"#?]+)"', html_text)
        urls: list[str] = []
        seen: set[str] = set()
        for path in matches:
            if not path.startswith(prefix):
                continue
            if any(path.startswith(excluded) for excluded in source.exclude_path_prefixes):
                continue
            article_url = urljoin(source.url, path)
            if article_url.rstrip("/") == source.url.rstrip("/"):
                continue
            if article_url in seen:
                continue
            seen.add(article_url)
            urls.append(article_url)
        return urls

    @staticmethod
    def _extract_html_title(html_text: str) -> str | None:
        title_match = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
        if title_match:
            title = unescape(title_match.group(1)).replace("\\", "").strip()
            title = title.split("|", maxsplit=1)[0].strip(" -")
            if title.endswith(" Anthropic"):
                title = title[: -len(" Anthropic")].strip(" -")
            return title
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.S | re.I)
        if h1_match:
            return " ".join(unescape(h1_match.group(1)).split())
        return None

    @staticmethod
    def _build_title_from_url(url: str) -> str:
        slug = url.rstrip("/").split("/")[-1].replace("-", " ").replace("_", " ").strip()
        return slug.title() or "Untitled report"

    @staticmethod
    def _extract_meta_description(html_text: str) -> str | None:
        match = re.search(r'<meta\s+(?:name|property)="(?:description|og:description)"\s+content="([^"]+)"', html_text, re.I)
        if not match:
            return None
        return " ".join(unescape(match.group(1)).split())

    @staticmethod
    def _extract_article_html(html_text: str) -> str | None:
        article_match = re.search(r"<article[^>]*>(.*?)</article>", html_text, re.S | re.I)
        if article_match:
            return article_match.group(1)
        main_match = re.search(r"<main[^>]*>(.*?)</main>", html_text, re.S | re.I)
        if main_match:
            return main_match.group(1)
        return None

    def _extract_body_text(self, html_text: str, *, article_html: str | None = None) -> str | None:
        text = self._strip_html(article_html or html_text)
        cleaned = self._clean_rich_text(text)
        return cleaned[:BODY_TEXT_LIMIT] if cleaned else None

    @staticmethod
    def looks_like_low_quality_body(text: str | None) -> bool:
        if not text:
            return True
        normalized = text.strip()
        lowered = normalized.lower()
        suspicious_markers = [
            "const guesttheme",
            "window.matchmedia",
            "document.documentelement",
            "__next",
            "webpack",
            "cookie.match",
        ]
        if any(marker in lowered[:1200] for marker in suspicious_markers):
            return True
        if len(normalized) < MIN_ARTICLE_TEXT_LENGTH:
            return True
        return False

    @staticmethod
    def _clean_rich_text(value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        blocks = re.split(r"\n\s*\n+", normalized)
        cleaned_blocks: list[str] = []
        for block in blocks:
            lines = [" ".join(line.split()) for line in block.splitlines()]
            compact = " ".join(part for part in lines if part).strip()
            if compact:
                cleaned_blocks.append(compact)
        if not cleaned_blocks:
            return None
        return "\n\n".join(cleaned_blocks)

    @staticmethod
    def _extract_html_publish_date(html_text: str) -> str | None:
        match = re.search(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}\b", html_text)
        return match.group(0) if match else None

    @staticmethod
    def parse_published_at(value: str | None) -> Any | None:
        if not value:
            return None
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return parsedate_to_datetime(candidate)
        except (TypeError, ValueError, IndexError, OverflowError):
            return None

    def _clean_text(self, value: str | None) -> str | None:
        if not value:
            return None
        return " ".join(self._strip_html(value).split())[:BODY_TEXT_LIMIT]
