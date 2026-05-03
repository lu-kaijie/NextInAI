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

