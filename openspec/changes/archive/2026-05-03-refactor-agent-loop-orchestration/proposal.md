## Why

当前 chat agent 虽然已经接入了 LLM tool calling，但执行链路里仍保留了较多手写映射和参数补全逻辑，例如工具意图推断、默认参数注入和多分支规范化。这样会削弱 agent loop 的一致性，也让系统继续依赖“程序替 AI 做规划”的旧思路，不符合 NextInAI 作为 harness 型 AI agent 项目的目标。

现在需要把 planner、解析、校验和执行边界重新收敛，让 AI 负责完整规划下一步工具动作，程序只保留状态解析、硬校验和循环保护等确定性职责，从而形成真正可扩展的 agent loop 主干。

## What Changes

- 重构 chat assistant 的调度主线，统一为单一的多步 agent loop，由 planner 基于上下文持续决定下一步工具调用。
- 移除基于工具名的手写意图推断和大部分业务默认值注入逻辑，改为由 AI 在 tool call 阶段显式提供。
- 将“引用解析 / 对象定位 / 上下文补全”从普通规范化函数中拆出，沉淀为可被 planner 调用的 resolver/validator 工具。
- 保留并强化执行前的硬校验、确认门、重复调用保护和最大步数限制，避免无限循环、重复调用和不安全副作用。
- 调整 chat、web 和 CLI 共用的 assistant orchestration，使同一套 agent loop 能覆盖查询、详情追问、导出、订阅和投递任务场景。

## Capabilities

### New Capabilities
- `agent-loop-orchestration`: 定义 assistant 如何在单一 agent loop 中规划、执行、继续调用工具并在满足退出条件时返回最终答复。
- `tool-resolution-and-validation`: 定义 resolver/validator 工具如何处理引用解析、对象定位、参数补全和执行前校验。

### Modified Capabilities
- 无

## Impact

- 受影响代码主要在 `src/nextinai/agents/assistant.py`、harness tool registry、execution engine、chat/web 入口以及相关测试。
- 会新增 resolver/validator 类型工具及其返回结构，并调整 planner 可见工具集合与提示词。
- 需要补充 agent loop 的状态字段、日志和测试，确保 chat、web、CLI 的行为保持一致。
