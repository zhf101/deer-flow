# 2026-03-24 统一造数平台设计修订清单

## 1. 文档目标

本文档将本轮评审意见转为可执行的设计修订项。

目的不是重复描述评审内容，而是明确：

- 哪些评审结论采纳
- 哪些结论需要修正理解
- 每一项应该补到哪份设计文档
- 每一项需要补充到什么粒度

适用文档：

- [design20260324.md](/D:/code/xagent/spec/design20260324.md)
- [xagent-implementation20260324.md](/D:/code/xagent/spec/xagent-implementation20260324.md)

## 2. 修订原则

### 2.1 采纳原则

以下类型问题直接采纳并补设计：

- 与现有 Xagent 底层强耦合有关的问题
- 影响运行态宿主、追踪、工作区、权限、事务一致性的问题
- 会导致正式执行语义不稳定的问题

### 2.2 修订方式

本轮修订不推翻当前总方案，而是在既有结论上补充：

- 运行时宿主设计
- 桥接层
- 工作区隔离
- 权限实体与鉴权落点
- 资产版本锁定
- 事务边界
- 前端状态宿主
- 展示图与执行图的持久化关系

## 3. 修订项清单

### R1. 明确 `Task` 与 `Run` 的分层宿主关系

#### 评审结论

成立，优先级最高。

#### 问题

当前 Xagent 底层以 `Task` 为一级宿主，但平台执行态又引入了 `Run`，
两者关系必须显式设计。

#### 修订要求

- 明确 `Task` 是探索态 runtime 宿主
- 明确 `Run` 是执行态业务宿主
- 明确 V1 采用“业务上双宿主、基础设施上分层宿主”
- 明确引入 `RunRuntimeBridge`

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R2. 明确 `DAGExecution` 的范围与去留

#### 评审结论

成立。

#### 问题

当前 `DAGExecution` 强绑定 `Task`，而新平台引入 `Run` 后，
必须明确 `DAGExecution` 是继续承担执行态，还是只保留探索态。

#### 修订要求

- 明确 `DAGExecution` 在 V1 只保留探索态用途
- 明确执行态真相源是 `Run / RunStep`
- 不写“立即废弃”，而写“范围收缩与后续迁移评估”

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R3. 补充 TraceEvent / WebSocket 的桥接策略

#### 评审结论

成立。

#### 问题

当前 `TraceEvent` 和 WebSocket 都以 `task_id` 为主键，
新设计中的正式执行以 `run_id` 为主，需要桥接。

#### 修订要求

- 明确 V1 不一步到位改成存储层双宿主
- 明确 V1 消息体与聚合层引入 `run_id`
- 明确执行态页面优先围绕 `Run` 聚合展示
- 明确后续阶段再评估 `TraceEvent` 双宿主化

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R4. 明确 Workspace 隔离策略

#### 评审结论

成立，优先级高。

#### 问题

当前工作区和文件注册逻辑高度 task-centric，
会导致试跑和正式执行产物污染或归属混乱。

#### 修订要求

- 区分 `TaskWorkspace` 与 `RunWorkspace`
- 每个 `Run` 拥有独立隔离工作区
- 试跑和模板正式执行都不能继续混在原探索 workspace 中
- 设计 `RunRuntimeBridge` 的文件输入迁移/挂载策略
- 文件登记与执行产物归属要支持 `run_id`

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R5. 将 `admin_system_scopes` 落成实体设计

#### 评审结论

成立，但属于“概念已定、实体未细化”。

#### 问题

权限概念已在设计中存在，但还没有实体表结构与约束。

#### 修订要求

- 新增 `admin_system_scopes` 实体建议
- 明确主键、唯一键、用户关系
- 明确普通管理员多 scope 绑定方式

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R6. 明确鉴权逻辑的执行层级

#### 评审结论

成立。

#### 问题

目前还未明确基于 `systemShort` 的对象级越权拦截落在哪里。

#### 修订要求

- Middleware 只负责认证与装载用户 scope
- datamakepool service / repository 负责对象级过滤和越权拦截
- API 层不承载复杂业务鉴权

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R7. 明确资产版本锁定时点

#### 评审结论

成立，优先级高。

#### 问题

SQL 资产有审核后生效语义，如果 resolve、preflight、run 创建、执行之间发生资产变更，
必须明确以哪一个版本为准。

#### 修订要求

- 明确真正执行以 `Run` 创建时锁定的资产版本快照为准
- 明确 `RunStep` 保存 `resolved_execution_plan_snapshot`
- 必要时保存 `asset_version_snapshot_ref`
- 明确执行期间不受后续资产切换影响

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R8. 明确事务边界

#### 评审结论

成立，优先级高。

#### 问题

模板草稿生成、资产审核通过、Run 初始化都涉及多表操作，
必须保证事务一致性。

#### 修订要求

- 定义 `FlowDraft -> TemplateRevision + Steps + Schema + Mapping` 单事务
- 定义 SQL 资产审核通过与 current active version 切换单事务
- 定义 `Run + RunStep + 初始审计记录` 单事务初始化

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R9. 明确前端状态宿主

#### 评审结论

合理，属于评审未显式展开但必须补的点。

#### 问题

当前前端是明显 task-centric，新的平台前台需要区分探索态和执行态。

#### 修订要求

- 聊天探索页状态以 `task + flowdraft` 为主
- 运行详情页状态以 `run` 为主
- 前端 store 不再只围绕单一 `task` 组织所有页面

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

### R10. 明确 `business_graph` 的持久化语义

#### 评审结论

这是本轮附加修订项。

#### 问题

需要明确 `business_graph` 是模板版本持久化快照的一部分，
还是完全运行时派生内容。

#### 修订要求

- 建议在 `TemplateRevision` 中也保存 `business_graph` 快照
- 用于展示、审核和 diff
- 不仅依赖 `technical_graph` 运行时派生

#### 落点

- `design20260324.md`
- `xagent-implementation20260324.md`

## 4. 修订优先级

### P0 必补

- R1 `Task / Run` 分层宿主
- R2 `DAGExecution` 范围
- R3 Trace / WebSocket 桥接
- R4 Workspace 隔离
- R7 资产版本锁定
- R8 事务边界

### P1 应补

- R5 `admin_system_scopes` 实体
- R6 鉴权执行层级
- R9 前端状态宿主
- R10 `business_graph` 持久化语义

## 5. 修订完成标准

本轮修订完成后，应至少达到：

- `Task / Run / FlowDraft / TemplateRevision / RunStep` 的关系不再含糊
- 运行时宿主和业务宿主分层明确
- Trace / WS / Workspace 不再仅停留在概念层
- 权限模型不只停留在角色描述，而能落到实体和鉴权执行层
- 事务一致性和版本锁定有明确边界

## 6. 总结

本修订清单的目标不是推翻当前方案，
而是把本轮评审指出的真实集成风险转化为明确设计项，
从而让 `Xagent + datamakepool` 方案从“概念正确”继续走向“实现可落地”。
