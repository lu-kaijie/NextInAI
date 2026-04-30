"""Digest export helpers for Markdown and PDF outputs."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


class DigestExporter:
    """Export digest markdown into local files."""

    def __init__(self) -> None:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    def export_markdown(self, markdown: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
        return output_path

    def export_pdf(self, markdown: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(output_path), pagesize=A4)
        pdf.setFont("STSong-Light", 12)
        width, height = A4
        margin_x = 48
        cursor_y = height - 48
        for raw_line in markdown.splitlines():
            line = raw_line if raw_line else " "
            wrapped = self._wrap_line(line, 46)
            for item in wrapped:
                if cursor_y < 48:
                    pdf.showPage()
                    pdf.setFont("STSong-Light", 12)
                    cursor_y = height - 48
                pdf.drawString(margin_x, cursor_y, item)
                cursor_y -= 18
        pdf.save()
        return output_path

    @staticmethod
    def _wrap_line(text: str, width: int) -> list[str]:
        if len(text) <= width:
            return [text]
        return [text[index : index + width] for index in range(0, len(text), width)]
