# 2026-03-24 基于 Xagent 的统一造数平台实现设计

## 1. 文档目标

本文档是 [xagent20260324.md](/D:/code/xagent/spec/xagent20260324.md) 的实现展开版。

本文档重点回答：

- 应该新增哪些模块
- 统一业务 DAG 应该如何建模
- 五层视图如何落到前后端
- `http_step` / `sql_step` 的 Resolver / Executor 契约如何定义
- 聊天探索、重收敛、预检、试跑、模板沉淀如何串起来

本文档不展开：

- 详细数据库字段到最终 SQL DDL
- 所有接口的完整 OpenAPI
- 详细任务排期

## 2. 总体落点

### 2.1 代码落点建议

建议采用以下结构：

```text
src/xagent/
├── core/
│   └── datamakepool/
│       ├── contracts/
│       ├── flowdraft/
│       ├── templates/
│       ├── runs/
│       ├── assets/
│       ├── governance/
│       ├── resolvers/
│       │   ├── http/
│       │   └── sql/
│       ├── executors/
│       │   ├── http/
│       │   └── sql/
│       └── orchestration/
└── web/
    ├── api/
    │   └── datamakepool/
    └── services/
```

前端建议新增：

```text
frontend/src/
├── app/datamakepool/
│   ├── chat/
│   ├── templates/
│   ├── runs/[id]/
│   └── audit/
├── components/datamakepool/
│   ├── flowdraft/
│   ├── preflight/
│   ├── trial/
│   └── diff/
└── lib/datamakepool/
```

### 2.2 层次边界

#### Xagent 层

负责：

- 聊天入口
- 多轮澄清
- FlowDraft 可视化
- WebSocket 过程回传
- 探索态交互

#### datamakepool 层

负责：

- 统一业务 DAG 模型
- 资产、模板、Run、审计
- Resolver / Executor
- SQL 风险与确认
- 模板草稿与版本

### 2.3 运行时宿主策略

V1 推荐采用：

```text
业务上双宿主
基础设施上分层宿主
```

也就是：

- `Task` 继续作为探索态 runtime 宿主
- `Run` 作为执行态业务宿主
- 中间通过 `RunRuntimeBridge` 连接

#### `Task` 在实现中的职责

- chat transcript
- `DAGExecution`
- `TraceEvent`
- `TaskWorkspace`
- 探索态 WebSocket 通道

#### `Run` 在实现中的职责

- `Run`
- `RunStep`
- `AuditRecord`
- 正式执行状态与结果
- 运行详情页

#### `DAGExecution` 的实现范围

V1 建议：

- `DAGExecution` 只保留探索态用途
- 正式执行态真相源迁到 `Run / RunStep`

#### `RunRuntimeBridge`

建议新增桥接模块：

```text
src/xagent/core/datamakepool/orchestration/run_runtime_bridge.py
```

至少承担：

- `task_id <-> run_id` 映射
- 从 task runtime 投影 `RunStep`
- 聚合 trace 到 run 视图
- 关联 run 产物与 workspace

### 2.4 Trace / WebSocket 过渡策略

V1 不建议立刻重写底层 trace 存储模型。

建议：

- `TraceEvent` 存储层暂时仍以 `task_id` 为主
- 运行态消息与聚合结果带 `run_id`
- 运行详情页优先读取 run 聚合视图
- 第二阶段再评估 `TraceEvent` 双宿主化

### 2.5 Workspace 隔离策略

必须区分：

- `TaskWorkspace`
- `RunWorkspace`

建议新增：

```text
src/xagent/core/datamakepool/runs/run_workspace.py
```

规则：

- 探索态只用 `TaskWorkspace`
- 每个 `Run` 拥有独立 `RunWorkspace`
- trial run 和 template run 都各自隔离
- 产物归属必须能挂到 `run_id`

桥接层负责：

- 将探索态输入迁移或挂载到 `RunWorkspace`
- 将执行输出回填 run 产物目录

### 2.6 权限实体与鉴权层级

建议新增：

```text
src/xagent/web/models/admin_system_scope.py
```

建议结构：

