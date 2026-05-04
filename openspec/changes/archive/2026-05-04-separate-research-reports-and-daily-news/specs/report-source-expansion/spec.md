## MODIFIED Requirements

### Requirement: 系统 SHALL 提供扩展后的默认报告来源目录
系统 MUST 提供比当前更完整的默认 AI 报告来源目录，覆盖 AI 公司、研究组织、开源平台和高价值社区。来源目录 MUST 至少包含来源名称、分组、抓取地址、来源类型和是否默认启用等元数据。

#### Scenario: 默认来源目录可用于初始化展示
- **WHEN** Web 端请求报告来源列表
- **THEN** 系统 MUST 返回扩展后的默认来源目录
- **THEN** 每个来源 MUST 包含可展示的来源名称和所属分组

#### Scenario: 来源目录覆盖多类主体
- **WHEN** 系统初始化默认来源集合
- **THEN** 默认来源 MUST 同时包含公司类来源和社区类来源
- **THEN** 系统 MUST NOT 只保留单一类型来源

## ADDED Requirements

### Requirement: 来源目录 SHALL 区分调查报告来源与每日新闻来源
来源目录 MUST 支持区分“调查报告来源”和“每日新闻来源”，而不是继续把所有来源都挂在同一语义下。

#### Scenario: Web 端请求来源列表
- **WHEN** Web 报告与新闻页面请求可用来源
- **THEN** 系统 MUST 能标记每个来源属于调查报告、每日新闻或两者之一

### Requirement: 每日新闻来源 SHALL 支持默认主动展示
每日新闻来源 MUST 支持作为默认主动展示的新闻流输入，而不要求用户逐个来源手动点击抓取。

#### Scenario: 用户进入每日新闻流
- **WHEN** 用户打开每日新闻流页面
- **THEN** 系统 MUST 能从默认启用的新闻来源中返回最近条目
