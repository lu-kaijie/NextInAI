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
from nextinai.storage.files import FileStorage, ensure_workspace
from nextinai.harness.tools import DeliveryTaskStore


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


def _append_runtime_log(message: str) -> None:
    st.session_state.runtime_logs.append(message)
    st.session_state.runtime_logs = st.session_state.runtime_logs[-200:]


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


def _render_subscription_tab(service_registry, storage: FileStorage) -> None:
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
                    result = service_registry.subscription_service.add_subscription(
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
                    result = service_registry.subscription_service.sync_subscriptions(repository_filter or None)
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

    rows = service_registry.subscription_service.list_subscriptions()
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
                summary = service_registry.subscription_service.summarize_repository(summary_repo, int(summary_hours))
                _append_runtime_log(f"[subscription] 仓库摘要完成：{summary_repo}")
                st.markdown(summary)
            except Exception as exc:
                _append_runtime_log(f"[subscription] 仓库摘要失败：{exc}")
                st.error(str(exc))

    with st.expander("订阅原始状态文件", expanded=False):
        st.json(
            {
                "subscriptions": storage.load_collection("subscriptions"),
                "checkpoints": storage.load_collection("checkpoints"),
            }
        )


def _render_trending_tab(service_registry) -> None:
    st.subheader("热门项目榜")
    with st.form("trending_form"):
        window = st.selectbox("时间窗口", ["daily", "7d", "30d"], index=0)
        limit = st.slider("返回数量", min_value=1, max_value=10, value=5)
        submitted = st.form_submit_button("获取热门榜", use_container_width=True)
        if submitted:
            try:
                _append_runtime_log(f"[trending] 获取热门榜：window={window}, limit={limit}")
                result = service_registry.trending_service.get_trending(window, int(limit))
                _append_runtime_log("[trending] 热门榜生成完成")
                st.markdown(result)
            except Exception as exc:
                _append_runtime_log(f"[trending] 获取失败：{exc}")
                st.error(str(exc))


def _render_report_tab(service_registry, storage: FileStorage) -> None:
    st.subheader("AI 报告抓取与解读")

    def _progress(message: str) -> None:
        st.session_state.report_progress.append(message)
        _append_runtime_log(f"[report] {message}")

    if st.button("抓取默认来源组", use_container_width=True):
        st.session_state.report_progress = []
        try:
            _append_runtime_log("[report] 开始抓取默认来源组")
            result = service_registry.report_service.fetch_reports("default", progress_callback=_progress)
            _append_runtime_log(f"[report] 抓取完成：{result}")
            st.success(result)
        except Exception as exc:
            _append_runtime_log(f"[report] 抓取失败：{exc}")
            st.error(str(exc))

    if st.session_state.report_progress:
        st.markdown("### 抓取进度")
        st.code("\n".join(st.session_state.report_progress))

    with st.expander("最近报告解读", expanded=True):
        analyses = [
            item
            for item in storage.load_collection("analysis_results")
            if item.get("analysis_kind") == "report_interpretation"
        ]
        if analyses:
            for item in analyses[-10:][::-1]:
                st.markdown(f"#### {item['title']}")
                st.write(f"事实摘要：{item.get('factual_summary', '')}")
                st.write(f"解读分析：{item.get('interpreted_summary', '')}")
                st.divider()
        else:
            st.info("当前还没有报告解读。")


def _render_digest_tab(service_registry) -> None:
    st.subheader("简报生成与导出")
    with st.form("digest_form"):
        scope = st.selectbox("简报范围", ["daily", "7d", "30d"], index=0)
        export_md = st.checkbox("同时导出 Markdown", value=False)
        export_pdf = st.checkbox("同时导出 PDF", value=False)
        submitted = st.form_submit_button("生成简报", use_container_width=True)
        if submitted:
            try:
                _append_runtime_log(f"[digest] 开始生成简报：scope={scope}")
                digest = service_registry.digest_service.generate(scope)
                _append_runtime_log("[digest] 简报生成完成")
                st.markdown(digest)
                requested_formats: list[str] = []
                if export_md:
                    requested_formats.append("md")
                if export_pdf:
                    requested_formats.append("pdf")
                if requested_formats:
                    exported = service_registry.digest_service.export(scope, requested_formats)
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
    service_registry = build_service_registry()
    agent = AssistantAgent(storage=storage, service_registry=service_registry)

    _render_sidebar(storage)

    st.title("NextInAI 前端控制台")
    st.caption("围绕 AI 情报追踪、对话分析、简报生成和主动交付的一体化本地前端。")

    tabs = st.tabs(["Chat", "订阅", "热门榜", "报告", "简报", "任务"])
    with tabs[0]:
        _render_chat_tab(agent)
    with tabs[1]:
        _render_subscription_tab(service_registry, storage)
    with tabs[2]:
        _render_trending_tab(service_registry)
    with tabs[3]:
        _render_report_tab(service_registry, storage)
    with tabs[4]:
        _render_digest_tab(service_registry)
    with tabs[5]:
        _render_task_tab(storage)


if __name__ == "__main__":
    main()
