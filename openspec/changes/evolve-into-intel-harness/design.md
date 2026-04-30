## 背景

NextInAI 的下一阶段不再只是扩展单次 CLI 命令，而是演进为一个情报型 agent harness。该 harness 需要同时支持：

- CLI 主动查询
- 常驻对话式 agent
- 定时任务触发
- 主动通知推送
- 后续 Web / API 入口

因此架构重点不再是“再加几个命令”，而是定义一套稳定的 runtime、事件模型和交付视图。

## 目标 / 非目标

**目标：**
- 定义 harness runtime 的最小分层与核心对象
- 建立事件级情报模型，避免系统退化为流水账
- 让查询、简报、通知和对话围绕同一套对象工作
- 为后续常驻 agent shell / chat 入口做好结构铺垫

**非目标：**
- 当前变更不直接实现完整对话界面
- 当前变更不直接引入数据库或多租户能力
- 当前变更不要求第一时间引入 LangChain / LangGraph

## 分层设计

```text
Interaction Layer
- CLI
- chat shell
- future web/api

Harness Runtime Layer
- RunContext
- ToolRegistry
- Planner / Router
- ExecutionEngine
- SessionState
- AgentRun recorder

Domain & Infra Layer
- SourceItem
- IntelligenceEvent
- Briefing
- DeliveryTask
- collectors / storage / notifier / scheduler
```

### 1. Interaction Layer

负责接收用户输入和展示输出。它不直接承载业务逻辑，而是将请求转交给 runtime。

### 2. Harness Runtime Layer

这是系统核心。负责：

- 建立 run context
- 识别用户意图
- 解析会话引用对象
- 选择工具并执行
- 处理确认流
- 记录 `AgentRun`
- 更新 session state

#### 最小 runtime 接口

第一版 runtime 先收敛为以下 5 个核心接口：

- `RunContext`
- `Tool`
- `ToolRegistry`
- `SessionStateStore`
- `ExecutionEngine`

##### `RunContext`

每一次对话、CLI 触发、调度任务或主动推送，都必须运行在一个统一的 `RunContext` 下。

建议最小字段：

```text
RunContext
- run_id
- trigger_type        # chat / cli / schedule / webhook / manual
- session_id
- actor_id
- intent
- model_config
- allowed_tools[]
- metadata
- created_at
```

##### `Tool`

所有可被 `AssistantAgent` 编排的能力，都应通过统一 tool contract 暴露。

建议最小接口：

```text
Tool
- name
- description
- input_schema
- output_schema
- requires_confirmation
- execute(context, input) -> output
```

##### `ToolRegistry`

用于注册、查询和过滤当前可用工具。

建议最小接口：

```text
ToolRegistry
- register(tool)
- get(name)
- list_all()
- list_allowed(context)
```

##### `SessionStateStore`

用于支撑多轮对话中的引用解析，例如“第 3 个”“那份简报”“发出去”。

建议最小状态：

```text
SessionState
- session_id
- last_intent
- last_events[]
- last_briefing_id
- last_subject
- pending_action
- pending_tool_input
- updated_at
```

建议最小接口：

```text
SessionStateStore
- load(session_id)
- save(state)
- clear(session_id)
```

##### `ExecutionEngine`

统一负责工具执行、确认流和 run 记录。

建议最小接口：

```text
ExecutionEngine
- execute_tool(context, tool_name, tool_input)
- execute_plan(context, steps)
- record_run(context, result)
```

#### `AssistantResponse`

虽然不属于 runtime 最底层接口，但建议第一版统一定义 `AssistantResponse` 作为 Interaction Layer 的标准输出。

建议字段：

```text
AssistantResponse
- message
- referenced_event_ids[]
- referenced_briefing_id
- suggested_next_actions[]
- pending_confirmation
- confirmation_prompt
- raw_outputs
```

### 3. Domain & Infra Layer

