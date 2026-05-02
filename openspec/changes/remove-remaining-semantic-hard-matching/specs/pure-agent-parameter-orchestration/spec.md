## ADDED Requirements

### Requirement: Agent SHALL explicitly choose both tool and parameters
系统必须要求 agent 在 tool call 中显式给出工具名和业务参数。程序不得再根据用户自然语言文本补全 `window`、`hours`、`limit`、`formats`、`source_name`、`repository` 等业务参数。

#### Scenario: Trending 查询参数由 agent 显式给出
- **WHEN** 用户说“最近七天最火的项目”
- **THEN** 系统必须依赖 agent 产出的 `get_trending_events(window="7d", ...)` 或等价结构化参数
- **AND** 程序不得再通过 `_extract_window` 一类逻辑从原始文本自行推断 `window`

#### Scenario: 导出格式由 agent 显式给出
- **WHEN** 用户说“把这个报告导出成 PDF”
- **THEN** 系统必须依赖 agent 产出的 `formats=["pdf"]`
- **AND** 程序不得再通过文本匹配自动把“PDF”翻译成导出格式参数

### Requirement: Assistant SHALL not route by semantic hard matching
系统不得通过关键词枚举、短语映射或自然语言硬匹配来决定使用哪个能力或如何补齐业务参数。

#### Scenario: 程序不得通过关键词猜 trending 动作
- **WHEN** 用户输入中包含“热门”“最火”“排行榜”等词
- **THEN** 系统不得仅凭这些词在程序分支中直接锁定某个工具
- **AND** 工具选择必须来自 agent 的结构化决策

#### Scenario: 程序不得通过模糊匹配猜报告来源
- **WHEN** 用户提到某家公司或来源的报告
- **THEN** 程序不得通过字符串包含、模糊匹配或候选遍历把文本自动映射成 `source_name`
- **AND** 该参数必须由 agent 显式决定

### Requirement: Structured reference resolution MAY remain separate from semantic interpretation
系统可以保留基于会话状态的结构化引用解析，但该解析只能用于定位上下文对象，不能承担业务语义补参职责。

#### Scenario: 允许解析“第 3 个”
- **WHEN** 用户说“第 3 个详细讲讲”
- **THEN** 系统可以把 `reference_index=3` 解析到最近一轮列表结果
- **AND** 该解析只用于确定目标对象

#### Scenario: 引用解析不得顺带补业务参数
- **WHEN** 用户说“把刚才那个导出一下”
- **THEN** 系统可以解析“刚才那个”指向哪个对象
- **AND** 程序不得继续自动补全 `formats`、`scope` 或其他业务参数
