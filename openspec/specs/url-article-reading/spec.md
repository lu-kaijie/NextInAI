# url-article-reading

## Purpose
定义单篇文章 URL 导入后的统一阅读、翻译与导出体验。

## Requirements

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

### Requirement: 系统 SHALL 复用现有单篇阅读体验
手动 URL 导入的文章 MUST 复用现有报告阅读工作流，包括详细阅读页、专家带读式深度解读、全文翻译和导出能力。系统 MUST NOT 为 URL 导入文章单独创建一套不兼容的阅读模型。

#### Scenario: URL 导入成功后进入统一阅读页
- **WHEN** 用户成功导入一篇文章 URL
- **THEN** 系统 MUST 将其作为现有阅读工作流中的单篇内容对象处理
- **THEN** 用户 MUST 能从统一阅读页查看概览、触发深读并导出内容

#### Scenario: URL 导入文章可导出
- **WHEN** 某篇通过 URL 导入的文章已经生成概览、深读或全文翻译
- **THEN** 系统 MUST 支持将相应内容导出为 Markdown 和 PDF

### Requirement: 系统 SHALL 支持单篇文章全文翻译
对于通过 URL 导入并成功抓取正文的文章，系统 MUST 支持生成面向中文读者的全文翻译。若原文已经是中文，系统 MUST 直接保留原文，不得额外生成生硬的伪翻译文本。

#### Scenario: 英文文章生成中文全文翻译
- **WHEN** 用户查看一篇英文文章的全文翻译
- **THEN** 系统 MUST 输出完整、连贯、适合阅读的中文全文翻译
- **THEN** 翻译结果 MUST 与原文正文结构基本对应，而不是退化为摘要

#### Scenario: 中文文章保留中文正文
- **WHEN** 用户导入一篇原文即为中文的文章
- **THEN** 系统 MUST 将中文正文直接作为可阅读正文展示
- **THEN** 系统 MUST NOT 额外生成内容失真的重复翻译

### Requirement: 手动 URL 阅读 SHALL 暴露正文完整性状态
手动 URL 阅读结果 MUST 向上层暴露正文完整性状态，至少能区分完整正文、部分正文、站点限制和抓取失败。

#### Scenario: 用户查看 URL 导入结果
- **WHEN** 用户打开一篇通过 URL 导入的文章
- **THEN** 系统 MUST 能告诉用户正文是否完整
- **THEN** 若正文不完整，系统 MUST 提供明确状态而不是只显示半截正文
