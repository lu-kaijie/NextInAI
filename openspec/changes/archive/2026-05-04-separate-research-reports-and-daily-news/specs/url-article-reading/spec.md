## MODIFIED Requirements

### Requirement: 系统 SHALL 支持按单篇 URL 生成文章阅读结果
系统 MUST 允许用户输入单篇文章 URL，并基于该 URL 生成可阅读的文章结果。阅读结果 MUST 至少包含标题、来源 URL、正文内容、概览摘要，并能够继续进入深度解读和全文翻译流程。

#### Scenario: 用户提交可访问文章 URL
- **WHEN** 用户输入一个可访问且可解析正文的文章 URL
- **THEN** 系统 MUST 抓取该文章标题、规范化 URL 和正文内容
- **THEN** 系统 MUST 为该文章生成概览摘要
- **THEN** 系统 MUST 允许该文章继续进入深度解读和全文翻译流程

#### Scenario: 用户再次打开同一篇已导入文章
- **WHEN** 用户再次提交同一篇文章的等价 URL
- **THEN** 系统 MUST 优先复用已存在的文章结果
- **THEN** 系统 MUST NOT 强制重新抓取和重新生成全部分析内容

## ADDED Requirements

### Requirement: 手动 URL 阅读 SHALL 暴露正文完整性状态
手动 URL 阅读结果 MUST 向上层暴露正文完整性状态，至少能区分完整正文、部分正文、站点限制和抓取失败。

#### Scenario: 用户查看 URL 导入结果
- **WHEN** 用户打开一篇通过 URL 导入的文章
- **THEN** 系统 MUST 能告诉用户正文是否完整
- **THEN** 若正文不完整，系统 MUST 提供明确状态而不是只显示半截正文
