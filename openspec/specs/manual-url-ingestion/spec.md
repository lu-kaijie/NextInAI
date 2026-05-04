# manual-url-ingestion

## Purpose
定义用户手动输入文章 URL 时的校验、去重复用与结构化失败反馈能力。

## Requirements

### Requirement: 系统 SHALL 校验并规范化手动输入的文章 URL
系统 MUST 在执行抓取前校验用户输入是否为有效文章 URL，并对 URL 做可重复使用的规范化处理。规范化结果 MUST 可用于缓存命中、去重和后续内容定位。

#### Scenario: 用户提交合法 URL
- **WHEN** 用户输入格式合法的文章 URL
- **THEN** 系统 MUST 接受该输入并生成规范化 URL
- **THEN** 系统 MUST 使用规范化 URL 作为该文章的主识别键之一

#### Scenario: 用户提交非法 URL
- **WHEN** 用户输入空字符串、非 URL 文本或明显不合法的 URL
- **THEN** 系统 MUST 拒绝启动抓取
- **THEN** 系统 MUST 返回明确的校验失败原因

### Requirement: 系统 SHALL 对重复 URL 复用已有抓取与分析结果
系统 MUST 对重复导入的等价 URL 进行去重处理。若规范化 URL 已存在且内容有效，系统 MUST 直接复用已有正文、概览、深读和全文翻译结果，而不是重复生成。

#### Scenario: 规范化 URL 已存在
- **WHEN** 用户提交的 URL 在规范化后命中已有文章记录
- **THEN** 系统 MUST 返回已有文章记录
- **THEN** 系统 MUST 允许直接进入阅读页查看已保存结果

#### Scenario: 文章正文已存在但深读尚未生成
- **WHEN** 已有文章记录包含正文和概览，但没有深度解读
- **THEN** 系统 MUST 复用已有正文和概览
- **THEN** 系统 MUST 仅在用户显式请求时继续生成深度解读

### Requirement: 系统 SHALL 对 URL 导入失败返回结构化原因
当 URL 无法成功导入时，系统 MUST 返回结构化失败原因，至少覆盖输入非法、访问失败、正文为空、正文过短、站点限制和分析生成失败等类型。上层界面 MUST 能直接展示该原因，而不是只看到空白结果。

#### Scenario: 页面访问受限
- **WHEN** 目标页面返回拒绝访问、重定向到登录页或其他站点限制信号
- **THEN** 系统 MUST 将失败原因标记为访问受限或同等语义类别
- **THEN** 上层界面 MUST 能展示该失败原因

#### Scenario: 页面可访问但正文提取失败
- **WHEN** 系统成功请求页面，但无法提取有效正文
- **THEN** 系统 MUST 将失败原因标记为正文为空、正文过短或结构无法解析
- **THEN** 系统 MUST NOT 将该情况静默吞掉

### Requirement: 手动 URL 导入 SHALL 识别旧缓存截断与低质量正文
手动 URL 导入在命中已有缓存正文时，MUST 能识别旧版截断正文或低质量正文，并在需要时重新抓取正文。

#### Scenario: 命中旧截断缓存
- **WHEN** 系统命中的旧缓存正文疑似被历史逻辑截断
- **THEN** 系统 MUST 允许重新抓取正文
- **THEN** 成功时 MUST 用新正文覆盖旧缓存