负责底层事实与产物，不直接感知聊天或 UI 交互。包含 collectors、storage、briefing、notification 等稳定领域能力。

## 核心对象

### `SourceItem`
采集层原始输入，例如 release、PR、commit、trending 条目、feed item、报告正文等。

### `IntelligenceEvent`
系统核心认知对象。它不是原始内容，而是一件“值得被单独表达的新增变化、热度信号或洞察判断”。

### `AgentRun`
每次运行的记录对象。用于 observability、replay、debug 和 audit。

### `Briefing`
用户可读的交付产物，支持快讯版和深读版等不同视图。

### `DeliveryTask`
主动交付对象，描述发送目标、触发规则和任务状态。

## `IntelligenceEvent` 设计原则

### 定义

`IntelligenceEvent` 应由一个或多个 `SourceItem` 归并而来，代表一件对用户认知有新增价值的事件对象。

### 类型

- `change_event`
- `trend_event`
- `insight_event`

### 归并规则

第一版采用保守归并策略：

- 同对象
- 同核心变化 / 同热度信号
- 时间窗口接近

高置信才自动合并，低置信不强合并。

### 排序原则

优先级维度：

1. 新增信息强度
2. 用户相关性
3. 影响范围
4. 持续热度 / 信号强度
5. 可信度

排序目标不是复现热度，而是最大化用户单位注意力获得的新增价值。

## 交付视图

同一套 `IntelligenceEvent` 支持三种视图：

### 快讯版
- 用于快速决定今天最该看什么
- 默认只输出高优先级内容

### 深读版
- 用于建立理解
- 输出更多上下文、关联和判断边界

### 对话版
- 用于继续追问和执行动作
- 围绕 event、briefing 和 task 展开

## `AssistantAgent` 最小工作流

```text
user input
  -> intent classify
  -> reference resolve
  -> tool select
  -> execute
  -> render response
  -> session update
  -> agent run log
```

### 第一版支持的意图类型

- `query_intelligence`
- `explore_detail`
- `generate_briefing`
- `execute_action`

### 动作确认规则

默认直接执行：
- 查询
- 展开解释
- 生成预览

默认需要确认：
- 发邮件
- 发 webhook
- 创建/修改/删除定时任务
- 修改订阅

## 第一版最小工具集

第一版 `ToolRegistry` 建议按查询、生成、动作三类组织：

### 查询类
- `get_trending_events`
- `get_repo_update_events`
- `get_report_events`
- `get_event_detail`
- `get_recent_briefings`
- `get_delivery_tasks`

### 生成类
- `generate_briefing`
- `render_briefing_preview`

### 动作类
- `deliver_briefing`
- `add_subscription`
- `create_delivery_task`
- `delete_delivery_task`

## 现有能力映射与缺口

当前仓库已经具备不少 service 层能力，但大多仍以“直接返回文本给 CLI”为主要形态。第一版 harness 需要在这些 service 之上增加 event / briefing / task 适配层。

### 可直接复用或低成本复用

#### `add_subscription`
- 现状：`GitHubSubscriptionService.add_subscription`
- 结论：可直接封装为动作类 tool

#### `generate_briefing`
- 现状：`AgenticDigestService.generate`
- 结论：已有 briefing 雏形，但当前输出仍按模块拼接，需要后续逐步改为 event 驱动

#### `deliver_briefing`
- 现状：`AgenticNotificationService.send`
- 结论：已有投递能力，但输入仍偏 CLI 参数组合，需要包装为基于 `Briefing` 的动作 tool

### 可复用底层能力，但必须先做 event 适配

#### `get_trending_events`
- 现状：`GitHubTrendingService.get_trending` 直接返回文本榜单
- 缺口：需要先输出结构化 event，而不是终端展示文案

#### `get_repo_update_events`
- 现状：`GitHubSubscriptionService.summarize_repository` 直接返回 Markdown 摘要
- 缺口：需要把 release / PR / commit 的聚合结果提升为事件对象

