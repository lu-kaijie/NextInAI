# 决策记录

本文档用于记录 NextInAI 在需求、架构和产品方向上的关键决策，保留“为什么这样做”的上下文，避免只剩结果没有过程。

## 2026-04-30 - 从 CLI 工具集升级为情报 Harness

背景：
当前项目已经初步完成 CLI 版 GitHub 订阅、热门项目、报告抓取、digest 导出与通知能力，但产品形态仍偏“命令集合”。后续讨论中明确，目标不是继续堆叠更多 CLI 命令，而是演进为一个常驻、可对话、可行动、可定时运行的情报型 agent。

决策：
- 项目从“CLI-first 工具集”升级为“面向 AI 情报场景的 agent harness”。
- CLI 保留为工具入口，但不再被视为产品本体。
- 后续将新增常驻对话式 `AssistantAgent`，支持自然语言查询、继续追问、生成简报和执行动作。

原因：
- 单次 CLI 交互不足以体现 agent 的持续追踪和主动交付价值。
- 若只做自然语言壳层，很容易被通用 coding agent + skill 替代。
- 真正差异化来自持续追踪、跨来源去重、重要性排序和主动交付，而不是“也能聊天”。

影响：
- 后续设计需要围绕 harness runtime 展开，而不是继续围绕零散命令扩展。
- 对话入口、调度入口和未来 Web 入口应复用同一套 runtime 与核心对象模型。

后续动作：
- 新建 OpenSpec change：`evolve-into-intel-harness`
- 定义核心对象、AssistantAgent 工作流和交付视图

## 2026-04-30 - 核心差异化聚焦持续追踪与情报判断

背景：
讨论“为什么用户不直接用 Claude Code / Codex + skill”时发现，若产品只提供查询、总结和发送动作，差异化不足。

决策：
- 核心差异化聚焦两个能力：
  - 持续追踪与增量情报
  - 跨来源去重与重要性排序

原因：
- 通用 agent 更擅长“一次性解决问题”，不擅长“持续盯盘”。
- 用户真正缺的不是更多搜索结果，而是更少噪音、更强优先级判断和更稳定的主动交付。

影响：
- 后续能力设计应优先支持 event 归并、排序、连续观察和推送抑制。
- 热门榜、仓库更新和报告解读都应逐步汇聚到统一情报对象层。

## 2026-04-30 - 核心运行对象采用领域建模

背景：
在讨论 harness 架构时，需要先定义系统最小对象集合，否则后续 runtime、对话和交付层会缺少稳定边界。

决策：
- 第一版核心对象采用以下 5 个：
  - `SourceItem`
  - `IntelligenceEvent`
  - `AgentRun`
  - `Briefing`
  - `DeliveryTask`

原因：
- `SourceItem` 代表采集层原始输入
- `IntelligenceEvent` 代表归并后的事件级情报
- `AgentRun` 支撑 observability 和 replay
- `Briefing` 代表用户可读产物
- `DeliveryTask` 代表主动交付和定时任务

影响：
- 后续任何新需求都应优先判断自己属于采集层、认知层、运行层、阅读层还是交付层。

## 2026-04-30 - `IntelligenceEvent` 作为系统核心认知对象

背景：
如果系统直接围绕原始 feed、commit、release 和 trending 项目输出，最终会退化成流水账。

决策：
- `IntelligenceEvent` 定义为：
  - 由一个或多个 `SourceItem` 归并而成
  - 能代表一件值得关注的新增变化、热度信号或认知判断
  - 必须对用户的信息判断产生新增价值

原因：
- 用户要的是“今天最该看什么”，不是“今天收到了哪些原始条目”。
- event 层是去重、排序、对话和推送统一依赖的中心对象。

影响：
- 后续仓库更新、热门榜和报告解读都应逐步汇聚到 event 层。

## 2026-04-30 - 同一事件的归并规则采用保守策略

背景：
跨来源去重是产品价值核心，但过度归并会比漏归并更伤害可信度。

决策：
- 第一版归并优先采用：
  - 同对象
  - 同核心变化/主题
  - 时间窗口接近
- 高置信才自动合并，低置信先保留分离或只建立“相关”关系。

原因：
- 漏合并最多造成少量重复，错合并会直接破坏用户信任。

