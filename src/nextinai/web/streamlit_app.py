"""Streamlit frontend for NextInAI."""

from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
from typing import Any

import streamlit as st

from nextinai.agents.assistant import AssistantAgent
from nextinai.core.config import get_settings
from nextinai.core.logging import configure_logging, get_log_path, tail_logs
from nextinai.scheduler import DeliveryTaskScheduler
from nextinai.services.registry import build_service_registry
from nextinai.services.task_store import DeliveryTaskStore
from nextinai.storage.files import FileStorage, ensure_workspace
from nextinai.web.report_workbench import (
    build_source_category_options,
    build_source_name_options,
    chunk_reports,
    group_sources_by_category,
)


def _build_storage() -> FileStorage:
    settings = get_settings()
    ensure_workspace(settings)
    return FileStorage(settings.data_dir)


def _ensure_state() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = "streamlit-session"
    if "report_progress" not in st.session_state:
        st.session_state.report_progress = []
    if "runtime_logs" not in st.session_state:
        st.session_state.runtime_logs = []
    if "selected_report_source" not in st.session_state:
        st.session_state.selected_report_source = "全部来源"
    if "selected_report_category" not in st.session_state:
        st.session_state.selected_report_category = "全部分类"
    if "selected_report_id" not in st.session_state:
        st.session_state.selected_report_id = None
    if "manual_report_url" not in st.session_state:
        st.session_state.manual_report_url = ""
    if "daily_news_progress" not in st.session_state:
        st.session_state.daily_news_progress = []
    if "selected_news_source" not in st.session_state:
        st.session_state.selected_news_source = "全部来源"
    if "selected_news_category" not in st.session_state:
        st.session_state.selected_news_category = "全部分类"
    if "daily_news_auto_loaded" not in st.session_state:
        st.session_state.daily_news_auto_loaded = False


def _append_runtime_log(message: str) -> None:
    st.session_state.runtime_logs.append(message)
    st.session_state.runtime_logs = st.session_state.runtime_logs[-200:]


def _fulltext_status_label(status: str | None) -> str:
    mapping = {
        "full": "完整正文",
        "partial": "正文不完整",
        "restricted": "站点限制",
        "failed": "抓取失败",
    }
    return mapping.get(str(status or "").strip(), "未知状态")


def _render_body_text(body_text: str) -> None:
    paragraphs = [paragraph.strip() for paragraph in str(body_text).split("\n\n") if paragraph.strip()]
    if not paragraphs:
        st.info("当前没有可展示的原文正文。")
        return
    for paragraph in paragraphs:
        st.markdown(paragraph)


def _open_report_detail_page(report_id: str, auto_generate: bool = False) -> None:
    st.session_state.selected_report_id = report_id
    st.query_params["page"] = "report-detail"
    st.query_params["report_id"] = report_id
    if auto_generate:
        st.query_params["auto_generate"] = "1"
    elif "auto_generate" in st.query_params:
        del st.query_params["auto_generate"]
    st.rerun()


def _close_report_detail_page() -> None:
    if "page" in st.query_params:
        del st.query_params["page"]
    if "report_id" in st.query_params:
        del st.query_params["report_id"]
    if "auto_generate" in st.query_params:
        del st.query_params["auto_generate"]
    st.rerun()


def _render_sidebar(storage: FileStorage) -> None:
    settings = get_settings()
    st.sidebar.title("NextInAI")
    st.sidebar.caption("AI 情报 harness 控制台")
    st.sidebar.write(f"环境：`{settings.app_env}`")
    st.sidebar.write(f"模型：`{settings.ai_model or '(未配置)'}`")
    st.sidebar.write(f"数据目录：`{settings.data_dir}`")
    st.sidebar.write(f"报告目录：`{settings.report_output_dir}`")
    if st.sidebar.button("初始化本地存储", use_container_width=True):
        ensure_workspace(settings)
        Path(settings.report_output_dir).mkdir(parents=True, exist_ok=True)
        st.sidebar.success("本地存储已初始化。")

    with st.sidebar.expander("本地状态概览", expanded=False):
        for name in [
            "subscriptions",
            "content_items",
            "analysis_results",
            "deep_report_readings",
            "events",
            "delivery_tasks",
            "deliveries",
            "job_runs",
        ]:
            count = len(storage.load_collection(name))
            st.write(f"- `{name}.json`: {count}")

    with st.sidebar.expander("最近运行日志", expanded=False):
        log_path = get_log_path()
        st.caption(f"日志文件：{log_path}")
        combined_logs = tail_logs(80)
        if st.session_state.runtime_logs:
            combined_logs.extend(st.session_state.runtime_logs[-40:])
        if combined_logs:
            st.code("\n".join(combined_logs[-80:]))
        else:
            st.info("当前还没有日志。")


