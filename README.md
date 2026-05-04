# NextInAI

NextInAI 是一个面向 AI 情报追踪与主动交付的 Python harness。它不是单纯抓链接的脚本，也不是只会单轮问答的命令行壳，而是围绕“持续跟踪 -> 事件归并 -> 简报生成 -> 主动推送”构建的个人情报 agent。

当前版本仍然以本地 CLI 为主要入口，但产品核心已经转向统一的 runtime、event layer、chat shell 和 task daemon。它强调：

- 跟踪你关心的 GitHub 仓库最近更新了什么
- 快速理解一段时间内最热的 GitHub 项目在做什么
- 抓取并解读主流 AI 公司、研究组织和社区来源的调查报告与每日新闻
- 将原始更新整理为中文 `IntelligenceEvent`
- 生成快讯版、深读版、对话版三种简报视图
- 通过邮件或 Webhook 发送通知
- 通过本地任务系统定时执行主动推送
- 提供 Streamlit 前端控制台，支持可视化操作与日志观察

## 项目定位

如果只做“查一下最近热门项目”或“帮我总结一篇文章”，Claude Code / Codex + skill 也能部分完成。NextInAI 的差异化重点不在“也支持聊天”，而在：

- `持续追踪`
  - 不是一次性搜索，而是面向订阅、增量更新和持续观察

- `事件级输出`
  - 不把 commit、PR、release、feed item 原样堆给你，而是提升为适合浏览和追问的事件对象

- `主动交付`
  - 支持把简报持续推到邮箱或 Webhook，而不是每次都手动执行命令

- `运行留痕`
  - 任务执行、通知结果、失败回退、抑制记录都会落盘，方便长期运行和排障

## 当前能力

- `GitHub 仓库订阅`
  - 订阅仓库
  - 增量同步 release / merged PR / commit / 文档变更
  - 输出中文更新摘要
  - 当前摘要会尽量按“新增功能 / 主要改进 / 问题修复”组织，并直接解释每项更新意味着什么

- `GitHub 热门项目分析`
  - 获取日榜或自定义时间窗内的热门 GitHub 仓库
  - 输出每个仓库是做什么的、为什么上榜、值不值得关注

- `调查报告与每日新闻`
  - 将长篇研究/实验复盘与日常新闻流拆成两条浏览路径
  - 调查报告支持“事实摘要 + 解读分析 + 详细带读 + 全文翻译”
  - 每日新闻支持主动展示最近文章的标题、来源和总结
  - 支持手动输入单篇文章 URL，直接生成概览、详细解读和全文翻译
  - 对拿不到完整正文的文章，会明确标记正文状态并阻止生成详细解读，避免误导

- `Digest 生成与导出`
  - 聚合仓库更新、热门项目和报告解读
  - 内部开始复用 event layer
  - 导出为 Markdown 和 PDF

- `Chat Shell`
  - 进入常驻会话
  - 支持查询、追问、生成简报、执行动作
  - 支持“第 1 个详细讲讲”“删除第 1 个任务”这类会话引用
  - 当前已切换为单路径 agent loop，由模型决定工具调用，不再依赖关键词 fallback 路由
  - 程序端不再根据自然语言偷偷补全时间窗口、导出格式、报告来源等业务参数

- `Web 前端`
  - 基于 Streamlit 的本地控制台
  - 支持 Chat、订阅、热门榜、调查报告、每日新闻、简报、任务七个页签
  - 支持查看最近运行日志，便于确认 agent 每一步在做什么

- `通知与任务`
  - 支持邮件通知
  - 支持 Webhook 通知
  - 支持发送 `flash / deep / conversation` 视图
  - 支持创建、列出、删除本地推送任务
  - 支持常驻轮询执行、失败回退和重复发送抑制

## 当前边界

- 第一版不使用数据库，数据默认写入 `data/*.json`
- 第一版主要面向个人使用，不做多用户权限系统
- GitHub 更新摘要仍以 API 可拿到的标题、描述、release note 为主要证据来源，不是完整代码语义理解
- OpenAI 部分研究页面会返回 `HTTP 403`，这属于站点限制，不是本地网络异常
- Anthropic research 长文当前可恢复到完整正文，OpenAI 受限页面会在界面里明确标记
- 报告/新闻来源还是第一批白名单，后续可以继续扩展

## 能力分层

NextInAI 后续会按照下面这套分层继续演进：

- `service / capability`
  - 这里是唯一真实能力层
  - 负责热门榜、仓库更新、报告浏览、详细解读、导出、任务与通知等核心能力