- `id`
- `user_id`
- `system_short`
- `created_at`

建议 `(user_id, system_short)` 唯一。

权限执行层级建议：

- middleware / dependency
  - 认证
  - 装载用户 scope
- datamakepool service / repository
  - 对象级过滤与越权拦截
- API
  - 不承载复杂业务鉴权

## 3. 统一业务 DAG 模型

### 3.1 根对象

统一业务 DAG 以 `FlowDraft` 为根对象。

建议结构：

```text
FlowDraft
├── metadata
├── business_graph
├── technical_graph
├── pending_issues
├── preflight_summary
├── snapshots
└── linkage
```

### 3.2 `FlowDraft` 最小结构

建议 `FlowDraft` 至少包含：

- `id`
- `conversation_session_id`
- `status`
- `title`
- `objective`
- `business_graph`
- `technical_graph`
- `pending_issues`
- `preflight_summary`
- `latest_snapshot_id`
- `created_by`
- `created_at`
- `updated_at`

### 3.2.1 `business_graph` 的持久化

`business_graph` 不建议只做运行时派生。

建议在以下层次都持久化：

- `FlowDraft`
- `FlowDraftSnapshot`
- `TemplateRevision`

用于：

- 展示
- 审核
- diff

### 3.3 两层图结构

#### `business_graph`

面向主视图，表达：

- 业务意图节点
- 业务依赖关系
- 节点摘要
- 风险/确认摘要

#### `technical_graph`

面向技术实现图，表达：

- `http_step`
- `sql_step`
- `confirm`
- `mapping`
- `start`
- `end`

以及它们之间的依赖关系。

### 3.4 技术节点公共结构

所有技术节点至少包含：

- `step_id`
- `step_type`
- `name`
- `depends_on`
- `status`
- `design_intent`
- `resolution_rationale`
- `resolved_execution_plan`
- `editable_fields`
- `pending_flags`
- `latest_trial_result_ref`

### 3.5 `http_step`

建议 `http_step` 至少包含：

- `asset_id`
- `asset_version_ref`
- `param_template`
- `param_sources`
- `default_values`
- `default_value_sources`
- `request_shape`
- `extract_rules`
- `output_mapping`
- `runtime_config`

### 3.6 `sql_step`

建议 `sql_step` 至少包含：

- `asset_id`
- `asset_version_ref`
- `sql_template`
- `param_template`
- `output_fields`
- `sql_lane`
- `risk_level`
- `requires_confirmation`
- `target_objects`
- `governance_check_result`
- `reference_bindings`
- `allowed_mutation_boundary`
- `runtime_config`

## 4. 五层视图落地

### 4.1 `FlowDraftGraph`

前端主图组件建议：

- `FlowDraftBusinessGraph`
- `FlowDraftTechnicalGraph`

功能：

- 默认展示业务意图图
- 用户可切换技术实现图
- 节点点击后联动右侧详情

### 4.2 `FlowStepDesign`

右侧详情面板建议按三段组织：

1. 资产与参数
2. 执行语句与提取规则
3. 风险与影响

并根据 `editable_fields` 决定：

- 哪些字段直接可编辑
- 哪些字段需要重收敛

### 4.3 `PreflightCheckView`

建议作为聊天页内独立区域或抽屉。

至少支持：

- 按问题类型分组
- 按步骤分组
- 默认按问题类型分组
- 每个问题给出推荐修正路径

### 4.4 `TrialExecutionDetail`

建议支持两层：

- 整体试跑概览
- 单步执行详情

HTTP 节点展示：

- request snapshot
- response snapshot
- extracted outputs

SQL 节点展示：

- sql snapshot
- bound params
- result snapshot
- extracted outputs
- audit summary

### 4.5 `ToolTraceView`

建议默认折叠。

面向：

- 研发
- 排障
- 高级管理员

展示：

- resolver 内部过程摘要
- executor 内部 agent/tool 调用轨迹

## 5. 探索态与重收敛流程

### 5.1 初版生成

主链：

```text
用户输入目标
  ↓
Lead 生成初版 FlowDraft
  ↓
展示业务意图图 + 待确认项
```