def _render_chat_tab(agent: AssistantAgent) -> None:
    st.subheader("对话式 Agent")
    st.caption("支持多轮引用、简报生成、任务创建与确认流。")

    cols = st.columns([3, 1])
    with cols[0]:
        st.text_input("会话 ID", key="chat_session_id")
    with cols[1]:
        if st.button("清空会话展示", use_container_width=True):
            st.session_state.chat_messages = []

    for item in st.session_state.chat_messages:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    prompt = st.chat_input("例如：最近最火的 5 个项目 / 第 2 个详细讲讲 / 生成深读简报")
    if prompt:
        _append_runtime_log(f"[chat] 用户输入：{prompt}")
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        response = agent.respond(prompt, session_id=st.session_state.chat_session_id)
        _append_runtime_log("[chat] Agent 已完成响应")
        st.session_state.chat_messages.append({"role": "assistant", "content": response.message})
        with st.chat_message("assistant"):
            st.markdown(response.message)


def _render_subscription_tab(capability_service, storage: FileStorage) -> None:
    st.subheader("GitHub 仓库订阅")
    add_col, sync_col = st.columns(2)
    with add_col:
        with st.form("subscription_add_form"):
            repository = st.text_input("新增仓库", placeholder="owner/name")
            lookback_hours = st.number_input("初始回看小时数", min_value=1, value=24)
            refresh_minutes = st.number_input("刷新频率（分钟）", min_value=1, value=60)
            submitted = st.form_submit_button("添加订阅", use_container_width=True)
            if submitted:
                try:
                    _append_runtime_log(f"[subscription] 开始添加订阅：{repository}")
                    result = capability_service.add_subscription(
                        repository,
                        int(lookback_hours),
                        int(refresh_minutes),
                    )
                    _append_runtime_log(f"[subscription] 添加订阅完成：{result}")
                    st.success(f"已创建订阅：{result}")
                except Exception as exc:
                    _append_runtime_log(f"[subscription] 添加订阅失败：{exc}")
                    st.error(str(exc))

    with sync_col:
        with st.form("subscription_sync_form"):
            repository_filter = st.text_input("仅同步指定仓库（可空）", placeholder="owner/name")
            submitted = st.form_submit_button("执行同步", use_container_width=True)
            if submitted:
                try:
                    _append_runtime_log(
                        f"[subscription] 开始同步订阅：{repository_filter or '全部仓库'}"
                    )
                    result = capability_service.sync_subscriptions(repository_filter or None)
                    _append_runtime_log(
                        f"[subscription] 同步完成：新增 {result['new_items']}，成功 {len(result['synced_repositories'])} 个"
                    )
                    st.success(
                        f"同步完成：新增 {result['new_items']}，成功 {len(result['synced_repositories'])} 个，"
                        f"失败 {len(result['failed_repositories'])} 个。"
                    )
                    st.json(result)
                except Exception as exc:
                    _append_runtime_log(f"[subscription] 同步失败：{exc}")
                    st.error(str(exc))

    rows = capability_service.list_subscriptions()
    st.markdown("### 当前订阅")
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("当前还没有订阅。")

    st.markdown("### 仓库更新摘要")
    with st.form("subscription_summary_form"):
        summary_repo = st.text_input("仓库", placeholder="owner/name")
        summary_hours = st.number_input("摘要时间窗口（小时）", min_value=1, value=168)
        submitted = st.form_submit_button("生成摘要", use_container_width=True)
        if submitted:
            try:
                _append_runtime_log(f"[subscription] 生成仓库摘要：{summary_repo}")
                summary = capability_service.summarize_repository(summary_repo, int(summary_hours))
                st.session_state["last_repo_summary"] = {
                    "repository": summary_repo,
                    "hours": int(summary_hours),
                    "markdown": summary,
                }
                _append_runtime_log(f"[subscription] 仓库摘要完成：{summary_repo}")
                st.markdown(summary)
            except Exception as exc:
                _append_runtime_log(f"[subscription] 仓库摘要失败：{exc}")
                st.error(str(exc))
    last_repo_summary = st.session_state.get("last_repo_summary")
    if last_repo_summary:
        export_cols = st.columns(2)
        with export_cols[0]:
            if st.button("导出仓库摘要 Markdown", use_container_width=True):
                exported = capability_service.export_repository_summary(
                    str(last_repo_summary["repository"]),
                    int(last_repo_summary["hours"]),
                    ["md"],
                )
                _append_runtime_log(f"[subscription] 已导出仓库摘要 Markdown：{last_repo_summary['repository']}")
                st.success("仓库摘要 Markdown 导出完成")
                st.json(exported)
        with export_cols[1]:
            if st.button("导出仓库摘要 PDF", use_container_width=True):
                exported = capability_service.export_repository_summary(
                    str(last_repo_summary["repository"]),
                    int(last_repo_summary["hours"]),
                    ["pdf"],
                )
                _append_runtime_log(f"[subscription] 已导出仓库摘要 PDF：{last_repo_summary['repository']}")
                st.success("仓库摘要 PDF 导出完成")
                st.json(exported)

    with st.expander("订阅原始状态文件", expanded=False):
        st.json(
            {
                "subscriptions": storage.load_collection("subscriptions"),
                "checkpoints": storage.load_collection("checkpoints"),
            }
        )


