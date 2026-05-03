"""Pure helpers for the Streamlit report workbench."""

from __future__ import annotations


def build_source_category_options(source_rows: list[dict[str, object]]) -> list[str]:
    categories = sorted(
        {
            str(row.get("category"))
            for row in source_rows
            if row.get("category")
        }
    )
    return ["全部分类", *categories]


def build_source_name_options(
    source_rows: list[dict[str, object]],
    selected_category: str | None,
) -> list[str]:
    rows = source_rows
    if selected_category and selected_category != "全部分类":
        rows = [row for row in rows if row.get("category") == selected_category]
    return ["全部来源", *[str(row["source_name"]) for row in rows]]


def group_sources_by_category(source_rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in source_rows:
        category = str(row.get("category") or "未分类")
        grouped.setdefault(category, []).append(row)
    return dict(sorted(grouped.items(), key=lambda item: item[0]))


def chunk_reports(reports: list[dict[str, object]], columns: int = 2) -> list[list[dict[str, object]]]:
    if columns <= 0:
        return [reports]
    return [reports[index : index + columns] for index in range(0, len(reports), columns)]
