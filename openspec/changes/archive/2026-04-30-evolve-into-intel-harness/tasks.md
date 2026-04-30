## 1. 核心对象与事件模型

- [x] 1.1 定义 `SourceItem`、`IntelligenceEvent`、`AgentRun`、`Briefing`、`DeliveryTask` 的最小字段模型
- [x] 1.2 设计 `IntelligenceEvent` 的类型、归并规则和排序输入字段
- [x] 1.3 设计 event 与原始来源、briefing、delivery 之间的引用关系

## 2. Harness Runtime

- [x] 2.1 设计 `RunContext`、`ToolRegistry`、`SessionState` 和 `ExecutionEngine` 的最小接口
- [x] 2.2 为查询、生成和动作执行定义统一的 tool contract
- [x] 2.3 设计 `AgentRun` 记录结构，覆盖输入、工具调用、输出和错误
- [x] 2.4 明确第一版最小工具集，并逐项映射到现有 service 能力或 adapter 层
- [x] 2.5 定义 `AssistantResponse` 作为 Interaction Layer 的统一响应对象

## 3. AssistantAgent

- [x] 3.1 定义 `AssistantAgent` 的最小意图集合：查询、追问、生成、动作
- [x] 3.2 设计引用解析机制，支持“第 3 个”“刚才那篇报告”“那份简报”等会话引用
- [x] 3.3 设计动作确认流，区分可直接执行与需要确认的操作

## 4. 交付视图

- [x] 4.1 设计快讯版视图结构，明确优先级分层和建议动作输出
- [x] 4.2 设计深读版视图结构，明确上下文、关联与判断边界
- [x] 4.3 设计对话版视图结构，明确 event / briefing / task 的对话引用方式

## 5. 迁移与兼容

- [x] 5.1 明确现有 CLI/service/collector 中哪些能力直接复用，哪些需要重构
- [x] 5.2 设计从“模块输出”向“事件输出”的迁移路径
- [x] 5.3 评估当前文件存储是否足以承载 harness 第一阶段运行记录与事件层数据
- [x] 5.4 设计从现有文本型 service 到结构化 tool output 的 adapter 策略
- [x] 5.5 设计 `events.json`、`session_states.json`、`delivery_tasks.json` 等新增集合及其与现有 JSON 文件的关系