影响：
- 归并动作本身后续应带 `merge_confidence`
- 低置信相似内容不应强行合并为同一 event

## 2026-04-30 - 排序目标不是复现热度，而是最大化新增价值

背景：
如果热门榜和简报只按热度排序，产品会退化成 Trending 重述器。

决策：
- `IntelligenceEvent` 排序优先级采用：
  - 新增信息强度
  - 用户相关性
  - 影响范围
  - 持续热度/信号强度
  - 可信度

原因：
- “最火”不等于“最值得看”
- 情报产品真正价值在于注意力分配，而非复刻全网排名

影响：
- 后续快讯版和深读版都应由同一套优先级结果派生

## 2026-04-30 - 交付采用快讯版 / 深读版 / 对话版三种视图

背景：
同一套情报既要支持快速扫读，也要支持深度理解和多轮追问。

决策：
- 同一套 `IntelligenceEvent` 支持三种交付视图：
  - 快讯版
  - 深读版
  - 对话版

原因：
- 快讯用于注意力分配
- 深读用于建立理解
- 对话用于继续追问和执行动作

影响：
- 后续 `Briefing` 需要区分输出形态
- AssistantAgent 需要优先围绕 event 层展开追问

## 2026-04-30 - Harness runtime 自研，LangChain 不作为核心骨架

背景：
讨论是否应引入 LangChain 等框架实现 agent 时，需要先明确框架在项目中的角色边界。

决策：
- 核心 harness runtime 自研
- 领域对象自研
- OpenAI SDK 继续直连
- LangChain / LangGraph 若后续引入，也仅作为局部编排插件，不主导核心结构

原因：
- 当前复杂度主要在持续追踪、事件归并、排序、交付和 observability，不在 prompt 链本身。
- 过早引入框架容易让领域模型反过来被框架抽象绑架。

影响：
- 后续应先定义 runtime、tool registry、session state 和 agent run 结构
- 是否引入 LangChain，只在 AssistantAgent 复杂度明显上升时再评估

## 2026-04-30 - 第一版工具集围绕用户意图而不是 service 名字设计

背景：
在定义 `AssistantAgent` 的最小工作流后，需要决定第一版 `ToolRegistry` 中到底暴露哪些能力，以及这些能力是否能直接复用现有代码。

决策：
- 第一版工具分为查询类、生成类和动作类三组
- tool 的命名围绕用户意图，例如 `get_trending_events`、`generate_briefing`、`deliver_briefing`
- 不直接把现有 CLI service 名字原样暴露给 `AssistantAgent`

原因：
- 现有 service 大多返回面向终端的文本，而不是 event / briefing / task 级结果
- 如果直接暴露现有 service，会让对话层继续耦合 CLI 风格输出

影响：
- 需要增加一层 adapter，将现有 service 结果提升为结构化 tool output
- 第一版可直接复用的能力主要是 `add_subscription`、`generate_briefing` 和 `deliver_briefing`
- trending / repo summary / report fetch 等能力都需要 event 适配后再进入 `ToolRegistry`

## 2026-04-30 - 默认采用自主推进协作模式

背景：
随着主线切换到 `evolve-into-intel-harness`，项目进入持续设计与逐步重构阶段。如果每推进一步都等待人工确认，会显著打断节奏。

决策：
- 默认采用自主推进模式：
  - 分析、设计、文档更新、代码实现、本地测试、OpenSpec 更新可直接连续推进
  - 以后默认围绕 `evolve-into-intel-harness` 主线继续收敛与实现
- 仅在以下情况需要停下确认：
  - 外部副作用动作：发邮件、发 webhook、创建/删除定时任务、推送 GitHub
  - 破坏性动作：删除大量数据、重置状态、回滚关键改动
  - 明显存在多条产品路线且影响较大时
  - 权限、网络或外部信息不足时

原因：
- 当前阶段更需要连续推进和留痕，而不是频繁中断
- 主线方向已经明确，剩余工作更适合自主拆解并持续推进

影响：
- 后续若无高风险动作，将默认不逐条等待人工确认
- 决策、设计和实现推进过程应继续沉淀到 OpenSpec 与本决策文档

## 2026-04-30 - Harness runtime 先以 5 个最小接口落地