### 5.2 修正路径

默认修正路径：

- 方案问题 -> 回聊天修正
- 配置问题 -> 去节点详情修正

### 5.3 重收敛策略

支持：

- 局部重收敛
- 全量重收敛

默认：

- 局部重收敛

建议全量重收敛的场景：

- 改了上游关键节点
- 改了资产
- 改了 SQL 主体
- 改了全局输入 schema

### 5.4 关键版本快照

建议新增 `FlowDraftSnapshot`：

- `snapshot_id`
- `flowdraft_id`
- `snapshot_type`
- `business_graph_snapshot`
- `technical_graph_snapshot`
- `preflight_summary_snapshot`
- `created_at`
- `created_by`

关键快照点：

- 初版生成后
- 每次重收敛后
- 进入试跑前
- 试跑成功后

### 5.6 前端状态宿主

前端建议拆分两类状态模型：

#### 探索态 store

围绕：

- `task`
- `flowdraft`
- `preflight`

#### 执行态 store

围绕：

- `run`
- `run_steps`
- `audit_summary`

不建议继续用单一 task-centric store 覆盖全部页面。

### 5.5 Diff

建议新增两个 diff 计算器：

- `BusinessGraphDiffBuilder`
- `TechnicalGraphDiffBuilder`

默认展示：

- business diff

可下钻：

- technical diff

## 6. Preflight 预检机制

### 6.1 预检目标

判断当前 `FlowDraft` 是否从探索态进入可试跑态。

### 6.2 预检输入

建议输入：

- 最新 `technical_graph`
- 最新 pending flags
- 最新 resolver 输出
- governance 校验结果

### 6.3 预检输出

建议输出结构：

```text
PreflightResult
├── is_runnable
├── issues[]
├── grouped_by_type
├── grouped_by_step
└── suggested_actions
```

### 6.4 问题类型

至少包含：

- `route_pending`
- `asset_pending`
- `param_pending`
- `governance_blocked`
- `dependency_incomplete`
- `mapping_incomplete`

## 7. Resolver / Executor 设计

### 7.1 公共契约

建议定义两组公共契约：

- `ResolverInput`
- `ResolverOutput`
- `ExecutorInput`
- `ExecutorOutput`

并为 HTTP / SQL 做专门扩展。

### 7.2 `HTTPResolver`

#### 输入

- `design_intent`
- `upstream_outputs`
- `user_inputs`
- `http_asset_definition`
- `template_context`
- `system_defaults`
- `history_examples`
- `history_success_mappings`

#### 输出

- `resolution_status`
- `blocking_issues`
- `resolution_rationale`
- `resolved_execution_plan`
- `editable_fields`

#### 规则

- 试跑前必须唯一确定具体资产
- 只允许补安全非关键默认值
- 关键参数缺失应阻塞

### 7.3 `HTTPExecutor`

#### 输入

- `resolved_execution_plan`
- `runtime_values`

#### 输出

- `execution_status`
- `request_snapshot`
- `response_snapshot`
- `extracted_outputs`
- `execution_metrics`
- `error_info`
- `audit_payload`

### 7.4 `SQLResolver`

#### 输入

- `design_intent`
- `upstream_outputs`
- `user_inputs`
- `sql_asset_definition`
- `schema_info`
- `template_context`
- `system_defaults`
- `governance_rules`
- `reference_sql_examples`
- `history_success_trials`

#### 输出

- `resolution_status`
- `blocking_issues`
- `resolution_rationale`
- `resolved_execution_plan`
- `editable_fields`

#### 规则

- 试跑前必须唯一确定具体 SQL 资产
- 设计阶段必须完成 lane/risk/confirmation 判定
- query 可以补安全默认项
- mutation 不允许用默认值补关键条件

### 7.5 `SQLExecutor`

#### 输入

- `resolved_execution_plan`
- `runtime_values`

#### 输出

- `execution_status`
- `sql_snapshot`
- `bound_params_snapshot`
- `result_snapshot`
- `extracted_outputs`
- `execution_metrics`
- `error_info`
- `audit_payload`

### 7.6 资产版本锁定

