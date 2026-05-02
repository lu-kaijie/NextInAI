from nextinai.digests.exporters import DigestExporter


def test_digest_exporter_builds_structured_story_for_headings_lists_and_code() -> None:
    exporter = DigestExporter()
    markdown = """# 标题

## 小节

第一段内容。

- 要点一
- 要点二

```text
print("hello")
```
"""

    story = exporter._build_story(markdown)

    assert len(story) >= 5


def test_digest_exporter_exports_readable_pdf_for_long_markdown(tmp_path) -> None:
    exporter = DigestExporter()
    long_paragraph = "这是一个很长的段落，用来验证 PDF 导出在长文本情况下也能正常分页和换行。" * 30
    markdown = f"""# NextInAI 导出测试

## 摘要

{long_paragraph}

- 第一条
- 第二条

## 详细内容

{long_paragraph}
"""
    output_path = tmp_path / "sample.pdf"

    result = exporter.export_pdf(markdown, output_path)

    assert result.exists()
    assert result.stat().st_size > 1500