背景：
在确认项目主线切换到 `evolve-into-intel-harness` 后，需要决定 runtime 从哪里开始收敛，避免一上来就过度设计。

决策：
- 第一版 harness runtime 先定义 5 个最小接口：
  - `RunContext`
  - `Tool`
  - `ToolRegistry`
  - `SessionStateStore`
  - `ExecutionEngine`
- 同时定义一个统一的 `AssistantResponse` 供交互层消费

原因：
- 这套接口已经足以支撑查询、追问、生成预览、确认执行和运行记录
- 再继续扩展复杂 planner / memory / graph 前，先把最小可运行骨架定住更稳

影响：
- 后续实现 `nextinai chat` 时，应优先围绕这些接口搭建
- 现有 CLI/service 层需要通过 adapter 接到 tool contract，而不是直接暴露给对话层

## 2026-04-30 - 文件存储继续沿用，但补齐事件层与会话层集合

背景：
当前仓库已经使用本地 JSON 文件保存订阅、原始内容、分析结果、digest 和投递记录，需要判断这套存储是否足以承接 harness 第一阶段。

决策：
- 继续沿用本地文件存储作为第一阶段落盘方案
- 在现有集合基础上新增：
  - `events.json`
  - `session_states.json`
  - `delivery_tasks.json`
- `job_runs.json` 逐步扩展为更通用的 `AgentRun` 记录集合

原因：
- 当前阶段面向个人使用，本地 JSON 仍然最轻、最可控
- 在尚未需要多用户和复杂查询前，引入数据库收益不高

影响：
- 现有 `content_items`、`digests`、`deliveries` 等集合仍可复用
- 事件层和会话层落地后，系统可逐步从“CLI 输出驱动”迁移到“runtime 对象驱动”

## 2026-04-30 - 现有 CLI 保留，但降级为薄壳入口

背景：
随着 harness 方向明确，需要判断已经做出来的 CLI 是否应继续保留，还是直接废弃。

决策：
- 保留现有 CLI
- 但将其角色明确降级为：
  - 调试与验收入口
  - 底层能力的稳定壳
  - harness 故障时的降级模式
- 后续新能力优先实现到 harness runtime / tool layer，而不是继续把 CLI 当主线扩张

原因：
- 现有 CLI 已经能直接验证 GitHub 订阅、热门榜、报告抓取、digest 和通知链路
- 如果完全删除 CLI，会失去非常直接的回归测试和人工排障入口
- 让 CLI 变薄，而不是变重，更符合后续 chat shell / web 复用同一 runtime 的目标

影响：
- 现有 CLI 继续保留，不主动破坏
- 新的 agent 能力应通过 adapter 接入 tool registry，再由 CLI 或 chat 复用

## 2026-05-01 - 功能同步以 capability 为中心，而不是要求传统 CLI 全量对齐

背景：
随着 `chat` 和 `web` 逐渐成为主交互入口，一个自然问题是：每次新增能力后，是否都需要同步补一套传统 CLI 参数命令。

决策：
- 功能同步遵循以下顺序：
  - 先实现到 `service / capability`
  - 再接入 `chat`
  - 再接入 `web`
  - 传统 CLI 只补高价值、适合脚本化和批处理的入口
- 不要求传统 CLI 与 `chat / web` 保持机械式全量对齐

原因：
- 很多能力天然依赖上下文，例如“展开上一条报告”“把刚才那份结果导出 PDF”“把这份分析发到邮箱”，这类流程放到 `chat` 或 `web` 中更自然
- 如果强行把这些能力全部翻译成传统 CLI 参数，命令会越来越长，交互体验和可维护性都会变差
- 真正需要统一的是底层能力边界，而不是每个入口表面上都长得一样

影响：
- `chat` 与 `web` 需要尽量共享完整能力面
- 传统 CLI 继续作为脚本入口、验收入口和故障降级入口存在
- 后续架构工作应优先推进统一 capability 层，而不是继续堆叠 CLI 子命令

## 2026-05-02 - Chat 改为单路径 Agent Loop，不再保留关键词 fallback

背景：
在继续推进 `AssistantAgent` 时确认，若同时保留“LLM planner + 关键词规则 fallback”两套判定逻辑，会长期增加复杂度，并弱化项目作为 agent harness 的定位。

