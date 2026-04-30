## ADDED Requirements

### Requirement: 系统以统一 runtime 承载不同入口的执行流程
系统 SHALL 使用统一的 harness runtime 处理 chat、CLI、schedule 等不同触发来源，而不是让每个入口各自耦合业务逻辑。

#### Scenario: CLI 与 chat 共享执行逻辑
- **WHEN** 用户通过 CLI 主动查询，或通过常驻会话提出同一类请求
- **THEN** 系统应复用同一套 tool contract 和 execution flow，而不是维护两套平行业务实现

#### Scenario: 定时任务触发同一业务链路
- **WHEN** 调度器触发简报生成或主动推送
- **THEN** 系统应通过同一 runtime 执行链路完成，而不是绕开 run context 与记录体系

### Requirement: 系统为每次执行建立统一运行上下文
系统 SHALL 为每次用户请求、调度任务或主动推送建立 `RunContext`，用于承载触发来源、意图、会话状态和可用工具范围。

#### Scenario: 对话请求创建 run context
- **WHEN** 用户在常驻会话中输入一条自然语言请求
- **THEN** 系统应创建带 `session_id`、`intent` 和 `allowed_tools` 的运行上下文

#### Scenario: 调度任务创建 run context
- **WHEN** 某个 delivery task 或 watch task 被定时触发
- **THEN** 系统应创建带 `trigger_type=schedule` 的运行上下文，并记录执行过程

### Requirement: 系统通过统一 tool contract 暴露能力
系统 SHALL 将查询、生成和动作能力统一注册为 tool，并允许 runtime 基于上下文路由到这些工具。

#### Scenario: 查询类请求调用只读工具
- **WHEN** 用户请求热门项目、仓库更新或报告列表
- **THEN** 系统应调用相应的查询类 tool，并返回结构化结果

#### Scenario: 动作类请求要求确认
- **WHEN** 用户请求发送通知、创建任务或修改订阅
- **THEN** tool 应声明该动作需要确认，runtime 在确认前不得直接执行

### Requirement: 系统维护会话状态以支持多轮引用
系统 SHALL 保存最小会话状态，用于解析“第 3 个”“刚才那份简报”“发出去”等多轮引用表达。

#### Scenario: 基于上一轮结果继续追问
- **WHEN** 用户在上一轮已经看到一组事件列表后继续说“第 3 个详细讲讲”
- **THEN** 系统应根据 session state 将“第 3 个”解析为上一轮返回的具体事件

#### Scenario: 基于上一轮生成物执行动作
- **WHEN** 用户上一轮刚生成简报，下一轮说“发到邮箱”
- **THEN** 系统应从 session state 中解析当前 briefing 引用，并进入动作确认流

### Requirement: 系统记录每次运行的执行轨迹
系统 SHALL 使用 `AgentRun` 记录输入、工具调用、输出、确认流和错误信息，以支持调试、重放和可观测性。

#### Scenario: 多步计划执行成功
- **WHEN** 系统执行“查询 -> 生成简报 -> 发送通知”的多步链路
- **THEN** 系统应在一次或一组关联的 `AgentRun` 中记录完整步骤、结果与最终状态

#### Scenario: 执行中断或失败
- **WHEN** 工具报错、用户未确认动作或外部目标不可达
- **THEN** 系统应记录中断原因与上下文，并向上层返回明确状态
