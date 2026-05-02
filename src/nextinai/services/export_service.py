"""Generic export helpers for reusable intelligence content."""

from __future__ import annotations

from pathlib import Path

from nextinai.core.config import get_settings
from nextinai.digests.exporters import DigestExporter


class IntelligenceExportService:
    """Export arbitrary markdown intelligence content into supported formats."""

    def __init__(self, output_dir: Path | None = None, exporter: DigestExporter | None = None) -> None:
        settings = get_settings()
        self.output_dir = output_dir or settings.report_output_dir
        self.exporter = exporter or DigestExporter()

    def export_markdown_content(
        self,
        *,
        title: str,
        markdown: str,
        slug_prefix: str,
        formats: list[str],
    ) -> dict[str, str]:
        slug = self._build_slug(slug_prefix, title)
        exported: dict[str, str] = {}
        if "md" in formats:
            path = self.exporter.export_markdown(markdown, self.output_dir / f"{slug}.md")
            exported["md"] = str(path)
        if "pdf" in formats:
            path = self.exporter.export_pdf(markdown, self.output_dir / f"{slug}.pdf")
            exported["pdf"] = str(path)
        return exported

    @staticmethod
    def _build_slug(prefix: str, title: str) -> str:
        normalized = "".join(char.lower() if char.isalnum() else "-" for char in title)
        normalized = "-".join(part for part in normalized.split("-") if part)
        return f"{prefix}-{normalized}"