决策：
- `chat` 改为单路径 agent loop
- 工具选择由模型负责
- 不再保留关键词意图路由 fallback
- 不再为同一交互能力维护“planner 一套、规则一套”的双轨逻辑

原因：
- 双轨逻辑会让系统表面上像 agent，底层却仍是命令匹配器
- 复杂度更高，调试边界更模糊，后续扩展成本也更差
- 当前项目更适合把唯一主路径做好，而不是靠备用路径掩盖主路径问题

影响：
- `AssistantAgent` 在未配置可用 AI planner 时，将直接提示不可调度，而不是退回硬编码规则
- 剩余文本规则只用于参数校验、引用解析和确认流，不再决定“该调用哪个工具”
- 后续优化重心从“补更多关键词”转向“收敛 tool schema、capability 层和 loop 稳定性”

## 2026-04-30 - AssistantAgent 采用受控式意图路由，而不是自由代理

背景：
在真正开始实现常驻交互入口时，需要决定 `AssistantAgent` 是走开放式自由推理，还是走受控工具编排。

决策：
- 第一版 `AssistantAgent` 采用受控式路由
- 意图固定为 4 类：
  - `query_intelligence`
  - `explore_detail`
  - `generate_briefing`
  - `execute_action`
- 多轮交互依赖 `SessionState` 做引用解析
- 所有带副作用的动作继续要求确认后执行

原因：
- 当前项目的核心价值在持续追踪、事件编排和稳定交付，不在开放式 agent 自由发挥
- 受控路由更容易调试、测试和逐步扩展
- 现阶段比起“更聪明”，更需要“更稳、更可控”

影响：
- `AssistantAgent` 会优先围绕 tool registry 工作，而不是直接拼 prompt 做全能问答
- 后续若引入更复杂 planner，也应建立在当前受控 contract 之上

## 2026-04-30 - 第一版 chat shell 先走 CLI 常驻会话模式

背景：
既然产品主线已经从工具集转向 harness，就需要一个真正可交互的入口，而不只是单次命令。

决策：
- 第一版交互入口先以 `nextinai chat` 落地
- 支持：
  - 单轮消息模式
  - 常驻 REPL 会话模式
  - 会话状态持久化
  - 引用上一轮结果继续追问

原因：
- 这是验证 runtime、session state、confirmation flow 和 tool routing 是否真正闭环的最短路径
- 比起直接上 Web，这一层更容易快速迭代和压实抽象边界

影响：
- CLI 不再只是“命令菜单”，开始承担 chat shell 角色
- 后续 Web/API 应复用相同的 `AssistantAgent` 和 runtime，而不是重写一套逻辑

## 2026-04-30 - Briefing 统一扩展为快讯 / 深读 / 对话三种视图

背景：
仅有快讯版虽然能解决“先看什么”，但还不能很好承接“为什么值得看”“接下来怎么问/怎么做”。

决策：
- `BriefingViewBuilder` 统一支持三种视图：
  - `flash`
  - `deep`
  - `conversation`
- `generate_briefing` / `render_briefing_preview` tool 增加 `view` 参数
- `AssistantAgent` 可根据自然语言直接生成深读简报或对话视图

原因：
- 三种视图共享同一组 `IntelligenceEvent`，这是 harness 的核心复用价值
- 先把视图层抽象统一，后面无论 CLI、chat 还是 Web 都能复用同一个 briefing contract

影响：
- `nextinai chat` 不再只能返回快讯，还可以直接生成深读/对话简报
- 后续 PDF、邮件、Webhook 发送也可以围绕统一 `Briefing` 视图选择扩展

## 2026-04-30 - digest 主链开始从模块拼接迁移到事件视图驱动

背景：
原先的 digest 主要是“仓库更新一段、热门榜一段、报告一段”的模块式拼接，这更像旧 CLI 时期的产物。

决策：
- 现阶段不推翻旧模块段落，但在 digest 顶部新增“事件快讯视图”
- 该视图由 `IntelligenceEventAdapter + BriefingViewBuilder` 生成
- 原有 repo/trending/report 三段继续保留，作为兼容和过渡层

原因：
- 这样可以最小代价验证从“模块输出”向“事件输出”的迁移路径
- 不会一下子打断现有 CLI 用户的认知和测试基线

