## 1. Loop 主线重构

- [x] 1.1 清理 `AssistantAgent` 中残留的工具意图推断和业务默认参数注入逻辑，只保留单一 bounded agent loop 主线
- [x] 1.2 为 planner prompt 和工具 schema 补充明确参数约束，确保查询、导出、简报和任务工具由 AI 显式给参
- [x] 1.3 在 loop controller 中补齐统一终止条件，包括最终答复、最大步数、重复调用检测、确认门暂停和不可恢复错误退出
- [x] 1.4 调整 `RunContext`、日志和会话状态记录，使执行标签以 `tool_name` 和工具元数据为主

## 2. Resolver / Validator 工具化

- [x] 2.1 从 assistant 私有规范化逻辑中抽离引用解析职责，新增事件详情和投递任务的 resolver 工具
- [x] 2.2 为导出和简报场景新增目标补全 / 上下文准备类 resolver 工具，返回 planner 可直接复用的结构化结果
- [x] 2.3 在执行层实现本地 deterministic validator，统一处理必填字段、枚举值、副作用确认和执行前约束
- [x] 2.4 让 resolver 或 validator 失败结果能够回写当前 loop，支持 planner 后续修正参数或改调工具

## 3. 入口与工具注册对齐

- [x] 3.1 更新 harness tool registry，暴露新的 resolver/validator 工具及其描述、参数 schema 和返回结构
- [x] 3.2 校准 chat、web、CLI 三个入口对 `AssistantAgent` 的调用方式，确保共用同一 orchestration 行为
- [x] 3.3 清理与旧规范化分支绑定的 helper、日志字段和不可达代码，避免残留双实现

## 4. 测试与验收

- [x] 4.1 重写 assistant 相关单测，按 planner -> tool -> planner 的真实 loop 节奏建模
- [x] 4.2 为 resolver 成功/失败、validator 拦截、重复调用保护、最大步数退出和确认门暂停补充测试
- [x] 4.3 运行 chat/web/CLI 关键路径验收测试，确认查询、追问、导出、订阅和任务删除都走同一条 agent loop
