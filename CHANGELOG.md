# Changelog

本文档记录 NextInAI 的版本变化，重点说明每个版本新增了什么、修了什么，以及当前仍然存在的边界。

## [0.3.0] - 2026-05-01

### 新增

- 新增 Streamlit 本地前端控制台，提供 Chat、订阅、热门榜、报告、简报、任务六个页签
- 新增 `nextinai web` CLI 入口和 `make web` 启动方式
- 新增统一运行日志模块，默认写入 `data/nextinai.log`
- 新增 `nextinai system show-logs`，可直接查看最近运行日志

### 改进

- 前端直接复用现有 harness 和 service registry，而不是单独维护一套后端逻辑
- 将 assistant、tool execution、订阅同步、热门榜、报告抓取、简报生成、通知发送、任务执行全部接入统一日志链路
- README 补充前端启动、日志查看和体验路径说明

### 修复

- 修复 Streamlit 任务执行结果序列化时对 `__dict__` 的依赖问题，改为稳定的 dataclass 输出
- 修复 assistant 日志参数命名冲突导致的测试失败问题

### 当前边界

- 前端目前仍是本地单机场景，不包含鉴权、多用户和远程部署编排
- Streamlit 版本主要提供控制台和观察能力，复杂会话运营和可视化分析仍可继续增强

## [0.2.0] - 2026-04-30

### 新增

- 将项目主线从“CLI 工具集”演进为“AI 情报 harness”
- 新增 `IntelligenceEvent`、`Briefing`、`DeliveryTask`、`AgentRun` 等核心对象
- 新增 harness runtime：`RunContext`、`ToolRegistry`、`SessionStateStore`、`ExecutionEngine`
- 新增 `AssistantAgent`，支持常驻 `chat shell`
- 新增 `nextinai chat` 单轮/常驻对话入口
- 新增三种简报视图：`flash`、`deep`、`conversation`
- 新增本地推送任务系统：创建、列出、删除、执行到期任务
- 新增 `nextinai task daemon` 本地轮询守护模式
- 新增失败回退重试和重复发送抑制
- 新增 `events.json`、`session_states.json`、`delivery_tasks.json`

### 改进

- 将 trending、仓库更新、报告解读逐步汇聚到 event layer
- digest 顶部新增事件快讯视图，不再只是旧模块拼接
- 通知层支持按 `briefing_view` 发送快讯版或深读版
- chat 支持引用上一轮结果继续追问，例如“第 1 个详细讲讲”“删除第 1 个任务”
- 主动推送的执行结果会同步写入 `deliveries.json` 和 `job_runs.json`

### 修复

- 修复多轮引用依赖事件未持久化时的追问失效问题
- 修复若干 harness / services / digest 间的循环依赖问题
- 修复任务失败后只按原始 daily/weekly 窗口等待、无法及时重试的问题

### 当前边界

- 第一版常驻运行仍以本地轮询为主，不包含 systemd / supervisor / Docker 编排模板
- 调度语义仍偏个人使用场景，未提供多租户和复杂 SLA 配置
- GitHub 更新分析仍主要依赖 GitHub API 可拿到的标题、摘要和 release note，不是完整代码语义分析

## [0.1.0] - 2026-04-30

### 新增

- 初始化 Python CLI 项目骨架，建立 `collectors`、`agents`、`digests`、`notifiers`、`storage`、`services` 等模块边界
- 建立本地文件存储，使用 `data/*.json` 保存订阅、内容项、分析结果、digest 和投递记录
- 接入 OpenAI SDK，并支持通过环境变量配置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`NEXTINAI_AI_MODEL`
- 实现 GitHub 仓库订阅、同步与更新摘要
- 实现 GitHub 热门项目分析
- 实现 AI 报告抓取与解读
- 实现 digest 生成、Markdown 导出和 PDF 导出
- 实现邮件与 Webhook 通知能力
- 增加中文 README，覆盖安装、配置、体验路线和 CLI 用法

### 改进

- 将仓库更新摘要从“事件罗列”调整为“解读型输出”
- 对重复的 PR / commit / release 做合并，减少同一件事重复出现
- 将仓库摘要调整为更自然的解读型输出，减少机械结构感
- 将热门榜数据口径调整为直接对齐 GitHub 官方 Trending 页面
- 改进通知层结构，统一消息模型、投递适配器和投递记录
- 保持模型选择不写死，允许外部通过环境变量切换

### 修复

- 修复 `python -m nextinai.cli.app ...` 时 CLI 无输出的问题
- 修复 GitHub 时间戳带 `Z` 时的 ISO 时间解析错误
- 为 OpenAI 调用增加兼容回退，降低静默落回规则路径的概率

### 当前边界

- 第一版仍然是个人使用导向，不包含数据库和多用户能力
- GitHub 更新分析仍主要依赖 GitHub API 可拿到的标题、摘要和 release note，不是完整代码语义分析

### 推荐升级说明

- 首次使用建议先执行 `pip install -e .`
- 建议配置 `NEXTINAI_GITHUB_TOKEN`，否则 GitHub API 更容易触发限流
- 建议同时配置 `OPENAI_API_KEY` 与 `OPENAI_BASE_URL`，确保 AI 解读路径可用
