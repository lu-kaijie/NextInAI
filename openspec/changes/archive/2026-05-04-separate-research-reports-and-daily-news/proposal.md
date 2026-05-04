## Why

当前“报告”能力把长篇研究文章、公司新闻、论坛内容和手动 URL 导入都混在同一个入口里，导致两个问题同时暴露：一是长文调查报告经常只抓到半截正文、没有原始格式，后续深读和全文翻译也跟着失真；二是用户真正想要的“每日 AI 新闻流”并不是点进去再抓，而是应该默认主动展示、快速扫读。现在需要把这两类内容从产品模型上拆开，并把“能否真正读到全文”作为独立能力来修。

## What Changes

- 将现有报告阅读体验拆成两条明确产品线：`调查报告` 和 `每日新闻`。
- 为调查报告新增“全文读取能力评估与恢复”链路，区分旧缓存截断、正文抽取失败、站点限制和网络问题。
- 对长文页面加强正文抽取、整篇翻译和格式保留策略，避免只显示半截正文或只翻译前半段。
- 当系统无法确认拿到完整正文时，禁止生成详细解读，并明确告诉用户原因。
- 新增每日 AI 新闻流能力，默认主动展示来自知名公司、网站和论坛的 AI 新闻条目；每条至少显示标题、来源和简短总结。
- 在 Web 端把“调查报告阅读工作台”和“每日新闻流”分开布局，降低阅读门槛。
- 对 OpenAI 等受限站点增加“失败原因可解释性”，明确是 `403/访问限制` 还是纯抽取失败，而不是模糊地显示“没抓到”。

## Capabilities

### New Capabilities
- `daily-ai-news-stream`: 主动展示面向快讯浏览的每日 AI 新闻流，包含标题、来源和总结。
- `report-fulltext-recovery`: 针对长篇调查报告建立正文完整性判断、重抓、整篇翻译和失败原因评估能力。

### Modified Capabilities
- `url-article-reading`: 手动 URL 阅读结果需要提升为“尽可能读全文、保留格式、支持整篇翻译”，而不是只读部分正文。
- `manual-url-ingestion`: 手动 URL 导入需要区分网络不通、站点限制、旧缓存截断和正文抽取失败等不同失败类别。
- `report-reading-workbench`: Web 端需要把调查报告工作台和每日新闻流区分展示，并在调查报告页显示全文读取状态与失败原因。
- `report-source-expansion`: 来源模型需要区分“调查报告来源”和“每日新闻来源”，而不是继续共用同一套语义。
- `on-demand-deep-report-reading`: 详细解读必须依赖完整正文判断，拿不到全文时不得继续生成深读。

## Impact

- 主要影响 `src/nextinai/collectors/reports.py`、`src/nextinai/services/report_agent.py`、`src/nextinai/web/streamlit_app.py`、`src/nextinai/agents/intelligence.py` 以及来源目录配置。
- 可能需要新增新闻流采集与展示模型，并在本地存储中区分调查报告与每日新闻条目。
- 会调整 Web 信息架构和部分 CLI / service 能力边界，但不会引入数据库。
- 不会承诺所有站点都能稳定拿到全文；对于像 `https://openai.com/index/where-the-goblins-came-from/` 这类当前直连返回 `403` 的页面，系统需要给出明确限制说明。
