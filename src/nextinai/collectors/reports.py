"""Collectors for AI report and announcement sources."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from typing import Any
from xml.etree import ElementTree

import httpx


@dataclass(slots=True)
class ReportSource:
    name: str
    group: str
    kind: str
    url: str
    trusted: bool = True


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


DEFAULT_REPORT_SOURCES = [
    ReportSource("OpenAI News", "default", "feed", "https://openai.com/news/rss.xml"),
    ReportSource("Anthropic News", "default", "feed", "https://www.anthropic.com/news/rss.xml"),
    ReportSource("Hugging Face Blog", "default", "feed", "https://huggingface.co/blog/feed.xml"),
    ReportSource("LessWrong AI", "default", "feed", "https://www.lesswrong.com/feed.xml?view=curated-rss"),
]


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
        self.client = client or httpx.Client(timeout=feed_timeout, headers={"User-Agent": "nextinai/0.2.0"})

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def collect(self, source: ReportSource, progress_callback=None) -> list[CollectedReportItem]:
        if source.kind != "feed":
            raise ValueError(f"暂不支持的来源类型：{source.kind}")
        response = self.client.get(source.url, timeout=self.feed_timeout)
        response.raise_for_status()
        return self._parse_feed(source, response.text, progress_callback=progress_callback)

    def fetch_article_body(self, url: str) -> str | None:
        response = self.client.get(url, timeout=self.article_timeout)
        if response.status_code >= 400:
            return None
        text = self._strip_html(response.text)
        text = " ".join(text.split())
        return text[:4000] if text else None

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
            try:
                body_text = self.fetch_article_body(url)
                partial = not bool(body_text)
                if progress_callback is not None:
                    status = "正文已抓取" if body_text else "正文为空，使用摘要降级"
                    progress_callback(f"[{source.name}] 第 {index}/{total} 篇完成：{status}")
            except Exception as exc:
                partial = True
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
                    metadata_json={"source_url": source.url, "group": source.group},
                    partial=partial,
                )
            )
        return items

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
        text = value
        for token in ["<p>", "</p>", "<br>", "<br/>", "<br />", "</div>", "</li>", "</h1>", "</h2>", "</h3>"]:
            text = text.replace(token, "\n")
        while "<" in text and ">" in text:
            start = text.find("<")
            end = text.find(">", start)
            if end == -1:
                break
            text = text[:start] + text[end + 1 :]
        return unescape(text)

    def _clean_text(self, value: str | None) -> str | None:
        if not value:
            return None
        return " ".join(self._strip_html(value).split())[:4000]
