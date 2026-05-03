## ADDED Requirements

### Requirement: Web 报告页 SHALL 使用卡片化工作台展示最近报告
Web 报告页 MUST 使用非表格化的卡片工作台展示最近报告。每条报告 MUST 以独立卡片呈现标题、来源、发布时间、概览摘要、状态和主要操作入口。

#### Scenario: 最近报告不再以表格主视图呈现
- **WHEN** 用户打开 Web 报告页的“最近报告”区域
- **THEN** 系统 MUST 以卡片化布局展示报告列表
- **THEN** 主视图 MUST NOT 以 `st.dataframe` 形式直接呈现报告集合

#### Scenario: 报告卡片展示关键概览信息
- **WHEN** 用户浏览某一条报告卡片
- **THEN** 卡片 MUST 展示标题、来源、发布时间和概览摘要
- **THEN** 卡片 MUST 提供查看链接或进入详细动作的入口

### Requirement: Web 报告页 SHALL 隐藏内部标识字段
Web 报告页 MUST NOT 直接向用户展示 `report_id`、去重指纹或其他内部存储标识。用户可见层只能显示对阅读有意义的业务字段。

#### Scenario: 最近报告区域不显示 report_id
- **WHEN** 用户浏览最近报告列表或单篇详情
- **THEN** 页面 MUST NOT 显示 `report_id` 字段
- **THEN** 内部标识仅可作为系统内部操作参数存在

### Requirement: 报告概览 SHALL 支持展开、折叠和并排浏览
报告工作台 MUST 支持用户对单篇报告进行展开/折叠，并允许多条报告在桌面端并排浏览，以提升快速对比和扫读效率。

#### Scenario: 用户展开单篇概览
- **WHEN** 用户点击某一条报告卡片的展开入口
- **THEN** 系统 MUST 展示该卡片的更多概览信息
- **THEN** 展开行为 MUST NOT 强制替换掉整页报告列表

#### Scenario: 用户并排浏览多条报告
- **WHEN** 页面在桌面宽度下展示多条报告
- **THEN** 系统 MUST 允许多条卡片并排布局
- **THEN** 用户 MUST 能在不切换页面的前提下连续浏览多条候选报告

### Requirement: 概览摘要 SHALL 与深读职责分离
报告工作台中的 summary MUST 表示“快速概览”，而不是完整深度解读。页面 MUST 将概览摘要和后续深读入口明确区分。

#### Scenario: 概览只用于快速判断是否值得深入
- **WHEN** 用户浏览报告卡片中的 summary
- **THEN** 该内容 MUST 用于说明报告主题、核心结论或值得关注的点
- **THEN** 它 MUST NOT 假装替代完整深度带读

#### Scenario: 深读入口独立于概览摘要
- **WHEN** 用户想查看更长、更细的解读
- **THEN** 页面 MUST 提供单独的“生成详细解读”或同等语义入口
- **THEN** 系统 MUST 将该入口与概览摘要展示分离

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
