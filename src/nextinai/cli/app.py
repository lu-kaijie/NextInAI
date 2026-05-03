"""Application CLI entrypoint."""

from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import typer
from rich.console import Console
from rich.table import Table

from nextinai.agents.assistant import AssistantAgent
from nextinai.core.config import get_settings
from nextinai.core.logging import configure_logging, get_log_path, tail_logs
from nextinai.services.registry import build_service_registry
from nextinai.storage.files import ensure_workspace

app = typer.Typer(help="NextInAI 命令行入口。")
system_app = typer.Typer(help="系统初始化与诊断命令。")
subscription_app = typer.Typer(help="GitHub 仓库订阅命令。")
trending_app = typer.Typer(help="热门项目分析命令。")
report_app = typer.Typer(help="报告采集与解读命令。")
digest_app = typer.Typer(help="简报生成与导出命令。")
notify_app = typer.Typer(help="通知发送命令。")
task_app = typer.Typer(help="推送任务与调度命令。")
app.add_typer(system_app, name="system")
app.add_typer(subscription_app, name="subscription")
app.add_typer(trending_app, name="trending")
app.add_typer(report_app, name="report")
app.add_typer(digest_app, name="digest")
app.add_typer(notify_app, name="notify")
app.add_typer(task_app, name="task")

console = Console()
chat_session_holder = {"session_id": None}


@app.callback()
def main() -> None:
    """NextInAI CLI root."""
    configure_logging()


@system_app.command("show-config")
def show_config() -> None:
    """输出当前关键配置。"""

    settings = get_settings()
    table = Table(title="NextInAI 配置概览")
    table.add_column("项目")
    table.add_column("值")
    table.add_row("环境", settings.app_env)
    table.add_row("数据目录", str(settings.data_dir))
    table.add_row("AI Provider", settings.ai_provider)
    table.add_row("AI 模型", settings.ai_model or "(未配置)")
    table.add_row("OpenAI Base URL", settings.openai_base_url or "(默认)")
    table.add_row("报告目录", str(settings.report_output_dir))
    table.add_row("默认邮件目标", settings.default_notification_email or "(未配置)")
    console.print(table)


@system_app.command("init-storage")
def init_storage(create_output_dir: bool = typer.Option(True, help="是否同时创建报告输出目录。")) -> None:
    """初始化本地存储和基础目录。"""

    settings = get_settings()
    ensure_workspace(settings)
    if create_output_dir:
        Path(settings.report_output_dir).mkdir(parents=True, exist_ok=True)
    console.print("[green]本地存储初始化完成。[/green]")


@system_app.command("show-logs")
def show_logs(lines: int = typer.Option(80, help="显示最近多少行日志。")) -> None:
    """查看最近运行日志。"""

    path = get_log_path()
    rows = tail_logs(lines)
    if not rows:
        console.print(f"[yellow]当前还没有日志文件：{path}[/yellow]")
        return
    console.print(f"[cyan]日志文件：{path}[/cyan]")
    console.print("\n".join(rows))


@subscription_app.command("add")
def add_subscription(
    repository: str = typer.Argument(..., help="GitHub 仓库，格式 owner/name。"),
    lookback_hours: int = typer.Option(24, help="初始回看时间窗口（小时）。"),
    refresh_minutes: int = typer.Option(60, help="刷新频率（分钟）。"),
) -> None:
    """新增 GitHub 仓库订阅。"""

    service = build_service_registry().subscription_service
    try:
        result = service.add_subscription(repository, lookback_hours, refresh_minutes)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(f"[green]已创建订阅：[/green]{result}")


@subscription_app.command("list")
def list_subscriptions() -> None:
    """列出当前订阅。"""

    service = build_service_registry().subscription_service
    rows = service.list_subscriptions()
    if not rows:
        console.print("[yellow]当前没有订阅。[/yellow]")
        return
    table = Table(title="仓库订阅")
    table.add_column("仓库")
    table.add_column("回看窗口")
    table.add_column("刷新频率")
    for row in rows:
        table.add_row(row["repository"], f'{row["lookback_hours"]}h', f'{row["refresh_minutes"]}m')
    console.print(table)