def _render_trending_tab(capability_service) -> None:
    st.subheader("热门项目榜")
    with st.form("trending_form"):
        window = st.selectbox("时间窗口", ["daily", "7d", "30d"], index=0)
        limit = st.slider("返回数量", min_value=1, max_value=10, value=5)
        submitted = st.form_submit_button("获取热门榜", use_container_width=True)
        if submitted:
            try:
                _append_runtime_log(f"[trending] 获取热门榜：window={window}, limit={limit}")
                result = capability_service.get_trending_markdown(window, int(limit))
                st.session_state["last_trending_result"] = {"window": window, "limit": int(limit), "markdown": result}
                _append_runtime_log("[trending] 热门榜生成完成")
                st.markdown(result)
            except Exception as exc:
                _append_runtime_log(f"[trending] 获取失败：{exc}")
                st.error(str(exc))
    last_trending_result = st.session_state.get("last_trending_result")
    if last_trending_result:
        export_cols = st.columns(2)
        with export_cols[0]:
            if st.button("导出热门榜 Markdown", use_container_width=True):
                exported = capability_service.export_trending(
                    str(last_trending_result["window"]),
                    int(last_trending_result["limit"]),
                    ["md"],
                )
                _append_runtime_log(f"[trending] 已导出热门榜 Markdown：{last_trending_result['window']}")
                st.success("热门榜 Markdown 导出完成")
                st.json(exported)
        with export_cols[1]:
            if st.button("导出热门榜 PDF", use_container_width=True):
                exported = capability_service.export_trending(
                    str(last_trending_result["window"]),
                    int(last_trending_result["limit"]),
                    ["pdf"],
                )
                _append_runtime_log(f"[trending] 已导出热门榜 PDF：{last_trending_result['window']}")
                st.success("热门榜 PDF 导出完成")
                st.json(exported)


