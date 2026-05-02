## Why

当前前端和 chat 已经能覆盖一部分 AI 情报场景，但核心交互仍然偏“受控命令壳”而不是更自然的 agent。尤其是 chat 层大量依赖硬编码关键词匹配，导致语义扩展性弱、行为不够稳健，也很难把网页端所有能力自然收敛到统一对话入口。与此同时，GitHub trending 时间窗口、报告筛选与详细解读、导出能力都还不够完整，已经开始限制产品体验。

现在推进这次变更，是为了把 NextInAI 从“能用的本地控制台”进一步升级成“真正以 agent 为中心的情报工作台”：网页功能和 chat 能力一致、报告与 GitHub 内容都支持更细粒度浏览和导出、交互逻辑从硬匹配逐步迁移到 agent loop + tool calling。

## What Changes

- 将 chat 交互从关键词硬匹配主导，升级为单路径 agent loop 的工具调用流程，并保留必要的约束与确认机制。
- 梳理并升级 GitHub trending 查询能力，优先确认 GitHub 官方接口和当前 collector 的真实边界，支持更细粒度或任意时间范围能力时再纳入产品。
- 重构“AI 公司/论坛报告”浏览体验，支持按来源筛选、查看某个来源的最近报告、点击单条进入详细解读。
- 为 GitHub 简报、公司报告摘要、详细解读增加统一导出能力，并修复当前 PDF 导出格式差、可读性弱的问题。
- 保证用户通过 chat 能完成网页上的全部核心功能，网页与 chat 共享同一套后端能力。
- 明确传统 CLI 的角色是脚本化入口、验收入口和降级入口，不要求把所有新交互能力机械同步成 CLI 参数命令。

## Capabilities

### New Capabilities
- `agent-loop-orchestration`: 用 agent loop + tool calling 驱动 chat 交互、确认流与多轮任务执行。
- `github-trending-intelligence`: 定义热门项目查询的时间窗口能力、边界与降级策略。
- `digest-and-briefing-export`: 统一 GitHub 简报、报告摘要、详细解读等内容的导出能力。
- `pdf-export-quality`: 定义 PDF 导出的排版质量、结构可读性和内容保真要求。
- `report-browsing-and-export`: 支持按来源浏览报告、查看摘要、进入详细解读，并导出摘要或详细内容。
- `cross-surface-capability-parity`: 保证 chat 与网页端共享同一套功能能力和调用链路。
- `scriptable-cli-boundary`: 明确传统 CLI 只保留高价值、适合脚本化的入口，而不是追求与 chat / web 全量同构。

### Modified Capabilities
- 无

## Impact

- 影响模块：`src/nextinai/agents/assistant.py`、`src/nextinai/harness/*`、`src/nextinai/services/*`、`src/nextinai/web/streamlit_app.py`
- 可能新增或调整的依赖：OpenAI tool-calling 相关调用方式、导出组件复用层
- 会影响 chat、网页端、导出链路、报告浏览链路以及 trending collector/查询策略
- 需要新增 openspec specs，作为后续实现与验收标准
