from nextinai.web.report_workbench import (
    build_source_category_options,
    build_source_name_options,
    chunk_reports,
    group_sources_by_category,
)


def test_group_sources_by_category() -> None:
    rows = [
        {"source_name": "OpenAI News", "category": "AI 公司"},
        {"source_name": "Anthropic News", "category": "AI 公司"},
        {"source_name": "LessWrong AI", "category": "社区与论坛"},
    ]

    grouped = group_sources_by_category(rows)

    assert list(grouped.keys()) == ["AI 公司", "社区与论坛"]
    assert len(grouped["AI 公司"]) == 2


def test_build_source_options_respect_category() -> None:
    rows = [
        {"source_name": "OpenAI News", "category": "AI 公司"},
        {"source_name": "LessWrong AI", "category": "社区与论坛"},
    ]

    categories = build_source_category_options(rows)
    names = build_source_name_options(rows, "AI 公司")

    assert categories == ["全部分类", "AI 公司", "社区与论坛"]
    assert names == ["全部来源", "OpenAI News"]


def test_chunk_reports_for_two_column_layout() -> None:
    reports = [
        {"title": "A"},
        {"title": "B"},
        {"title": "C"},
    ]

    chunks = chunk_reports(reports, columns=2)

    assert len(chunks) == 2
    assert [item["title"] for item in chunks[0]] == ["A", "B"]
    assert [item["title"] for item in chunks[1]] == ["C"]