#### `get_report_events`
- 现状：`AgenticReportService.fetch_reports` 负责抓取、解读并落盘
- 缺口：需要增加“读取已解读报告事件”的查询接口，而不是只在抓取时输出进度和总结

#### `get_event_detail`
- 现状：无直接能力
- 缺口：需要围绕 `IntelligenceEvent` 构建 detail 视图与来源链聚合

#### `get_recent_briefings`
- 现状：`digests.json` 已存在
- 缺口：需要增加简报索引与 briefing 查询接口

#### `get_delivery_tasks`
- 现状：尚未实现任务层
- 缺口：依赖 `DeliveryTask` 建模与调度层落地

#### `render_briefing_preview`
- 现状：`DigestDocument.to_markdown()` 和 `AgenticDigestService.generate` 已可输出文本
- 缺口：需要将 preview 明确为 `Briefing` 的一个渲染视图，而不是直接让 CLI 打印 markdown

### 当前尚不存在、需要新建的工具能力

#### `create_delivery_task`
- 现状：未实现
- 依赖：调度层、任务模型、确认流

#### `delete_delivery_task`
- 现状：未实现
- 依赖：任务查询与状态修改

## 迁移策略

第一阶段不直接推翻现有 service，而是增加一层 adapter：

```text
existing services
  -> event/briefing/task adapters
  -> tools
  -> AssistantAgent / chat shell
```

这样可以保留当前 CLI 可用性，同时逐步把系统核心迁移到 harness runtime。

进一步建议的最小实现路径：

```text
existing service methods
  -> adapters
  -> tool outputs
  -> ExecutionEngine
  -> AssistantResponse
  -> CLI chat / future web
```

## 文件存储承载能力评估

当前项目已经有一套本地 JSON 文件存储，适合作为 harness 第一阶段的落盘层，但需要从“面向 CLI 结果”升级为“面向 runtime 与事件对象”。

### 现有集合与建议映射

- `content_items.json`
  - 可继续承载 `SourceItem`

- `analysis_results.json`
  - 可继续作为报告解读和过渡期分析结果集合
  - 后续应逐步让更多输出汇聚到 `IntelligenceEvent`

- `digests.json`
  - 可继续承载 `Briefing`

- `deliveries.json`
  - 可继续承载 delivery records

- `job_runs.json`
  - 可作为 `AgentRun` 的过渡集合
  - 但字段需要扩充，不能只保留 job 级信息

- `subscriptions.json`
  - 可继续承载订阅配置

- `checkpoints.json`
  - 可继续承载 watch / collect 的增量游标

### 第一阶段仍然缺少的集合

- `events.json`
  - 用于承载 `IntelligenceEvent`

- `session_states.json`
  - 用于承载 `SessionState`

- `delivery_tasks.json`
  - 用于承载主动推送任务配置

### 结论

当前文件存储仍足以支撑 harness 第一阶段，但需要新增事件层、会话层和任务层集合，并为 `job_runs` 扩展为更通用的 `AgentRun` 记录结构。

## 关于 LangChain / LangGraph

本项目核心 runtime 与领域对象保持自研。

### 原则
- harness runtime 自研
- 领域模型自研
- OpenAI SDK 直连
- LangChain / LangGraph 只作为未来可能的局部编排插件

### 原因
- 当前复杂度主要在持续追踪、事件归并、排序、交付与 observability，不在 prompt 链本身
- 过早采用框架会让领域结构被框架抽象绑架

## 风险 / 权衡

- `IntelligenceEvent` 设计过重：会拖慢实现
  - 解决：第一版先保留最小字段与保守归并

- 对话 agent 过度自由：容易失控
  - 解决：第一版使用受控工作流，而非开放式自由 agent

- 事件归并过度：会破坏可信度
  - 解决：高置信才合并，低置信保留分离

- 运行记录不完整：后续无法 debug
  - 解决：从一开始引入 `AgentRun` 记录思想