- `chat`
  - 这是完整 agent 入口
  - 适合多轮追问、引用上一条结果、继续导出、继续发送、继续创建任务

- `web`
  - 这是可视化入口
  - 适合浏览、筛选、查看日志和手动触发动作

- `传统 CLI`
  - 这是脚本化和验收入口
  - 保留高价值命令，但不追求和 `chat / web` 做机械式全量同步

这意味着后续新增能力时，优先顺序应该是：

1. 先落到 `service / capability`
2. 再接到 `chat` 和 `web`
3. 最后只在确实适合脚本化时，再补传统 CLI 命令

因此，传统 CLI 未来会继续保留，但它的目标不是成为“所有交互能力的参数化镜像”。

## Chat 说明

`nextinai chat` 当前依赖 AI planner 才能工作。

- 如果已配置 `OPENAI_API_KEY` 和 `NEXTINAI_AI_MODEL`，chat 会进入单路径 agent loop
- 如果未配置可用模型，chat 不会再退回关键词规则路由，而是直接提示当前无法调度

这样做是为了保持系统只有一条真实交互路径，避免“表面是 agent，底层还是命令匹配器”的双轨复杂度。

同时，chat 当前遵循一个更严格的约束：

- 模型必须显式决定工具和业务参数
- 程序只负责引用解析、参数校验、确认门、工具执行和结构化错误返回
- 如果参数缺失或不合法，系统会直接返回结构化校验错误，而不是继续猜测用户原意

## 环境要求

- Python `3.10+`
- 推荐虚拟环境目录：`.venv-nextinai`
- 运行依赖：`requirements.txt`
- 开发依赖：`requirements-dev.txt`

## 安装与初始化

### 1. 创建虚拟环境

```bash
python3 -m venv .venv-nextinai
source .venv-nextinai/bin/activate
```

### 2. 安装依赖

如果你只想运行：

```bash
pip install -r requirements.txt
```

如果你要参与开发：

```bash
pip install -r requirements-dev.txt
pip install -e .
```

安装 `-e .` 之后，就可以直接使用 `nextinai ...` 命令，而不必每次写 `python -m nextinai.cli.app ...`。

### 3. 配置环境变量

复制一份示例配置：

```bash
cp .env.example .env
```

至少建议配置这些：

```env
NEXTINAI_APP_ENV=development
NEXTINAI_DATA_DIR=./data
NEXTINAI_GITHUB_TOKEN=
OPENAI_API_KEY=
OPENAI_BASE_URL=
NEXTINAI_AI_PROVIDER=openai
NEXTINAI_AI_MODEL=
NEXTINAI_REPORT_OUTPUT_DIR=./artifacts/reports
```

说明：

- `OPENAI_API_KEY`：用于 AI 分析与解读
- `OPENAI_BASE_URL`：如果你走代理网关或兼容 OpenAI 的路由服务，需要配置
- `NEXTINAI_AI_MODEL`：建议通过环境变量指定，不在代码中写死
- `NEXTINAI_GITHUB_TOKEN`：强烈建议配置，否则 GitHub API 更容易限流

如果要使用邮件通知，还要配置：

```env
NEXTINAI_DEFAULT_NOTIFICATION_EMAIL=
NEXTINAI_SMTP_HOST=
NEXTINAI_SMTP_PORT=587
NEXTINAI_SMTP_USERNAME=
NEXTINAI_SMTP_PASSWORD=
```

如果要使用 Webhook 通知，还要配置：

```env
NEXTINAI_WEBHOOK_BASE_URL=
```

### 4. 初始化本地存储

```bash
nextinai system init-storage
```

如果你还没有安装 `-e .`，也可以用：

```bash
python -m nextinai.cli.app system init-storage
```

## 前端入口

安装依赖后，可以直接启动本地前端：

```bash
nextinai web
```

默认监听：

- 地址：`127.0.0.1`
- 端口：`8501`

也可以自定义：

```bash
nextinai web --address 0.0.0.0 --port 8501
```

如果你习惯 Makefile：

```bash
make web
```

## 快速体验

### 推荐体验路线

如果你是第一次接触 NextInAI，推荐按下面这条路径体验，能最快看出这个项目和普通抓取脚本的区别：

1. 初始化配置和本地存储

```bash
nextinai system show-config
nextinai system init-storage
```

2. 订阅一个你熟悉、近期活跃的仓库

