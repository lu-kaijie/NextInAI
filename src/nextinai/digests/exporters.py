"""Digest export helpers for Markdown and PDF outputs."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, Preformatted, SimpleDocTemplate, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont


class DigestExporter:
    """Export digest markdown into local files."""

    def __init__(self) -> None:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        self.styles = self._build_styles()

    def _build_styles(self) -> dict[str, ParagraphStyle]:
        base = getSampleStyleSheet()
        return {
            "title": ParagraphStyle(
                "NextInAITitle",
                parent=base["Title"],
                fontName="STSong-Light",
                fontSize=20,
                leading=28,
                spaceAfter=10 * mm,
            ),
            "h1": ParagraphStyle(
                "NextInAIH1",
                parent=base["Heading1"],
                fontName="STSong-Light",
                fontSize=16,
                leading=22,
                spaceBefore=6 * mm,
                spaceAfter=3 * mm,
            ),
            "h2": ParagraphStyle(
                "NextInAIH2",
                parent=base["Heading2"],
                fontName="STSong-Light",
                fontSize=13,
                leading=18,
                spaceBefore=4 * mm,
                spaceAfter=2 * mm,
            ),
            "body": ParagraphStyle(
                "NextInAIBody",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=10.5,
                leading=16,
                spaceAfter=2.5 * mm,
            ),
            "bullet": ParagraphStyle(
                "NextInAIBullet",
                parent=base["BodyText"],
                fontName="STSong-Light",
                fontSize=10.5,
                leading=16,
                leftIndent=4 * mm,
                firstLineIndent=0,
                spaceAfter=1.5 * mm,
            ),
            "code": ParagraphStyle(
                "NextInAICode",
                parent=base["Code"],
                fontName="STSong-Light",
                fontSize=9,
                leading=13,
                leftIndent=4 * mm,
                rightIndent=4 * mm,
                spaceBefore=2 * mm,
                spaceAfter=2 * mm,
            ),
        }

    def export_markdown(self, markdown: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown + "\n", encoding="utf-8")
        return output_path

    def export_pdf(self, markdown: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self._try_export_pdf_via_html(markdown, output_path):
            return output_path
        self._export_pdf_via_reportlab(markdown, output_path)
        return output_path

    def _try_export_pdf_via_html(self, markdown: str, output_path: Path) -> bool:
        try:
            from markdown_it import MarkdownIt
            from weasyprint import HTML
        except Exception:
            return False

        renderer = MarkdownIt("commonmark", {"breaks": True, "html": False})
        body_html = renderer.render(markdown)
        title = escape(self._extract_pdf_title(markdown))
        html_document = f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      @page {{
        size: A4;
        margin: 18mm 16mm;
      }}
      body {{
        font-family: "Noto Sans CJK SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
        font-size: 12px;
        line-height: 1.75;
        color: #111827;
      }}
      h1 {{
        font-size: 24px;
        margin: 0 0 18px 0;
        border-bottom: 1px solid #d1d5db;
        padding-bottom: 10px;
      }}
      h2 {{
        font-size: 18px;
        margin: 22px 0 10px 0;
      }}
      h3 {{
        font-size: 15px;
        margin: 18px 0 8px 0;
      }}
      p {{
        margin: 0 0 10px 0;
        text-align: justify;
      }}
      ul, ol {{
        margin: 8px 0 12px 22px;
      }}
      li {{
        margin: 4px 0;
      }}
      pre {{
        white-space: pre-wrap;
        word-break: break-word;
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        padding: 10px 12px;
        font-size: 10px;
        line-height: 1.6;
      }}
      code {{
        font-family: "Sarasa Mono SC", "SFMono-Regular", Consolas, monospace;
      }}
      blockquote {{
        margin: 12px 0;
        padding-left: 12px;
        border-left: 3px solid #d1d5db;
        color: #374151;
      }}
    </style>
  </head>
  <body>
    {body_html}
  </body>
</html>
"""
        try:
            HTML(string=html_document, base_url=str(output_path.parent)).write_pdf(str(output_path))
        except Exception:
            return False
        return True

    def _export_pdf_via_reportlab(self, markdown: str, output_path: Path) -> None:
        document = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=self._extract_pdf_title(markdown),
        )
        story = self._build_story(markdown)
        document.build(story)

    def _build_story(self, markdown: str) -> list:
        story: list = []
        paragraph_lines: list[str] = []
        bullet_lines: list[str] = []
        code_lines: list[str] = []
        in_code_block = False

        def flush_paragraph() -> None:
            nonlocal paragraph_lines
            if not paragraph_lines:
                return
            text = " ".join(line.strip() for line in paragraph_lines if line.strip())
            if text:
                story.append(Paragraph(self._inline_markup(text), self.styles["body"]))
            paragraph_lines = []

        def flush_bullets() -> None:
            nonlocal bullet_lines
            if not bullet_lines:
                return
            items = [
                ListItem(Paragraph(self._inline_markup(item), self.styles["bullet"]))
                for item in bullet_lines
            ]
            story.append(ListFlowable(items, bulletType="bullet", start="circle", leftIndent=0))
            story.append(Spacer(1, 1.5 * mm))
            bullet_lines = []

        def flush_code() -> None:
            nonlocal code_lines
            if not code_lines:
                return
            story.append(Preformatted("\n".join(code_lines), self.styles["code"]))
            story.append(Spacer(1, 2 * mm))
            code_lines = []

        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()

            if stripped.startswith("```"):
                flush_paragraph()
                flush_bullets()
                if in_code_block:
                    flush_code()
                    in_code_block = False
                else:
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            if not stripped:
                flush_paragraph()
                flush_bullets()
                story.append(Spacer(1, 1.5 * mm))
                continue

            heading_level = self._heading_level(stripped)
            if heading_level is not None:
                flush_paragraph()
                flush_bullets()
                text = stripped[heading_level + 1 :].strip()
                style = "title" if heading_level == 1 and not story else "h1" if heading_level == 1 else "h2"
                story.append(Paragraph(escape(text), self.styles[style]))
                continue

            if stripped.startswith("- "):
                flush_paragraph()
                bullet_lines.append(stripped[2:].strip())
                continue

            paragraph_lines.append(stripped)

        flush_paragraph()
        flush_bullets()
        flush_code()
        return story

    @staticmethod
    def _heading_level(text: str) -> int | None:
        if text.startswith("# "):
            return 1
        if text.startswith("## "):
            return 2
        if text.startswith("### "):
            return 3
        return None

    @staticmethod
    def _extract_pdf_title(markdown: str) -> str:
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return "NextInAI Export"

    @staticmethod
    def _inline_markup(text: str) -> str:
        escaped = escape(text)
        escaped = escaped.replace("**", "")
        escaped = escaped.replace("`", "")
        return escaped
