## ADDED Requirements

### Requirement: Web 报告工作台 SHALL 提供手动 URL 导入入口
Web 报告工作台 MUST 提供显式的文章 URL 输入入口，使用户能够不依赖预配置来源目录，直接粘贴单篇文章链接并启动阅读流程。

#### Scenario: 用户在工作台输入 URL
- **WHEN** 用户在 Web 报告工作台输入一篇文章 URL 并提交
- **THEN** 系统 MUST 启动 URL 校验、抓取和阅读结果准备流程
- **THEN** 页面 MUST 给出进行中的状态提示

#### Scenario: URL 导入成功
- **WHEN** 某个 URL 已成功抓取并生成可用概览
- **THEN** 工作台 MUST 提供进入统一阅读页的入口
- **THEN** 用户 MUST 不需要先等待该文章出现在来源抓取列表中

### Requirement: Web 报告工作台 SHALL 明确展示 URL 导入失败原因
当用户通过工作台导入 URL 失败时，页面 MUST 直接展示清晰的失败原因，并允许用户修改 URL 后重试。页面 MUST NOT 只表现为无响应、空白或静默失败。

#### Scenario: 非法 URL 立即报错
- **WHEN** 用户提交非法 URL
- **THEN** 页面 MUST 直接显示 URL 校验失败原因
- **THEN** 系统 MUST NOT 进入后续抓取步骤

#### Scenario: 正文无法解析
- **WHEN** 页面请求成功但正文无法提取
- **THEN** 工作台 MUST 展示“正文为空”或“页面结构无法解析”等明确错误
- **THEN** 用户 MUST 能继续尝试其他 URL

### Requirement: Web 报告工作台 SHALL 复用现有阅读与深读体验
通过 URL 导入的文章在 Web 端 MUST 复用现有详细阅读页、详细解读生成入口、全文翻译和导出能力。工作台只负责发起导入和进入阅读，不负责承载全部长篇阅读内容。

#### Scenario: 用户从 URL 导入结果进入详细页
- **WHEN** 用户点击 URL 导入成功后的查看入口
- **THEN** 系统 MUST 跳转到现有详细阅读页或同等独立阅读视图
- **THEN** 该阅读视图 MUST 支持继续生成详细解读和全文翻译

#### Scenario: 工作台不承载长篇深读正文
- **WHEN** 用户尚未进入详细阅读页
- **THEN** 工作台主视图 MUST 只承担输入、状态反馈和进入阅读的职责
- **THEN** 长篇深读与全文翻译 MUST 在详细阅读视图中展示