```bash
nextinai subscription add langchain-ai/langchain
nextinai subscription sync --repository langchain-ai/langchain
nextinai subscription summary langchain-ai/langchain --hours 168
```

你应该重点看：

- 它是否真的讲清楚“最近更新了什么”
- 它是否能区分新增功能、常规维护和问题修复
- 它是否比单纯贴 commit 和链接更容易读

3. 看热门项目榜单

```bash
nextinai trending show --window daily --limit 5
```

你应该重点看：

- 每个仓库是不是只给名字，而没有解释
- 输出是否能回答“它是做什么的”“为什么最近火”

4. 抓报告并生成 digest

```bash
nextinai report fetch --source-group default
nextinai digest generate --scope daily --export-md --export-pdf
```

你应该重点看：

- digest 有没有把多种来源聚合起来
- Markdown 和 PDF 是否已经能作为一份可读简报使用

5. 试一下 chat shell 和任务系统

```bash
nextinai chat
```

进入后可以继续说：

```text
最近最火的 5 个项目
第 2 个详细讲讲
```

## 运行日志

现在 NextInAI 会把关键运行过程统一写入日志，包括：

- 收到什么用户请求
- agent loop 当前走到了哪一步
- capability 层调了哪项核心能力
- 调用了哪个工具
- 订阅同步、报告抓取、简报生成、任务执行分别进行到哪一步
- 是否成功、失败、被抑制，以及大致结果

默认日志文件：

```text
data/nextinai.log
```

直接查看最近日志：

```bash
nextinai system show-logs
```

如果你走前端，也可以在左侧边栏的“最近运行日志”里直接看。

继续在 chat 里体验多轮操作时，可以这样说：

```text
生成深读简报
每天发一份深读到邮箱
确认
列出任务
```

6. 最后再试通知或调度链路

```bash
nextinai task list
nextinai task run-due --force
```

如果你只想快速看出“这个项目有没有 agent 味道”，最值得先体验的是：

```bash
nextinai chat "最近最火的 5 个项目"
nextinai chat "给我最近 3 篇 AI 报告"
```

### 查看当前配置

```bash
nextinai system show-config
```

### 订阅一个 GitHub 仓库

```bash
nextinai subscription add openai/openai-python
nextinai subscription add langchain-ai/langchain
nextinai subscription list
```

### 同步订阅仓库更新

```bash
nextinai subscription sync
```

只同步单个仓库：

```bash
nextinai subscription sync --repository langchain-ai/langchain
```

### 生成单仓库更新摘要

```bash
nextinai subscription summary langchain-ai/langchain --hours 168
```

这个输出会尽量回答：

- 最近几天到底更新了什么
- 哪些是新增功能
- 哪些只是常规维护
- 哪些修复更值得关注

### 查看热门 GitHub 项目

```bash
nextinai trending show --window daily --limit 5
```

也可以看更长时间窗：

```bash
nextinai trending show --window 7d --limit 10
```

### 抓取并解读 AI 报告

```bash
nextinai report fetch --source-group default
```

说明：

- `web` 端现在会把“调查报告”和“每日新闻”分开显示
- 调查报告会展示正文状态：`完整正文 / 正文不完整 / 站点限制 / 抓取失败`
- 如果正文不完整或站点限制，系统不会生成详细解读，只保留概览和问题说明
- `https://openai.com/index/where-the-goblins-came-from/` 这类返回 `403` 的页面，会被记录为站点限制
- `https://www.anthropic.com/research/project-vend-2`、`https://www.anthropic.com/research/constitutional-classifiers` 这类页面当前可读取完整正文并生成深读

手动导入单篇文章 URL：

```bash
nextinai report import-url "https://openai.com/index/where-the-goblins-came-from/"
```

### 生成 digest

```bash
nextinai digest generate --scope daily
```

同时导出 Markdown 和 PDF：

```bash
nextinai digest generate --scope daily --export-md --export-pdf
```

### 导出最近一次 digest

```bash
nextinai digest export --scope daily --md --pdf
```

### 发送通知

发送 digest 到邮件：

```bash
nextinai notify send --channel email --content-kind digest --scope daily --briefing-view flash --target you@example.com
```

发送深读版 digest 到邮件：

```bash
nextinai notify send --channel email --content-kind digest --scope daily --briefing-view deep --target you@example.com
```

发送 digest 到 Webhook：

```bash
nextinai notify send --channel webhook --content-kind digest --scope daily --briefing-view flash --target https://example.com/webhook
```

发送指定报告解读：

