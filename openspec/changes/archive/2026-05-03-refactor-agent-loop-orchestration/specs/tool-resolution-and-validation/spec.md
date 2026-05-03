## ADDED Requirements

### Requirement: The system SHALL expose resolver tools for state-dependent target resolution
对于依赖会话状态、最近结果或引用编号的目标解析，系统 MUST 通过 resolver 工具对 planner 显式暴露解析能力，而不是要求 assistant 在业务工具执行前静默完成这类解析。

#### Scenario: Planner resolves an event reference from the previous result list
- **WHEN** 用户追问“第 2 个详细讲讲”，且 planner 尚未持有真实 `event_id`
- **THEN** planner MUST 能调用 resolver tool 解析 `reference_index=2`
- **THEN** resolver tool MUST 返回对应的真实事件标识或明确的解析失败信息

#### Scenario: Planner resolves a delivery task before deletion
- **WHEN** planner 计划删除上一轮列出的第 1 个任务
- **THEN** planner MUST 能调用 resolver tool 将引用编号解析为真实 `task_id`
- **THEN** 删除动作 MUST 使用解析后的目标执行

### Requirement: Resolver tools SHALL return planner-usable structured results
resolver/validator 工具 MUST 返回结构化结果，至少包括是否成功、解析出的对象标识、以及必要的错误或澄清信息，以便 planner 决定下一步继续执行、改参重试或向用户解释。

#### Scenario: Resolver succeeds
- **WHEN** resolver tool 成功解析出目标对象
- **THEN** 返回结果 MUST 包含可直接供下一步 tool call 使用的字段
- **THEN** planner MUST 能依据该结果继续调用后续业务工具

#### Scenario: Resolver fails
- **WHEN** resolver tool 无法从当前会话状态定位唯一对象
- **THEN** 返回结果 MUST 明确标识失败原因
- **THEN** planner MUST 能基于该结果选择澄清用户或停止本轮调用

### Requirement: Deterministic execution validation SHALL remain local to the system
对 schema 必填字段、枚举合法性、副作用确认门、步数预算和重复调用检测等确定性执行约束，系统 MUST 在本地执行层完成校验，而 MUST NOT 依赖 LLM 自主判断是否满足这些硬约束。

#### Scenario: Required field is missing
- **WHEN** planner 调用工具时缺少 schema 定义的必填字段
- **THEN** 本地 validator MUST 拦截该调用
- **THEN** assistant MUST 将结构化错误返回给 planner 或用户，而不是直接执行

#### Scenario: Side effect action requires confirmation
- **WHEN** planner 请求执行新增订阅、删除任务、发送投递等副作用动作
- **THEN** 本地执行层 MUST 在真正执行前触发确认门
- **THEN** assistant MUST 暂停 loop 并等待用户确认

### Requirement: Validation failures SHALL feed back into the active loop
当 resolver 或本地 validator 发现参数错误、目标不存在或上下文不足时，assistant MUST 将失败结果反馈回当前 loop，使 planner 有机会修正参数、先调用 resolver 工具或直接生成解释，而不是立即退回到独立的手写兜底逻辑。

#### Scenario: Planner retries after validation feedback
- **WHEN** planner 的首次业务 tool call 因参数不完整被 validator 拦截
- **THEN** assistant MUST 将结构化错误结果写回 loop 上下文
- **THEN** planner MUST 能在后续轮次改正参数或改用 resolver tool

#### Scenario: No fallback branch is used
- **WHEN** resolver 或 validator 返回失败
- **THEN** assistant MUST 继续留在同一条 agent loop 主线上处理该失败
- **THEN** 系统 MUST NOT 切换到旧的关键词匹配或手写补全分支