def _render_report_detail_page(capability_service) -> None:
    report_id = str(st.query_params.get("report_id", st.session_state.selected_report_id or "")).strip()
    if not report_id:
        st.warning("缺少报告标识，无法打开详细页。")
        if st.button("返回报告页", use_container_width=True):
            _close_report_detail_page()
        return

    st.session_state.selected_report_id = report_id
    detail = capability_service.get_report_detail(report_id)
    if detail is None:
        st.error("未找到这篇报告，可能筛选条件变化或本地数据已被清理。")
        if st.button("返回报告页", use_container_width=True):
            _close_report_detail_page()
        return

    auto_generate = str(st.query_params.get("auto_generate", "")).strip() == "1"
    if auto_generate and not detail.get("deep_reading_ready") and detail.get("can_deep_read"):
        with st.spinner("正在生成详细解读..."):
            detail = capability_service.generate_deep_report_reading(report_id, force=False)
        if "auto_generate" in st.query_params:
            del st.query_params["auto_generate"]

    if detail.get("body_text") and not detail.get("full_translation_text"):
        with st.spinner("正在生成全文翻译..."):
            detail = capability_service.generate_report_excerpt_translation(report_id, force=False)

    back_col, open_col = st.columns([1, 1])
    with back_col:
        if st.button("返回报告总览", use_container_width=True):
            _close_report_detail_page()
    with open_col:
        st.link_button("打开原文", str(detail["url"]), use_container_width=True)

    st.title(str(detail["title"]))
    st.caption(
        f"{'调查报告' if detail.get('source_role') == 'research_report' else '每日新闻'} | "
        f"{detail['source_name']} | {detail.get('source_category') or '未分类'} | "
        f"{detail.get('published_at') or '未知时间'}"
    )

    meta_cols = st.columns(5)
    meta_cols[0].metric("来源", str(detail["source_name"]))
    meta_cols[1].metric("分类", str(detail.get("source_category") or "未分类"))
    meta_cols[2].metric("发布时间", str(detail.get("published_at") or "未知"))
    meta_cols[3].metric("正文状态", _fulltext_status_label(str(detail.get("fulltext_status") or "")))
    meta_cols[4].metric("深读状态", "已生成" if detail.get("deep_reading_ready") else "未生成")
    if detail.get("fulltext_reason"):
        st.info(f"正文状态说明：{detail['fulltext_reason']}")
    if not detail.get("can_deep_read"):
        st.warning(str(detail.get("deep_read_block_reason") or "当前无法生成详细解读。"))

    action_cols = st.columns(4)
    with action_cols[0]:
        if st.button(
            "生成 / 刷新详细解读",
            key="detail-refresh-deep",
            use_container_width=True,
            disabled=not bool(detail.get("can_deep_read")),
        ):
            _append_runtime_log(f"[report] 强制刷新详细解读：{report_id}")
            try:
                with st.spinner("正在生成详细解读..."):
                    detail = capability_service.generate_deep_report_reading(report_id, force=True)
                st.success("详细解读已刷新。")
            except Exception as exc:
                st.error(str(exc))
    with action_cols[1]:
        if st.button("刷新原文正文", key="detail-refresh-body", use_container_width=True):
            try:
                with st.spinner("正在重新抓取正文..."):
                    detail = capability_service.import_report_url(str(detail["url"]))
                st.success("原文正文已刷新。")
            except Exception as exc:
                st.error(str(exc))
    with action_cols[2]:
        if st.button(
            "导出详细解读 Markdown",
            key="detail-export-md",
            use_container_width=True,
            disabled=not bool(detail.get("deep_reading_ready")),
        ):
            exported = capability_service.export_report(report_id, ["md"])
            st.success("详细解读 Markdown 导出完成")
            st.json(exported)
    with action_cols[3]:
        if st.button(
            "导出详细解读 PDF",
            key="detail-export-pdf",
            use_container_width=True,
            disabled=not bool(detail.get("deep_reading_ready")),
        ):
            exported = capability_service.export_report(report_id, ["pdf"])
            st.success("详细解读 PDF 导出完成")
            st.json(exported)

    detail_tabs = st.tabs(["快速概览", "原文正文", "详细解读", "全文翻译"])
    with detail_tabs[0]:
        st.write(f"快速概览：{detail.get('overview_summary') or '暂无'}")
        st.write(f"事实摘要：{detail.get('factual_summary') or detail.get('summary_text') or '暂无'}")
        st.write(f"概览解读：{detail.get('interpreted_summary') or '暂无'}")
    with detail_tabs[1]:
        body_text = str(detail.get("body_text") or "").strip()
        if body_text:
            _render_body_text(body_text)
        else:
            st.info("当前没有可展示的原文正文。")
    with detail_tabs[2]:
        if detail.get("deep_reading_markdown"):
            st.markdown(str(detail["deep_reading_markdown"]))
        elif not detail.get("can_deep_read"):
            st.info(str(detail.get("deep_read_block_reason") or "当前无法生成详细解读。"))
        else:
            st.info("这篇报告还没有生成详细解读。点击上方按钮后，系统会按需生成长篇带读。")
    with detail_tabs[3]:
        if detail.get("body_text"):
            excerpt_action_cols = st.columns(2)
            with excerpt_action_cols[0]:
                if st.button("刷新全文翻译", key="detail-refresh-excerpt", use_container_width=True):
                    with st.spinner("正在刷新全文翻译..."):
                        detail = capability_service.generate_report_excerpt_translation(report_id, force=True)
                    st.success("全文翻译已刷新。")
            with excerpt_action_cols[1]:
                generated_at = detail.get("full_translation_generated_at") or "未记录"
                st.caption(f"全文翻译生成时间：{generated_at}")
            translation_text = str(detail.get("full_translation_text") or "").strip()
            if translation_text:
                _render_body_text(translation_text)
            else:
                st.info("全文翻译生成中，请稍候。")
        else:
            st.info("当前没有可展示的正文内容。")