```bash
nextinai notify send --channel email --content-kind report --report-title "OpenAI Agents Update" --target you@example.com
```

### 进入 Chat Shell

单轮模式：

```bash
nextinai chat "最近最火的 5 个项目"
```

常驻模式：

```bash
nextinai chat
```

进入后可以继续说：

```text
第 1 个详细讲讲
生成深读简报
列出任务
删除第 1 个任务
确认
```

### 管理推送任务

查看任务：

```bash
nextinai task list
```

执行到期任务：

```bash
nextinai task run-due
```

强制执行全部启用任务：

```bash
nextinai task run-due --force
```

启动本地轮询守护：

```bash
nextinai task daemon --poll-seconds 60
```

只跑 2 轮做本地验证：

```bash
nextinai task daemon --poll-seconds 5 --max-cycles 2 --force-first-cycle
```

## CLI 命令总览

### `system`

- `nextinai system show-config`
  - 查看关键配置是否生效

- `nextinai system init-storage`
  - 初始化 `data/` 和报告输出目录

### `subscription`

- `nextinai subscription add <owner/name>`
  - 新增订阅仓库

- `nextinai subscription list`
  - 查看当前订阅列表

- `nextinai subscription sync [--repository <owner/name>]`
  - 同步所有或单个订阅仓库的最新更新

- `nextinai subscription summary <owner/name> --hours <N>`
  - 生成单仓库更新解读

### `trending`

- `nextinai trending show --window <daily|Nd> --limit <N>`
  - 输出热门仓库榜单和解读

### `report`

- `nextinai report fetch --source-group default`
  - 抓取并解读预设来源组中的报告

- `nextinai report import-url "<文章 URL>"`
  - 手动导入单篇文章，直接生成概览并进入后续详细解读 / 全文翻译链路

### `digest`

- `nextinai digest generate --scope <daily|Nd>`
  - 生成 digest

- `nextinai digest generate --scope <daily|Nd> --export-md --export-pdf`
  - 生成并导出 digest

- `nextinai digest export --scope <daily|Nd> --md --pdf`
  - 导出最近一次 digest

### `notify`

- `nextinai notify send --channel email --content-kind digest`
  - 发送 digest 到邮件

- `nextinai notify send --channel webhook --content-kind digest`
  - 发送 digest 到 Webhook

- `nextinai notify send --channel email --content-kind report --report-title "<标题>"`
  - 发送指定报告解读

### `chat`

- `nextinai chat "<message>"`
  - 单轮调用 agent

- `nextinai chat`
  - 进入常驻会话模式

### `task`

- `nextinai task list`
  - 查看本地推送任务

- `nextinai task run-due [--force]`
  - 执行到期任务或强制执行全部启用任务

- `nextinai task daemon --poll-seconds <N> [--max-cycles <N>]`
  - 启动本地轮询守护模式

## 输出目录说明

- `data/subscriptions.json`
  - 仓库订阅配置

- `data/checkpoints.json`
  - 增量抓取检查点

- `data/content_items.json`
  - 采集到的 GitHub / 热门榜 / 报告原始内容

- `data/analysis_results.json`
  - 报告解读等分析结果

- `data/events.json`
  - 事件级情报对象

- `data/session_states.json`
  - chat 会话状态和引用映射

- `data/delivery_tasks.json`
  - 主动推送任务配置和执行状态

- `data/digests.json`
  - 已生成的 digest 记录

- `data/deliveries.json`
  - 通知投递记录、重试结果和 suppressed 记录

- `data/job_runs.json`
  - runtime / scheduler 执行留痕

- `artifacts/reports/`
  - 导出的 Markdown / PDF 文件

## 适合谁

如果你属于下面几类人，这个工具会比较有价值：

- 想快速知道 AI 圈今天又冒出了什么 GitHub 项目
- 关注某些框架或 SDK 的更新，但不想自己翻 commit / PR
- 想把 GitHub 更新、报告解读和榜单速览统一收敛成一份中文简报
- 想把这些结果继续发到邮箱、Webhook 或后续接企业 IM

## 开发与测试

运行测试：

```bash
pytest -q
```

只看某个模块相关测试：

```bash
pytest -q tests/test_repository_summary.py
```

## 后续规划

- 更稳定的后台运行方式，例如 systemd / supervisor / Docker 场景
- 更细粒度的推送抑制与频率控制
- 更强的证据约束，进一步减少“模型推断说得太满”
- 扩展更多 AI 公司、研究组织和社区来源
- 视需求增加 Web/API 层
