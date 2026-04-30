## 背景

当前项目已经具备 GitHub 订阅、热门项目分析、报告抓取、digest 导出和通知等能力，但产品形态仍以“一次命令、一次执行”为主。随着需求继续明确，项目目标已经从“一个能查情报的 CLI 工具集”升级为“一个持续运行、可交互、可行动、可定时的情报型 agent harness”。

通用 coding agent 或加少量 skill 的对话产品，理论上也能完成部分查询和摘要动作，因此 NextInAI 的差异化不能只放在“也支持自然语言问答”上，而应放在持续追踪、跨来源去重、重要性排序、主动交付和可观测 runtime 上。

## 变更内容

- 将 NextInAI 从 CLI-first 工具集升级为面向情报场景的 agent harness。
- 保留现有 CLI 与工具能力，但将其降为工具入口与底层能力层，不再作为产品本体。
- 引入核心对象模型：`SourceItem`、`IntelligenceEvent`、`AgentRun`、`Briefing`、`DeliveryTask`。
- 新增常驻对话式 `AssistantAgent` 设计，支持自然语言查询、继续追问、生成简报和执行动作。
- 将热门榜、仓库更新和报告解读统一汇聚到 `IntelligenceEvent` 层，围绕事件级情报做归并、排序和交付。
- 新增 harness runtime 设计，包括 run context、tool registry、planner/router、execution engine 和 session state。

## 能力范围

### 新增能力
- `interactive-agent`: 常驻对话式 Agent 入口，支持自然语言查询与行动。
- `intelligence-event-model`: 将原始来源内容归并为事件级情报对象，并支持排序与交付。
- `harness-runtime`: 提供运行上下文、工具路由、执行记录和会话状态管理。

### 修改能力
- `github-trend-analysis`: 从“单次榜单解释”升级为可沉淀到事件层的热门信号输入源。
- `github-subscription-tracking`: 从“仓库摘要输出”升级为可沉淀到事件层的变化信号输入源。
- `ai-report-interpretation`: 从“报告解读结果”升级为可沉淀到事件层的洞察输入源。
- `digest-and-notification`: 从“按模块拼接摘要”升级为基于 `IntelligenceEvent` 的快讯与深读交付。

## 影响范围

- 需要新增一层 harness runtime，而非继续让 CLI 直接耦合 service。
- 需要重新定义对话、调度和主动通知共享的核心运行模型。
- 需要为事件归并、排序和 agent run 记录设计更稳定的数据结构。
- 需要明确哪些能力保持规则实现，哪些交由 LLM 辅助判断。
- 未来 Web 端应复用同一套 runtime 和领域对象，而不是平行重做一套逻辑。