影响：
- digest 已经开始复用 harness event layer
- 后续可以逐步减少旧模块段落的主导地位，最终让 briefing 成为真正的交付核心

## 2026-04-30 - DeliveryTask 先以本地轮询调度落地

背景：
在任务系统已经支持创建、查询和删除之后，还需要决定第一版“主动推送”到底如何真正执行。

决策：
- 第一版 `DeliveryTask` 先采用本地轮询执行模型
- 增加 `DeliveryTaskScheduler.run_due_tasks()`
- 调度频率先收敛为：
  - `hourly`
  - `daily`
  - `weekly`
- CLI 提供 `nextinai task list` 和 `nextinai task run-due`

原因：
- 当前是个人使用场景，本地轮询比引入常驻守护进程、系统服务或复杂 APScheduler 编排更轻
- 先把“任务可执行”闭环打通，比一上来追求复杂调度形态更重要

影响：
- `DeliveryTask` 已经从静态配置升级为可执行对象
- 后续如果需要常驻后台运行，可以在当前任务语义之上替换执行器，而不必重做任务模型

## 2026-04-30 - 通知发送开始支持 Briefing 视图选择

背景：
如果通知层始终只会发送旧式 digest，那么前面已经建立的 `flash/deep/conversation` 视图价值就落不到主动交付链路里。

决策：
- `NotificationService.send()` 增加 `briefing_view`
- `flash` 继续优先复用已有 digest
- `deep/conversation` 则直接基于 `generate_briefing()` 按视图实时生成内容后发送

原因：
- 这样能在不破坏旧 digest 导出链路的前提下，把新视图能力接入外发链路
- “发送什么视图”应是交付层的一等参数，而不是隐藏实现细节

影响：
- 任务调度和手动通知都可以明确指定发送快讯版还是深读版
- 后续若要支持不同渠道不同视图，这个接口已经有承载位

## 2026-04-30 - 主动交付默认启用重复发送抑制

背景：
当系统开始支持常驻轮询和自动推送后，如果同一内容在短时间内反复发送，会迅速损伤可用性。

决策：
- 对 `DeliveryTaskScheduler` 触发的主动通知，默认启用重复发送抑制
- 抑制依据为：
  - 同渠道
  - 同目标
  - 同 `content_hash`
  - 在配置时间窗口内已有成功发送记录
- 被抑制的动作仍记录到 `deliveries.json`，状态为 `suppressed`

原因：
- 情报系统的价值是减少噪音，而不是稳定重复提醒同一内容
- 即使不发送，也需要留痕，便于后续审计和调试

影响：
- 主动交付链路已经具备基本“抗重复”能力
- 后续可以继续扩展更细粒度的 suppression rule，而不必推翻当前记录结构

## 2026-04-30 - DeliveryTask 失败后采用本地回退重试

背景：
如果任务执行失败后必须等到下一个 daily/weekly 窗口再试，主动交付链路的鲁棒性会明显不足。

决策：
- 任务失败后在 `delivery_tasks.json` 的 `metadata` 中记录：
  - `consecutive_failures`
  - `last_error`
  - `next_retry_at`
- 第一版回退策略：
  - 第 1 次失败后 15 分钟重试
  - 之后按失败次数递增，最高回退到 60 分钟

原因：
- 本地回退策略实现简单，但已经足够覆盖大多数短暂 SMTP/Webhook 故障
- 在个人使用场景下，这比引入复杂队列和分布式重试更符合阶段目标

影响：
- 主动交付不再完全依赖原始 schedule 周期
- 后续如果引入更复杂的执行器，也应继续复用这些失败元数据语义

## 2026-04-30 - 常驻运行模式先以本地轮询 daemon 落地

背景：
为了让 harness 真正“持续运行”，仅靠手动执行 `task run-due` 还不够。

决策：
- 提供 `nextinai task daemon`
- 它基于本地轮询循环运行
- 支持：
  - `poll_seconds`
  - `max_cycles`
  - `force_first_cycle`

原因：
- 这是最轻量、最容易部署和验证的持续运行方式
- 比起先上系统服务或容器编排，本地 daemon 更适合当前个人使用场景

影响：
- 项目已经具备最小常驻运行形态
- 后续如果上 systemd、supervisor、Docker 或 Web 后台任务，只需替换外层运行包装，不必重写调度语义