@subscription_app.command("sync")
def sync_subscriptions(
    repository: str | None = typer.Option(None, help="仅同步指定仓库，格式 owner/name。"),
) -> None:
    """同步一个或全部 GitHub 仓库订阅。"""

    service = build_service_registry().subscription_service
    try:
        result = service.sync_subscriptions(repository)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    synced = ", ".join(result["synced_repositories"]) if result["synced_repositories"] else "(无成功同步仓库)"
    no_updates = (
        ", ".join(result["no_update_repositories"]) if result["no_update_repositories"] else "(无)"
    )
    failed = ", ".join(result["failed_repositories"]) if result["failed_repositories"] else "(无)"
    console.print(
        f"[green]同步完成。[/green] 仓库: {synced}，新增条目: {result['new_items']}，无更新: {no_updates}，失败: {failed}"
    )


@subscription_app.command("summary")
def summarize_repository(
    repository: str = typer.Argument(..., help="GitHub 仓库，格式 owner/name。"),
    hours: int = typer.Option(24, help="摘要时间窗口（小时）。"),
) -> None:
    """输出单仓库的结构化更新摘要。"""

    service = build_service_registry().subscription_service
    try:
        result = service.summarize_repository(repository, hours)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(result)


@trending_app.command("show")
def show_trending(
    window: str = typer.Option("daily", help="热门榜时间窗口，例如 daily / 7d。"),
    limit: int = typer.Option(10, help="返回数量。"),
) -> None:
    """展示热门项目概览。"""

    service = build_service_registry().trending_service
    result = service.get_trending(window, limit)
    console.print(result)


@report_app.command("fetch")
def fetch_reports(source_group: str = typer.Option("default", help="来源组名称。")) -> None:
    """抓取报告来源。"""

    service = build_service_registry().report_service
    def _progress(message: str) -> None:
        console.print(f"[cyan]{message}[/cyan]")

    console.print(service.fetch_reports(source_group, progress_callback=_progress))


@report_app.command("import-url")
def import_report_url(url: str = typer.Argument(..., help="单篇文章 URL。")) -> None:
    """手动导入单篇文章并生成概览。"""

    service = build_service_registry().report_service

    def _progress(message: str) -> None:
        console.print(f"[cyan]{message}[/cyan]")

    detail = service.import_report_url(url, progress_callback=_progress)
    console.print(f"[green]导入完成：[/green]{detail['title']}")
    console.print(f"report_id: {detail['report_id']}")
    console.print(f"来源: {detail['source_name']}")
    console.print(f"链接: {detail['url']}")


@digest_app.command("generate")
def generate_digest(
    scope: str = typer.Option("daily", help="简报范围。"),
    export_md: bool = typer.Option(False, help="是否同时导出 Markdown 文件。"),
    export_pdf: bool = typer.Option(False, help="是否同时导出 PDF 文件。"),
) -> None:
    """生成一份简报。"""

    service = build_service_registry().digest_service
    markdown = service.generate(scope)
    console.print(markdown)
    requested_formats: list[str] = []
    if export_md:
        requested_formats.append("md")
    if export_pdf:
        requested_formats.append("pdf")
    if requested_formats:
        exported = service.export(scope, requested_formats)
        for fmt, path in exported.items():
            console.print(f"[green]{fmt} 导出完成：[/green]{path}")


@digest_app.command("export")
def export_digest(
    scope: str = typer.Option("daily", help="简报范围。"),
    md: bool = typer.Option(True, help="导出 Markdown 文件。"),
    pdf: bool = typer.Option(False, help="导出 PDF 文件。"),
) -> None:
    """导出最近一次生成的简报。"""

    formats: list[str] = []
    if md:
        formats.append("md")
    if pdf:
        formats.append("pdf")
    if not formats:
        raise typer.BadParameter("至少需要选择一种导出格式。")

    service = build_service_registry().digest_service
    exported = service.export(scope, formats)
    for fmt, path in exported.items():
        console.print(f"[green]{fmt} 导出完成：[/green]{path}")


