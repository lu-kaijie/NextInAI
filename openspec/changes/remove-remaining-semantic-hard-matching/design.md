## Context

当前 NextInAI 已经完成了以 tool calling 为中心的主路径改造，但 `AssistantAgent` 里仍残留一批“程序替模型理解语义”的逻辑。典型表现包括：

- 根据自然语言短语推断 `window`，例如把“最近七天”“一个月”映射成 `7d` / `30d`
- 根据自然语言短语推断 `formats`，例如把“导出 pdf”“markdown”映射成 `["pdf"]` / `["md"]`
- 根据自然语言短语推断 `hours`、`limit`、`source_name`
- 在 export、trending、report 等动作上，先由模型选工具，再由程序继续补参数
- 通过 `_mentions_trending`、`_extract_window`、`_extract_limit`、`_extract_hours`、`_extract_source_name_for_export`、`_normalize_export_formats` 之类函数继续承担语义理解责任

这会让系统停留在“工具由 agent 选择，但参数仍由规则猜”的半 agent 状态，不符合项目的 harness 定位。用户已经明确要求：

- 不保留 fallback / 降级双轨
- 不保留关键词猜工具、关键词猜参数
- 不保留程序偷偷做语义理解
- 只保留参数校验、结构化错误、引用解析、确认门和受控执行

因此这次 change 的目标不是新增功能，而是继续收缩职责边界，把剩余语义硬匹配彻底移出主链路。

## Goals / Non-Goals

**Goals:**

- 删除 chat 主路径里剩余的自然语言参数提取与语义映射逻辑
- 让 agent loop 变成唯一编排路径：模型决定工具名和参数，程序只做校验和执行
- 为不合法参数返回结构化错误，供模型二次修正，而不是程序静态补参
- 明确哪些逻辑允许保留，哪些逻辑必须删除
- 保证 web / chat / CLI 复用同一 capability 语义边界，不再在不同入口偷偷补参数

**Non-Goals:**

- 本次不扩展新业务能力
- 本次不改 GitHub Trending 的产品能力边界
- 本次不把所有异常都改造成复杂恢复链路
- 本次不引入第二套 planner、规则引擎或 DSL

## Decisions

### 1. 删除自然语言参数提取器

决策：

- 移除 `AssistantAgent` 中所有负责从自然语言文本直接推导工具参数的辅助函数和调用链
- 包括但不限于：
  - `_extract_window`
  - `_mentions_unsupported_trending_window`
  - `_extract_hours`
  - `_extract_limit`
  - `_extract_source_name_for_export`
  - `_normalize_export_formats`
  - `_mentions_trending`
  - 以及其他语义等价的 `_extract_*` / `_normalize_*` 逻辑

原因：

- 这些逻辑本质上都在代替模型做参数规划
- 它们会制造双重语义源：一套来自模型，一套来自规则
- 后续任何新能力都会继续诱导开发者往这里加补丁

影响：

- 模型必须显式传出 `window`、`formats`、`hours`、`limit`、`source_name` 等参数
- 若参数缺失或错误，系统返回结构化错误，而不是猜测用户原意

### 2. 保留引用解析，但限定为结构化上下文解析

决策：

- 允许保留“第 3 个”“上一条结果”“待确认动作”这类结构化上下文解析
- 允许把 `reference_index` 解析到会话中最近一轮列表结果
- 不允许基于模糊短语替模型补业务参数，例如“刚才那个导出成 pdf”直接推断 `formats`

原因：

- 引用解析是对会话状态的结构化寻址，不是业务语义理解
- 没有引用解析，用户无法高效追问列表中的某项结果

边界：

- 只允许解析“引用哪个对象”
- 不允许顺便推断“如何操作该对象”

### 3. 程序端只做 schema 校验和能力边界校验

决策：

- 工具层与 capability 层只负责：
  - 必填项校验
  - 类型校验
  - 枚举值校验
  - 能力边界校验
  - 副作用确认门
  - 工具执行
  - 结构化错误返回
- 不负责把自然语言翻译成参数

原因：

- 这才符合 harness 的职责边界
- 程序端越纯，日志、测试和行为就越可预测

示例：

- `window="60d"` 时，直接返回 `unsupported_parameter`
- `formats=[]` 或缺少 `formats` 时，直接返回 `missing_required_field` 或 `invalid_value`
- `repository="langchain"` 时，返回 `invalid_format`，而不是猜测为 `langchain-ai/langchain`

### 4. 结构化错误必须可供 agent 重试

决策：

- 工具执行失败时，返回统一结构的错误对象，而不是混杂自然语言长句
- 错误对象至少应包含：
  - `error_type`
  - `message`
  - `field`
  - `provided_value`
  - `allowed_values`
  - `retryable`

原因：

- 这能让模型在同一 agent loop 中据此修正参数
- 也能让 web / chat / CLI 统一展示清晰错误

### 5. web / chat / CLI 不再自行做语义补参

决策：

- chat 不再做自然语言参数补全
- web 若已有明确 UI 控件，则由控件直接提交结构化参数
- CLI 若已有显式命令参数，则继续按显式参数工作，不新增自然语言映射层

原因：

- 三个入口都必须服从同一语义边界
- 只有 chat 需要模型规划；web 和 CLI 直接提供结构化输入即可

## Allowed vs Forbidden

### Allowed

- 解析 `reference_index`
- 恢复待确认动作
- 校验参数类型、格式、范围、枚举值
- 返回结构化错误
- 对副作用操作进行确认门控制

### Forbidden

- 根据“最近七天”“这个月”等短语推断 `window`
- 根据“导出 pdf”“导出 markdown”等短语推断 `formats`
- 根据“来 5 个”“看最近一周”等短语推断 `limit` / `hours`
- 根据“OpenAI 的报告”模糊匹配 `source_name`
- 根据“热门”“最火”这类词偷偷把工具固定成 trending
- 在模型没有给出参数时，由程序用默认语义补齐用户意图

## Risks / Trade-offs

- 删除硬匹配后，模型对工具 schema 的依赖更强
  - 处理方式：补强 tool description、必填项和结构化错误
- 以前能“蒙对”的输入现在会显式报错
  - 处理方式：接受这一收紧，宁可清晰失败，也不继续隐式猜测
- 部分测试会从“自然语言触发成功”改成“模型显式给参后成功”
  - 处理方式：重写测试口径，围绕 orchestration contract 验证

## Migration Plan

第一阶段：

- 梳理并删除 `AssistantAgent` 中剩余语义提取/补全函数
- 清理相关异常类型中带有语义映射假设的部分

第二阶段：

- 在 tool registry 或执行层补齐统一的参数校验与结构化错误对象
- 调整 agent loop 让错误可回传给模型继续规划

第三阶段：

- 更新 chat、web、CLI 的相关测试
- 更新文档，明确“程序不再做自然语言参数推断”

## Open Questions

- 结构化错误对象放在 `ExecutionEngine` 统一产出，还是由 `ToolRegistry`/tool handler 层先标准化
- `reference_index` 的保留范围是否只限最近一轮结果，还是允许更长会话回溯
- 对于缺少必填项的 tool call，是否允许模型在同一轮继续补参，还是先返回用户可见错误