def _render_report_tab(capability_service, storage: FileStorage) -> None:
    st.subheader("调查报告")
    st.caption("聚焦长篇研究、实验复盘、政策研究与公司深度文章。")

    def _progress(message: str) -> None:
        st.session_state.report_progress.append(message)
        _append_runtime_log(f"[report] {message}")

    if st.button("抓取默认来源组", use_container_width=True):
        st.session_state.report_progress = []
        try:
            _append_runtime_log("[report] 开始抓取调查报告来源")
            result = capability_service.fetch_reports("default", progress_callback=_progress, source_role="research_report")
            _append_runtime_log(f"[report] 抓取完成：{result}")
            st.success(result)
        except Exception as exc:
            _append_runtime_log(f"[report] 抓取失败：{exc}")
            st.error(str(exc))

    if st.session_state.report_progress:
        with st.expander("抓取进度", expanded=False):
            st.code("\n".join(st.session_state.report_progress))

    st.markdown("### 手动导入文章 URL")
    with st.form("manual_report_url_form"):
        manual_url = st.text_input(
            "文章链接",
            key="manual_report_url",
            placeholder="https://openai.com/index/where-the-goblins-came-from/",
        )
        submitted = st.form_submit_button("导入并开始阅读", use_container_width=True)
        if submitted:
            st.session_state.report_progress = []
            try:
                _append_runtime_log(f"[report] 开始手动导入 URL：{manual_url}")
                detail = capability_service.import_report_url(manual_url, progress_callback=_progress)
                _append_runtime_log(f"[report] URL 导入完成：{detail.get('title')}")
                _open_report_detail_page(str(detail["report_id"]), auto_generate=False)
            except Exception as exc:
                _append_runtime_log(f"[report] URL 导入失败：{exc}")
                st.error(str(exc))

    st.markdown("### 调查报告来源")
    source_rows = capability_service.list_report_sources(source_role="research_report")
    if source_rows:
        grouped_sources = group_sources_by_category(source_rows)
        for category, rows in grouped_sources.items():
            with st.expander(f"{category} ({len(rows)})", expanded=False):
                for row in rows:
                    latest = row.get("latest_published_at") or "暂无"
                    status = "默认抓取" if row.get("default_enabled") else "手动抓取"
                    st.markdown(f"**{row['source_name']}**")
                    st.caption(f"{row.get('description') or '暂无描述'}")
                    st.write(
                        f"来源组：{row.get('group') or '未标记'} | 报告数：{row.get('report_count') or 0} | "
                        f"最近发布时间：{latest} | {status}"
                    )
                    if row.get("last_issue"):
                        st.warning(f"最近抓取问题：{row.get('last_issue')}")
                    st.link_button("打开来源", str(row["url"]), use_container_width=False)
                    st.divider()
    else:
        st.info("当前还没有可展示的报告来源。")

    filter_cols = st.columns([1, 1, 1])
    with filter_cols[0]:
        category_options = build_source_category_options(source_rows)
        if st.session_state.selected_report_category not in category_options:
            st.session_state.selected_report_category = category_options[0]
        selected_category = st.selectbox("按分类筛选", category_options, key="selected_report_category")
    with filter_cols[1]:
        source_options = build_source_name_options(source_rows, selected_category)
        if st.session_state.selected_report_source not in source_options:
            st.session_state.selected_report_source = source_options[0]
        selected_source = st.selectbox("按来源筛选", source_options, key="selected_report_source")
    with filter_cols[2]:
        report_limit = st.slider("展示数量", min_value=4, max_value=24, value=12, step=2)
    active_source = None if selected_source == "全部来源" else selected_source
    active_category = None if selected_category == "全部分类" else selected_category
    reports = capability_service.list_reports(
        source_name=active_source,
        limit=report_limit,
        source_category=active_category,
        source_role="research_report",
    )

    st.markdown("### 最近调查报告")
    if reports:
        summary_export_cols = st.columns(2)
        with summary_export_cols[0]:
            if st.button("导出当前报告摘要 Markdown", use_container_width=True):
                exported = capability_service.export_report_summary(
                    active_source,
                    report_limit,
                    ["md"],
                    source_category=active_category,
                    source_role="research_report",
                )
                _append_runtime_log(f"[report] 已导出报告摘要 Markdown：{active_source or active_category or '全部来源'}")
                st.success("报告摘要 Markdown 导出完成")
                st.json(exported)
        with summary_export_cols[1]:
            if st.button("导出当前报告摘要 PDF", use_container_width=True):
                exported = capability_service.export_report_summary(
                    active_source,
                    report_limit,
                    ["pdf"],
                    source_category=active_category,
                    source_role="research_report",
                )
                _append_runtime_log(f"[report] 已导出报告摘要 PDF：{active_source or active_category or '全部来源'}")
                st.success("报告摘要 PDF 导出完成")
                st.json(exported)
        for row_index, report_row in enumerate(chunk_reports(reports, columns=2)):
            columns = st.columns(2)
            for col_index, report in enumerate(report_row):
                with columns[col_index]:
                    with st.container(border=True):
                        st.markdown(f"#### {report['title']}")
                        st.caption(
                            f"{report['source_name']} | {report.get('source_category') or '未分类'} | "
                            f"{report.get('published_at') or '未知时间'}"
                        )
                        st.write(report.get("overview_summary") or "暂无概览摘要")
                        status_text = "已生成详细解读" if report.get("deep_reading_ready") else "未生成详细解读"
                        if report.get("fulltext_status"):
                            status_text += f" | {_fulltext_status_label(str(report.get('fulltext_status')))}"
                        st.caption(status_text)
                        if report.get("fulltext_reason"):
                            st.info(str(report.get("fulltext_reason")))

                        action_cols = st.columns(3)
                        report_id = str(report["report_id"])
                        with action_cols[0]:
                            if st.button("查看详细区", key=f"report-open-{row_index}-{col_index}", use_container_width=True):
                                _append_runtime_log(f"[report] 打开详细页：{report_id}")
                                _open_report_detail_page(report_id, auto_generate=False)
                        with action_cols[1]:
                            if st.button("生成详细解读", key=f"report-deep-{row_index}-{col_index}", use_container_width=True):
                                _append_runtime_log(f"[report] 打开详细页并准备生成解读：{report_id}")
                                _open_report_detail_page(report_id, auto_generate=True)
                        with action_cols[2]:
                            st.link_button("原文链接", str(report["url"]), use_container_width=True)

                        with st.expander("查看概览详情", expanded=False):
                            st.write(f"事实摘要：{report.get('factual_summary') or '暂无'}")
                            st.write(f"解读概览：{report.get('interpreted_summary') or '暂无'}")

        st.info("点击卡片里的“查看详细区”或“生成详细解读”，会打开独立阅读页。")
    else:
        st.info("当前筛选条件下还没有可查看的报告。")

    with st.expander("最近已生成的详细解读", expanded=False):
        readings = storage.load_collection("deep_report_readings")
        if readings:
            readings.sort(key=lambda item: item.get("generated_at", ""), reverse=True)
            for item in readings[:10]:
                st.markdown(f"#### {item['title']}")
                st.caption(f"生成时间：{item.get('generated_at') or '未知'}")
                st.write(item.get("summary") or "暂无摘要")
                st.divider()
        else:
            st.info("当前还没有已生成的详细解读。")

    with st.expander("最近抓取问题", expanded=False):
        issues = [item for item in storage.load_collection("report_skips") if item.get("reason") not in {"duplicate"}]
        if issues:
            for item in issues[-20:][::-1]:
                source = item.get("source") or "未知来源"
                reason = item.get("reason") or "未知原因"
                title = item.get("title")
                line = f"[{source}] {reason}"
                if title:
                    line += f" | {title}"
                st.write(line)
        else:
            st.info("当前没有抓取问题记录。")


