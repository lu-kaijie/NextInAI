## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: 手动 URL 导入 SHALL 识别旧缓存截断与低质量正文
手动 URL 导入在命中已有缓存正文时，MUST 能识别旧版截断正文或低质量正文，并在需要时重新抓取正文。

#### Scenario: 命中旧截断缓存
- **WHEN** 系统命中的旧缓存正文疑似被历史逻辑截断
- **THEN** 系统 MUST 允许重新抓取正文
- **THEN** 成功时 MUST 用新正文覆盖旧缓存