真正执行时的资产版本锁定，建议以 `Run` 创建时为准。

实现建议：

- `RunStep` 保存 `resolved_execution_plan_snapshot`
- 必要时保存 `asset_version_snapshot_ref`
- SQL 资产必须明确锁到具体版本
- HTTP 资产至少锁定调用方案快照

## 8. 可编辑字段与重收敛策略

### 8.1 `http_step`

可直接编辑：

- 参数映射
- 默认值
- 提取规则

需要重收敛：

- 资产变更

### 8.2 `sql_step`

可直接编辑：

- 参数映射
- 输出字段
- 排序 / `limit` 等低风险结构项

需要重收敛：

- SQL 主体变更
- 资产变更
- 高风险条件结构变更

### 8.3 重收敛触发方式

支持：

- 自动重收敛
- 用户手动点击重收敛

默认行为：

- 将步骤标记为 `needs_resolution`
- 由用户明确触发

## 9. 试跑与模板沉淀

### 9.1 试跑前门槛

只有在满足以下条件时才允许试跑：

- 无待确认技术路线
- HTTP / SQL 资产都已唯一确定
- 参数补齐
- SQL 风险预检通过
- 输出映射完整

### 9.2 试跑成功后的固化

试跑成功后必须：

- 回写最新 `resolved_execution_plan`
- 记录 `resolution_rationale`
- 记录执行快照
- 生成模板草稿版本

### 9.3 模板草稿生成

模板草稿至少承接：

- 当前 `technical_graph`
- 当前 `input_schema`
- 当前 `output_mapping`
- 每个步骤的三层信息

即：

- `design_intent`
- `resolution_rationale`
- `resolved_execution_plan`

### 9.4 事务边界

以下动作必须单事务：

- `FlowDraft -> TemplateRevision + Steps + Schema + Mapping`
- SQL 资产审核通过并切换 `current_active_version_id`
- `Run + RunStep + 初始审计记录`

## 10. API 边界建议

### 10.1 聊天探索

- `POST /api/datamakepool/conversations`
- `POST /api/datamakepool/conversations/{id}/messages`
- `GET /api/datamakepool/conversations/{id}/flowdraft`

### 10.2 FlowDraft

- `GET /api/datamakepool/flowdrafts/{id}`
- `POST /api/datamakepool/flowdrafts/{id}/resolve`
- `POST /api/datamakepool/flowdrafts/{id}/preflight`
- `POST /api/datamakepool/flowdrafts/{id}/trial`
- `GET /api/datamakepool/flowdrafts/{id}/snapshots`
- `GET /api/datamakepool/flowdrafts/{id}/diff`

### 10.3 步骤编辑

- `PATCH /api/datamakepool/flowdrafts/{id}/steps/{step_id}`
- `POST /api/datamakepool/flowdrafts/{id}/steps/{step_id}/resolve`

### 10.4 模板与执行

- `POST /api/datamakepool/templates/from-flowdraft`
- `GET /api/datamakepool/templates`
- `GET /api/datamakepool/templates/{id}/revisions`
- `POST /api/datamakepool/template-revisions/{id}/submit-review`
- `POST /api/datamakepool/template-revisions/{id}/approve`
- `POST /api/datamakepool/runs/from-template`

## 11. 第一阶段实现顺序

建议顺序：

1. 定义 `FlowDraft`、技术节点 schema、快照 schema
2. 定义 `ResolverOutput` / `ExecutorOutput` 契约
3. 落 `PreflightCheckView` 与预检服务
4. 实现 `HTTP Resolver / Executor`
5. 实现 `SQL Resolver / Executor`
6. 接聊天探索页、节点详情、diff
7. 打通试跑成功 -> 模板草稿

## 12. 结论

实现层最关键的约束只有三条：

- 主 DAG 必须是业务 DAG，不是工具 DAG
- 设计层与执行层必须分离
- 试跑成功后必须把智能收敛结果固化成可审核、可发布、可重复执行的具体方案

只要这三条守住，`Xagent` 就仍然适合作为探索前台，
而 `datamakepool` 也能稳定承接真正的平台业务内核。