@notify_app.command("send")
def send_notifications(
    channel: str = typer.Option(..., help="发送渠道，如 email 或 webhook。"),
    content_kind: str = typer.Option("digest", help="发送内容类型：digest 或 report。"),
    scope: str = typer.Option("daily", help="digest 范围，如 daily 或 7d。"),
    briefing_view: str = typer.Option("flash", help="digest 视图，如 flash / deep / conversation。"),
    report_title: str | None = typer.Option(None, help="当内容类型为 report 时，可指定报告标题。"),
    target: str | None = typer.Option(None, help="覆盖默认投递目标。"),
) -> None:
    """触发通知发送。"""

    service = build_service_registry().notification_service
    try:
        result = service.send(
            channel=channel,
            content_kind=content_kind,
            scope=scope,
            briefing_view=briefing_view,
            report_title=report_title,
            target=target,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print(result)


@app.command("chat")
def chat(
    message: str | None = typer.Argument(None, help="单轮消息；不传则进入常驻交互模式。"),
    session_id: str | None = typer.Option(None, help="会话 ID；不传则自动生成并复用当前进程会话。"),
) -> None:
    """进入受控式 agent 对话模式。"""

    agent = AssistantAgent()
    active_session_id = session_id or chat_session_holder["session_id"] or f"session-{uuid4()}"
    chat_session_holder["session_id"] = active_session_id
    if message is not None:
        response = agent.respond(message, session_id=active_session_id)
        console.print(response.message)
        return

    console.print(f"[cyan]进入 NextInAI chat 模式，会话 ID: {active_session_id}[/cyan]")
    console.print("[cyan]输入 exit / quit 结束，会保留会话状态。[/cyan]")
    while True:
        user_input = typer.prompt("nextinai")
        if user_input.strip().lower() in {"exit", "quit"}:
            console.print("[yellow]会话结束。[/yellow]")
            break
        response = agent.respond(user_input, session_id=active_session_id)
        console.print(response.message)


@app.command("web")
def run_web(
    port: int = typer.Option(8501, help="Streamlit 端口。"),
    address: str = typer.Option("127.0.0.1", help="Streamlit 监听地址。"),
) -> None:
    """启动 Streamlit 前端。"""

    try:
        import streamlit  # noqa: F401
    except ImportError as exc:
        raise typer.BadParameter("当前环境未安装 streamlit，请先安装依赖。") from exc

    from nextinai.web.streamlit_app import __file__ as streamlit_file

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(streamlit_file),
        "--server.port",
        str(port),
        "--server.address",
        address,
    ]
    raise SystemExit(subprocess.call(command))


@task_app.command("list")
def list_delivery_tasks() -> None:
    """列出当前推送任务。"""

    from nextinai.harness.tools import DeliveryTaskStore

    rows = DeliveryTaskStore().list_tasks()
    if not rows:
        console.print("[yellow]当前没有推送任务。[/yellow]")
        return
    table = Table(title="推送任务")
    table.add_column("ID")
    table.add_column("渠道")
    table.add_column("目标")
    table.add_column("范围")
    table.add_column("视图")
    table.add_column("频率")
    table.add_column("上次执行")
    for row in rows:
        table.add_row(
            row["task_id"],
            row["channel"],
            str(row.get("target")),
            row.get("scope", "daily"),
            row.get("view", "flash"),
            row.get("schedule") or "daily",
            row.get("last_run_at") or "(未执行)",
        )
    console.print(table)


@task_app.command("run-due")
def run_due_tasks(force: bool = typer.Option(False, help="是否强制执行全部启用任务。")) -> None:
    """执行到期的推送任务。"""

    from nextinai.scheduler import DeliveryTaskScheduler

    results = DeliveryTaskScheduler().run_due_tasks(force=force)
    if not results:
        console.print("[yellow]当前没有需要执行的推送任务。[/yellow]")
        return
    for item in results:
        color = "green" if item.status == "success" else "red"
        console.print(f"[{color}]{item.task_id}[/]: {item.status} - {item.detail}")


@task_app.command("daemon")
def task_daemon(
    poll_seconds: int = typer.Option(60, help="轮询间隔秒数。"),
    max_cycles: int | None = typer.Option(None, help="最多轮询次数；不传则持续运行。"),
    force_first_cycle: bool = typer.Option(True, help="首轮是否强制执行全部启用任务。"),
) -> None:
    """以本地轮询模式持续执行推送任务。"""

    from nextinai.scheduler import DeliveryTaskScheduler

    console.print(
        f"[cyan]启动任务守护模式：poll_seconds={poll_seconds}, max_cycles={max_cycles or '∞'}[/cyan]"
    )
    stats = DeliveryTaskScheduler().run_loop(
        poll_seconds=poll_seconds,
        max_cycles=max_cycles,
        force_first_cycle=force_first_cycle,
    )
    console.print(
        f"[green]守护模式结束。[/green] cycles={stats.cycles}, executed={stats.executed_tasks}, "
        f"success={stats.success_count}, failed={stats.failed_count}, suppressed={stats.suppressed_count}"
    )


if __name__ == "__main__":
    app()
