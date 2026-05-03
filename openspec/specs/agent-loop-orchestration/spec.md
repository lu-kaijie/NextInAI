## ADDED Requirements

### Requirement: Assistant SHALL run all user requests through a single bounded agent loop
系统 MUST 使用单一的多步 agent loop 处理 chat、web 和 CLI 入口发起的 assistant 请求。planner 每一轮 SHALL 基于当前消息、会话状态和工具结果决定下一步动作；assistant MUST 在满足退出条件前持续执行该循环，而不是切换到其他调度分支。

#### Scenario: Planner completes a request in multiple tool steps
- **WHEN** 用户请求需要先查询列表、再解析详情、最后生成答复
- **THEN** assistant MUST 在同一条主 loop 中按顺序执行多个 tool call
- **THEN** assistant MUST 将每次 tool result 回填给 planner 再继续决策
- **THEN** assistant MUST 在 planner 不再请求工具时返回最终答复

#### Scenario: All entrypoints share the same orchestration behavior
- **WHEN** 用户分别通过 chat、web 或 CLI 触发同一个 assistant 请求
- **THEN** 系统 MUST 复用同一个 AssistantAgent loop contract
- **THEN** 系统 MUST 保持相同的工具调度、确认门和终止条件语义

### Requirement: Planner SHALL explicitly provide business tool inputs
对于查询、简报、导出、订阅和投递任务等业务工具，planner MUST 显式提供调用所需的业务参数；assistant MUST NOT 依赖手写业务默认值注入来替代 planner 完成规划。

#### Scenario: Planner requests trending events
- **WHEN** planner 调用 `get_trending_events`
- **THEN** tool call MUST 显式包含时间窗口参数
- **THEN** assistant MUST NOT 在未说明情况下自动为 planner 推断业务时间窗口

#### Scenario: Planner requests an export action
- **WHEN** planner 调用任一导出工具
- **THEN** tool call MUST 显式包含导出格式与目标对象信息或显式请求 resolver tool 先补全目标
- **THEN** assistant MUST NOT 通过手写导出分支自动猜测导出对象

### Requirement: Assistant SHALL terminate the loop only under explicit guard conditions
assistant MUST 以显式终止条件控制 loop，包括：planner 产出最终答复、需要用户确认、遇到不可恢复错误、达到最大步数、或检测到无增量的重复调用。系统 MUST NOT 允许无界无限循环。

#### Scenario: Planner returns final text without tool calls
- **WHEN** planner 返回非空最终文本且不包含 tool call
- **THEN** assistant MUST 结束 loop 并将该文本作为最终回复

#### Scenario: Repeated calls are detected
- **WHEN** planner 连续请求相同工具和等价参数，且上一次结果未提供新信息
- **THEN** assistant MUST 终止 loop
- **THEN** assistant MUST 返回可解释的停止原因或安全提示

#### Scenario: Maximum step budget is exceeded
- **WHEN** 单次请求的 tool-planner 循环达到系统设定的最大步数
- **THEN** assistant MUST 停止继续调用工具
- **THEN** assistant MUST 返回说明本轮未完成的终止信息

### Requirement: Tool metadata SHALL be the primary execution label
系统 MUST 以 `tool_name` 和 tool registry 元数据作为执行动作的主标签。任何意图分类如果仍需保留，MUST 从工具元数据派生，而不是依赖独立的手写工具名映射函数作为核心执行前提。

#### Scenario: Execution context is recorded for a tool call
- **WHEN** assistant 执行一次 tool call
- **THEN** RunContext 和日志 MUST 至少记录真实的 `tool_name`
- **THEN** 系统 MUST 能在不依赖手写 intent 映射函数的前提下记录这次执行
