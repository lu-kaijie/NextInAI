## ADDED Requirements

### Requirement: Tool validation failures SHALL be returned as structured retryable errors
当 tool input 缺失、类型错误、格式错误或超出能力边界时，系统必须返回结构化错误对象，供 agent 在同一编排链路中修正参数，而不是由程序静默猜测或补全。

#### Scenario: 缺少必填字段
- **WHEN** agent 调用某个工具但缺少必填参数
- **THEN** 系统返回包含 `error_type=missing_required_field`、`field`、`message`、`retryable=true` 的结构化错误
- **AND** 系统不得自动使用自然语言上下文补齐缺失参数

#### Scenario: 参数值超出支持范围
- **WHEN** agent 调用 trending 相关工具时传入不支持的 `window`
- **THEN** 系统返回包含 `error_type=unsupported_parameter`、`field=window`、`provided_value`、`allowed_values`、`retryable=true` 的结构化错误
- **AND** 系统不得再通过“两个月”“60天”等文本映射逻辑替换该参数

### Requirement: Validation errors SHALL be surface-neutral
结构化校验错误必须能被 chat、web、CLI 以一致的后端语义消费，而不是为某个入口单独拼装特殊错误文本。

#### Scenario: Chat 和 web 看到同一种参数校验语义
- **WHEN** 相同的非法 tool 参数从 chat 或 web 路径进入
- **THEN** 两条路径都收到同一结构的后端错误语义
- **AND** 不允许某一路径继续依赖本地规则兜底修正参数

### Requirement: Confirmation-gated actions SHALL preserve validation before execution
副作用型动作在进入确认门之前，也必须先完成参数校验；若参数不合法，应先返回结构化错误，而不是先挂起待确认动作。

#### Scenario: 发邮件前先校验参数
- **WHEN** agent 计划执行发送邮件或 webhook 推送
- **THEN** 系统必须先校验 channel、target、scope、view 等参数
- **AND** 只有在参数合法后，系统才可以生成待确认动作