def _render_daily_news_tab(capability_service, storage: FileStorage) -> None:
    st.subheader("每日新闻")
    st.caption("主动展示官方动态、社区讨论和 AI 新闻流，默认看标题、来源和总结。")

    def _progress(message: str) -> None:
        st.session_state.daily_news_progress.append(message)
        _append_runtime_log(f"[daily-news] {message}")

    existing_news = capability_service.list_daily_news(limit=12)
    if not existing_news and not st.session_state.daily_news_auto_loaded:
        st.session_state.daily_news_auto_loaded = True
        try:
            st.session_state.daily_news_progress = []
            _append_runtime_log("[daily-news] 首次进入页面，自动抓取默认新闻来源")
            with st.spinner("首次进入页面，正在自动抓取每日新闻..."):
                result = capability_service.fetch_reports("default", progress_callback=_progress, source_role="daily_news")
            _append_runtime_log(f"[daily-news] 自动抓取完成：{result}")
            st.success(result)
            existing_news = capability_service.list_daily_news(limit=12)
        except Exception as exc:
            _append_runtime_log(f"[daily-news] 自动抓取失败：{exc}")
            st.warning(f"自动抓取每日新闻失败：{exc}")

    news_action_cols = st.columns([1, 1])
    with news_action_cols[0]:
        if st.button("抓取默认新闻来源", use_container_width=True):
            st.session_state.daily_news_progress = []
            try:
                _append_runtime_log("[daily-news] 手动抓取默认新闻来源")
                result = capability_service.fetch_reports("default", progress_callback=_progress, source_role="daily_news")
                _append_runtime_log(f"[daily-news] 抓取完成：{result}")
                st.success(result)
            except Exception as exc:
                _append_runtime_log(f"[daily-news] 抓取失败：{exc}")
                st.error(str(exc))
    with news_action_cols[1]:
        if st.button("刷新新闻列表", use_container_width=True):
            st.rerun()

    if st.session_state.daily_news_progress:
        with st.expander("新闻抓取进度", expanded=False):
            st.code("\n".join(st.session_state.daily_news_progress))

    source_rows = capability_service.list_report_sources(source_role="daily_news")
    filter_cols = st.columns([1, 1, 1])
    with filter_cols[0]:
        category_options = build_source_category_options(source_rows)
        if st.session_state.selected_news_category not in category_options:
            st.session_state.selected_news_category = category_options[0]
        selected_category = st.selectbox("按分类筛选", category_options, key="selected_news_category")
    with filter_cols[1]:
        source_options = build_source_name_options(source_rows, selected_category)
        if st.session_state.selected_news_source not in source_options:
            st.session_state.selected_news_source = source_options[0]
        selected_source = st.selectbox("按来源筛选", source_options, key="selected_news_source")
    with filter_cols[2]:
        news_limit = st.slider("展示数量", min_value=6, max_value=24, value=12, step=3, key="daily-news-limit")

    active_source = None if selected_source == "全部来源" else selected_source
    active_category = None if selected_category == "全部分类" else selected_category
    news_rows = capability_service.list_daily_news(
        source_name=active_source,
        limit=int(news_limit),
        source_category=active_category,
    )

    st.markdown("### 最近新闻")
    if news_rows:
        export_cols = st.columns(2)
        with export_cols[0]:
            if st.button("导出当前新闻摘要 Markdown", use_container_width=True):
                exported = capability_service.export_report_summary(
                    active_source,
                    int(news_limit),
                    ["md"],
                    source_category=active_category,
                    source_role="daily_news",
                )
                _append_runtime_log(f"[daily-news] 已导出新闻摘要 Markdown：{active_source or active_category or '全部来源'}")
                st.success("新闻摘要 Markdown 导出完成")
                st.json(exported)
        with export_cols[1]:
            if st.button("导出当前新闻摘要 PDF", use_container_width=True):
                exported = capability_service.export_report_summary(
                    active_source,
                    int(news_limit),
                    ["pdf"],
                    source_category=active_category,
                    source_role="daily_news",
                )
                _append_runtime_log(f"[daily-news] 已导出新闻摘要 PDF：{active_source or active_category or '全部来源'}")
                st.success("新闻摘要 PDF 导出完成")
                st.json(exported)
        for row_index, news_row in enumerate(chunk_reports(news_rows, columns=2)):
            columns = st.columns(2)
            for col_index, item in enumerate(news_row):
                with columns[col_index]:
                    with st.container(border=True):
                        st.markdown(f"#### {item['title']}")
                        st.caption(
                            f"{item['source_name']} | {item.get('source_category') or '未分类'} | "
                            f"{item.get('published_at') or '未知时间'}"
                        )
                        st.write(item.get("overview_summary") or "暂无总结")
                        status = _fulltext_status_label(str(item.get("fulltext_status") or ""))
                        st.caption(f"正文状态：{status}")
                        if item.get("fulltext_reason"):
                            st.info(str(item.get("fulltext_reason")))
                        action_cols = st.columns(3)
                        report_id = str(item["report_id"])
                        with action_cols[0]:
                            if st.button("打开阅读页", key=f"news-open-{row_index}-{col_index}", use_container_width=True):
                                _append_runtime_log(f"[daily-news] 打开新闻阅读页：{report_id}")
                                _open_report_detail_page(report_id, auto_generate=False)
                        with action_cols[1]:
                            if st.button("生成详细解读", key=f"news-deep-{row_index}-{col_index}", use_container_width=True):
                                _append_runtime_log(f"[daily-news] 打开新闻阅读页并尝试深读：{report_id}")
                                _open_report_detail_page(report_id, auto_generate=True)
                        with action_cols[2]:
                            st.link_button("原文链接", str(item["url"]), use_container_width=True)
    else:
        st.info("当前还没有可展示的每日新闻。")

    with st.expander("新闻来源", expanded=False):
        if source_rows:
            grouped_sources = group_sources_by_category(source_rows)
            for category, rows in grouped_sources.items():
                st.markdown(f"**{category}**")
                for row in rows:
                    latest = row.get("latest_published_at") or "暂无"
                    st.write(
                        f"{row['source_name']} | 抓取文章数 {row.get('report_count') or 0} | 最近发布时间 {latest}"
                    )
                    if row.get("last_issue"):
                        st.caption(f"最近问题：{row.get('last_issue')}")
        else:
            st.info("当前还没有新闻来源。")


