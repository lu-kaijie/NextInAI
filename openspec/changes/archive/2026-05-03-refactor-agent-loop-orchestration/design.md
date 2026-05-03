## Context

NextInAI 当前已经具备 chat、web、CLI 三个入口，也已经有基于 OpenAI tool calling 的 assistant 调度能力，但 orchestration 仍处于“LLM 负责选工具，程序继续代替它补大量业务语义”的中间态。典型表现包括：

- 通过 `_infer_intent_from_tool` 为工具名手写意图分类。
- 通过 `_normalize_planned_decision` 为多种工具注入默认业务参数。
- 由 assistant 直接承担引用解析、对象定位和导出补全等多种职责。
- loop 虽然存在，但仍保留了较多“为了让 planner 输出不完整也能跑起来”的程序兜底。

这会带来三个问题：

- agent loop 的职责边界不清，难以继续扩展更多工具。
- 同一能力在 chat、web、CLI 间共享时，容易在入口层堆积额外规则。
- 测试覆盖的是“程序自动补齐后的行为”，而不是“planner + tool + guard”的真实协作行为。

本次设计需要把 assistant 收敛为真正的 harness orchestrator：planner 负责决定下一步，resolver/validator 负责状态解析和硬校验，loop controller 负责控制循环与退出。

## Goals / Non-Goals

**Goals:**

- 统一 assistant 为单一 agent loop 主线，不再保留手写意图推断和业务级默认参数分派。
- 把引用解析、对象定位、参数补全等需要状态上下文的动作暴露为 resolver/validator 工具。
- 让 planner 面对的是完整工具集合，能够通过多步 tool calling 完成查询、追问、导出、订阅和投递任务。
- 保留确定性安全边界，包括参数 schema 校验、确认门、重复调用保护、最大步数限制和错误终止。
- 让 chat、web、CLI 共用同一 orchestration 行为和日志语义。

**Non-Goals:**

- 本次不引入 LangChain / LangGraph，不重写底层 harness runtime。
- 本次不新增数据库、队列或外部任务编排系统。
- 本次不改动 intelligence 采集、PDF 渲染或报告源抓取逻辑，除非为了适配新 loop 需要极小接口调整。
- 本次不追求真正无界无限循环，loop 必须保持可预测退出。

## Decisions

### 1. 保留单一 loop controller，但把“补业务语义”从 assistant 中移除

assistant 继续作为统一入口，负责：

- 维护 `SessionState`
- 组装 planner messages
- 执行 tool call
- 把 tool 结果回填到 messages
- 根据终止条件返回最终答复

assistant 不再负责：

- 用工具名映射意图类别
- 为工具注入查询条数、时间窗、简报视图等业务默认值
- 直接把“第 1 个”解析成 event_id 或 task_id

原因：

- 这样可以保证 planner 对自己的工具决策负责，避免程序重新介入规划。
- assistant 更接近 loop controller，职责更窄，便于在 chat/web/CLI 复用。

备选方案：

- 继续保留 `_normalize_planned_decision`，只是减少部分分支。
  不采用，因为这样仍保留“程序替 planner 补语义”的核心问题。

### 2. 引入 resolver/validator 工具，而不是把所有校验都交给 LLM

新增一组面向 planner 的工具，例如：

- `resolve_event_reference`
- `resolve_delivery_task_reference`
- `prepare_briefing_context`
- `prepare_export_target`

这些工具负责处理：

- 引用编号到真实对象 ID 的映射
- 基于会话状态选取最近结果或当前焦点对象
- 对导出、简报、删除动作进行目标补全

同时保留执行前的本地硬校验：

- schema 必填字段检查
- 枚举值合法性检查
- 是否需要确认
- 最大步数与重复调用保护

原因：

- 引用解析依赖会话状态和对象集合，适合由工具暴露给 planner。
- 本地确定性校验不值得浪费一轮 LLM，也不能交由模型自由判断。

