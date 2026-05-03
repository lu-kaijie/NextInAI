## Why

当前报告系统仍然依赖“预配置来源 + 自动抓取”这条主路径，一旦某个网站无法稳定抓取、某篇文章没有被来源目录覆盖，用户就没法继续使用解读和全文翻译能力。现在增加“手动输入文章 URL 生成解读与全文翻译”，能把系统从“只能读已接入来源”升级为“能按需读任意指定文章”，显著降低信息获取门槛。

## What Changes

- 新增手动 URL 文章导入能力，允许用户输入单篇文章 URL，并触发正文抓取、解读和全文翻译。
- 新增 URL 直读结果的数据模型与缓存，使同一 URL 的导入、解读和全文翻译可复用。
- 在 Web 报告页增加“手动输入 URL”入口，让用户能直接粘贴文章地址并进入阅读页。
- 对正文抓取失败、正文过短、页面受限或无法解析的 URL 返回明确原因，避免用户只看到“没结果”。
- 复用现有详细阅读页、深度解读和全文翻译体验，而不是为 URL 阅读再造一套独立 UI。

## Capabilities

### New Capabilities
- `url-article-reading`: 支持用户输入任意文章 URL，抓取正文并生成概览、深度解读与全文翻译。
- `manual-url-ingestion`: 定义系统如何校验、抓取、缓存和复用手动输入的文章 URL。

### Modified Capabilities
- `report-reading-workbench`: Web 报告工作台增加手动输入 URL 的入口，并允许用户从 URL 导入结果进入现有阅读流程。

## Impact

- 受影响代码主要在 `src/nextinai/collectors/reports.py`、`src/nextinai/services/report_agent.py`、`src/nextinai/web/streamlit_app.py`、agent 翻译/解读链路以及对应测试。
- 需要新增 URL 导入记录与正文抓取失败原因记录。
- Web 报告页会增加一个新的手动 URL 交互入口，但仍复用现有详细阅读页。