def _render_digest_tab(capability_service) -> None:
    st.subheader("简报生成与导出")
    with st.form("digest_form"):
        scope = st.selectbox("简报范围", ["daily", "7d", "30d"], index=0)
        export_md = st.checkbox("同时导出 Markdown", value=False)
        export_pdf = st.checkbox("同时导出 PDF", value=False)
        submitted = st.form_submit_button("生成简报", use_container_width=True)
        if submitted:
            try:
                _append_runtime_log(f"[digest] 开始生成简报：scope={scope}")
                digest = capability_service.generate_digest(scope)
                _append_runtime_log("[digest] 简报生成完成")
                st.markdown(digest)
                requested_formats: list[str] = []
                if export_md:
                    requested_formats.append("md")
                if export_pdf:
                    requested_formats.append("pdf")
                if requested_formats:
                    exported = capability_service.export_digest(scope, requested_formats)
                    _append_runtime_log(f"[digest] 导出完成：{','.join(requested_formats)}")
                    st.success("导出完成")
                    st.json(exported)
            except Exception as exc:
                _append_runtime_log(f"[digest] 简报处理失败：{exc}")
                st.error(str(exc))


def _render_task_tab(storage: FileStorage) -> None:
    st.subheader("推送任务与守护执行")
    scheduler = DeliveryTaskScheduler(storage=storage)
    task_store = DeliveryTaskStore(storage)

    task_rows = task_store.list_tasks()
    st.markdown("### 当前任务")
    if task_rows:
        st.dataframe(task_rows, use_container_width=True)
    else:
        st.info("当前还没有推送任务。你可以先在 Chat 页通过自然语言创建任务。")

    run_cols = st.columns(2)
    with run_cols[0]:
        if st.button("执行到期任务", use_container_width=True):
            _append_runtime_log("[task] 开始执行到期任务")
            results = scheduler.run_due_tasks(force=False)
            if results:
                _append_runtime_log(f"[task] 执行完成：{len(results)} 个任务")
                st.json([asdict(result) for result in results])
            else:
                _append_runtime_log("[task] 当前没有需要执行的任务")
                st.info("当前没有需要执行的任务。")
    with run_cols[1]:
        if st.button("强制执行全部启用任务", use_container_width=True):
            _append_runtime_log("[task] 开始强制执行全部任务")
            results = scheduler.run_due_tasks(force=True)
            if results:
                _append_runtime_log(f"[task] 强制执行完成：{len(results)} 个任务")
                st.json([asdict(result) for result in results])
            else:
                _append_runtime_log("[task] 当前没有可执行任务")
                st.info("当前没有可执行的任务。")

    st.markdown("### 最近投递记录")
    deliveries = storage.load_collection("deliveries")
    if deliveries:
        st.dataframe(deliveries[-20:][::-1], use_container_width=True)
    else:
        st.info("当前还没有投递记录。")

    st.markdown("### 最近运行记录")
    job_runs = storage.load_collection("job_runs")
    if job_runs:
        st.dataframe(job_runs[-20:][::-1], use_container_width=True)
    else:
        st.info("当前还没有运行记录。")


def main() -> None:
    configure_logging()
    st.set_page_config(
        page_title="NextInAI",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _ensure_state()
    storage = _build_storage()
    service_registry = build_service_registry(storage)
    capability_service = service_registry.capability_service
    agent = AssistantAgent(storage=storage, service_registry=service_registry)

    _render_sidebar(storage)

    if str(st.query_params.get("page", "")).strip() == "report-detail":
        _render_report_detail_page(capability_service)
        return

    st.title("NextInAI 前端控制台")
    st.caption("围绕 AI 情报追踪、对话分析、简报生成和主动交付的一体化本地前端。")

    tabs = st.tabs(["Chat", "订阅", "热门榜", "调查报告", "每日新闻", "简报", "任务"])
    with tabs[0]:
        _render_chat_tab(agent)
    with tabs[1]:
        _render_subscription_tab(capability_service, storage)
    with tabs[2]:
        _render_trending_tab(capability_service)
    with tabs[3]:
        _render_report_tab(capability_service, storage)
    with tabs[4]:
        _render_daily_news_tab(capability_service, storage)
    with tabs[5]:
        _render_digest_tab(capability_service)
    with tabs[6]:
        _render_task_tab(storage)


if __name__ == "__main__":
    main()