备选方案：

- 把所有解析和校验都继续放在 assistant 内部私有函数里。
  不采用，因为 planner 看不到中间解析步骤，行为不透明，且难以扩展复用。

### 3. 把“intent”从核心执行链路降级

当前 `intent` 更像日志标签，不应再成为调度前置条件。新设计中：

- planner 可以选择不返回 `intent`
- execution context 以 `tool_name` 作为主事实
- 如需意图标签，优先从工具注册表元数据派生，而不是用独立函数硬编码

原因：

- tool name 已经足够表达执行动作。
- 额外维护一层手写 intent 映射会带来重复分类和额外维护点。

备选方案：

- 继续保留 `_infer_intent_from_tool`。
  不采用，因为这是手写映射表，和本次“去规则化”的方向冲突。

### 4. loop 采用“有上限的持续迭代”，而不是真无限循环

loop controller 将基于以下条件退出：

- planner 返回无 tool call 且有最终文本
- 命中需要用户确认的副作用动作
- 工具执行出现不可恢复错误
- 命中最大步数上限
- 连续重复相同工具和相近参数且没有新信息增量

原因：

- 真无限循环不利于 harness 稳定性，也难以调试。
- bounded loop 仍然满足多步 agent 协作，同时能控制成本和风险。

备选方案：

- 完全依赖模型自行决定何时停止。
  不采用，因为容易出现循环调用、空转和成本失控。

### 5. 测试按“planner-tool-planner”真实交互建模

测试层将不再模拟单次 `decide(...)` 返回，而是模拟：

- planner 第一次返回 tool call
- assistant 执行 tool
- planner 基于 tool result 再决定下一步或结束

同时新增针对以下情况的覆盖：

- resolver tool 后接业务 tool
- 重复调用保护触发
- 最大步数触发
- planner 缺少必填参数时被 validator 拦截
- 需要确认的动作暂停并等待下一轮输入

原因：

- 这样测试才能真实反映新 orchestration 模式。

## Risks / Trade-offs

- [Risk] planner 输出质量不稳定，可能漏填参数或频繁先调错工具
  → Mitigation：收紧 tool schema、提升 system prompt、增加 resolver/validator 工具的可解释返回，并用测试覆盖关键路径。

- [Risk] 新增 resolver/validator 工具后，loop 步数增加，单次请求成本上升
  → Mitigation：只把依赖状态的解析暴露为工具，纯本地校验继续在执行层完成；为高频工具设计明确输入输出，减少试错轮次。

- [Risk] chat、web、CLI 在状态管理或日志显示上出现不一致
  → Mitigation：所有入口统一调用同一 AssistantAgent，入口层只负责展示和输入输出适配。

- [Risk] 移除默认参数注入后，短期内 planner 更容易因缺参数失败
  → Mitigation：先补充更强的 tool descriptions 和例子，再在 validator 返回中提供明确错误提示，让 planner 在下一轮自行修正。

## Migration Plan

1. 先在 `assistant.py` 内部引入新的 loop contract 和 resolver/validator 工具，但保留现有 tool registry 主体。
2. 将引用解析与导出补全逻辑迁移出 `_normalize_planned_decision`，落到独立工具或执行前 validator。
3. 移除工具名意图映射和大部分业务默认值注入，更新 planner prompt 与测试。
4. 让 chat、web、CLI 共用新的 assistant 行为，验证体验一致性。
5. 完整通过测试后再清理遗留 helper 和旧日志字段。

回滚策略：

- 如果新 loop 在真实使用中不稳定，可回滚到本次变更前的 commit；本次不设计运行时双轨开关，避免长期保留双实现。

## Open Questions

- resolver/validator 工具是否需要和普通业务工具分组展示，以减少 planner 误用。
- planner 最终输出是否需要结构化的“final answer” schema，而不是自由文本。
- `SessionState` 是否需要新增“当前焦点对象”字段，以减少重复 reference resolve。
