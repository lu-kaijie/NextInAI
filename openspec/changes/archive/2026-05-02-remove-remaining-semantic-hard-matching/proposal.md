## Why

当前 `chat` 主路径虽然已经切到了 agent loop，但代码里仍然保留了不少“程序替模型理解语义”的硬匹配逻辑，例如时间窗口短语映射、导出格式推断、报告/热门榜参数补全等。这会让系统停留在“工具由模型选、参数仍由规则猜”的半 agent 状态，不符合项目希望实现的真正 harness 形态。

现在推进这次变更，是为了把 NextInAI 进一步收敛成纯粹的 agent orchestration：模型负责决定工具和参数，程序只负责 schema 暴露、参数校验、工具执行和结构化错误返回。这样可以彻底去掉“程序偷偷做语义理解”的双轨复杂度。

## What Changes

- 移除 `AssistantAgent` 中剩余的自然语言硬匹配参数提取逻辑，不再通过代码把“最近七天”“一个月”“pdf”“markdown”“第 3 个报告”等文本直接翻译成业务参数。
- 将 agent loop 收敛为“模型产出工具名和参数 -> 程序校验并执行 -> 结果/错误返回模型”的单一交互模式。
- 为热门榜、导出、报告详情、任务操作等能力补充更严格的工具 schema 和结构化错误响应，让模型基于错误继续修正参数，而不是程序静态兜底。
- 统一梳理 chat、capability、tool registry 中所有残留的语义补全函数，删除会替模型做语义推断的部分，仅保留校验、约束和引用解析。
- 更新文档与测试，明确“参数也由 agent 决定，程序端不再做自然语言映射”这一约束。

## Capabilities

### New Capabilities
- `pure-agent-parameter-orchestration`: 定义工具参数必须由 agent 决定，程序只做校验、执行和结构化错误返回的能力边界
- `structured-tool-validation-errors`: 定义工具参数不合法或当前能力不支持时，系统如何向 agent 返回可重试的结构化错误

### Modified Capabilities
- `agent-loop-orchestration`: 将 requirement 从“主路径使用 agent loop”进一步收紧为“工具选择和参数决定都由 agent 负责”
- `cross-surface-capability-parity`: 调整为 chat / web / capability 层不得再依赖自然语言硬匹配补参数

## Impact

- 影响模块：`src/nextinai/agents/assistant.py`、`src/nextinai/harness/tools.py`、`src/nextinai/services/capabilities.py`、部分 service/collector 校验逻辑
- 会影响 chat tool-calling 交互、参数校验行为、错误返回格式，以及相关测试
- 需要新增或修改 OpenSpec specs，作为“去掉剩余语义硬匹配”的验收标准
