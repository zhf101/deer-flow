# GDP Agent Runtime 语义地图

> 🔗 **2026-06-23 交叉引用**：本文是 MVP1–3 语义的历史入口。最新现役权威认知请以 `docs/20260623/gdp-agent-runtime-架构地图.md` 为准（逐条对照源码、标注行号）；LangGraph 回归路线见 `docs/20260623/gdp-langgraph-回归与分层说明.md`。本文与代码冲突时以代码和 06-23 地图为准。

> 本文回答一个问题：`agent_runtime` 里到底引入了哪些语义，哪些会影响 Agent 编排流程走向，哪些只是账本记录或实现细节。
>
> 结论先行：真正决定流程走向的语义应收敛到三层：**任务状态 TaskRunStatus**、**资源缺口状态 RequirementStatus**、**结果判定 VerdictType**。`SuspendReason` 只解释为什么暂停等待用户，不是新的任务状态。`PlanStep` / `Action` / `Attempt` / `Observation` / `Evidence` 更多是执行账本，不应在需求讨论里变成主语言。

## 1. 语义分层

### 1.1 产品层：用户真正关心什么

用户只关心这些话：

```text
我要造什么数据
系统现在在找什么资源
系统准备执行哪个场景
还缺什么信息
是否需要我确认
执行结果是否完成
失败原因是什么
是否存在副作用未知，不能重试
```

产品层不应该直接说：

```text
SELECT_SCENE
APPROVE
SATISFIED
LMProposal
ActionAttempt
UNKNOWN_STATE
```

对用户和需求文档，更推荐中文表达：

| 内部术语 | 对外中文 |
|---|---|
| `SELECT_SCENE` | 选择候选场景 |
| `SUPPLY_SCENE_CODE` | 手动指定场景 |
| `APPROVE` | 批准执行 |
| `SATISFIED` | 缺口已满足 / 已选定资源 |
| `UNKNOWN_STATE` | 执行结果未知 |
| `ActionAttempt` | 执行尝试 |
| `Evidence` | 可判定证据 |
| `Verdict` | 结果判定 |

### 1.2 编排层：真正改变流程走向的东西

编排层只需要关心三个问题：

```text
任务现在能不能继续跑？          -> TaskRunStatus
当前缺口有没有被解决？          -> RequirementStatus
刚才执行结果应该怎么收口？      -> VerdictType
任务为什么等待用户？            -> SuspendReason
```

前三类状态才是 Agent 主循环和 reply 恢复的核心；`SuspendReason` 用来解释 `WAITING_USER` 的恢复类型。

### 1.3 执行账本层：记录发生了什么

这些对象用于解释、审计、幂等和回放，不应主导需求语言：

```text
PlanStep
Action
ActionAttempt
Observation
Evidence
Variable
```

它们很重要，但角色不同：

| 对象 | 作用 | 是否直接决定主流程 |
|---|---|---|
| `PlanStep` | 记录任务步骤 | 间接决定 |
| `Action` | 记录一次准备执行的副作用动作 | 间接决定 |
| `ActionAttempt` | 记录一次外部调用尝试 | 间接决定 |
| `Observation` | 保存原始执行观察 | 不直接决定 |
| `Evidence` | 把观察转成可判定事实 | 通过 Verdict 决定 |
| `Variable` | 记录输入和输出变量来源 | 当前阶段不直接决定 |

## 2. 当前代码已存在的语义

当前代码位置：`backend/app/gdp/agent_runtime/`。

### 2.1 TaskRun：任务运行

`TaskRun` 是一次造数目标的根账本。当前状态在 `TaskRunStatus`：

| 状态 | 中文语义 | 谁会进入 | 后续走向 |
|---|---|---|---|
| `CREATED` | 已创建，尚未启动 | 创建任务后 | `start` 后进入 `RUNNING`，或取消进入 `CANCELLED` |
| `RUNNING` | 正在推进 | `start` 或合法 reply 后 | 根据 Verdict 进入 `COMPLETED` / `FAILED` / `WAITING_USER` |
| `WAITING_USER` | 等用户输入，运行已暂停 | 缺参数、证据不足、未知状态 | 用户 reply 后进入 `RUNNING` 或取消 |
| `COMPLETED` | 任务完成 | Verdict 为 `DONE` | 终态 |
| `FAILED` | 任务失败 | Verdict 为 `FAILED` 或用户确认未知后停止 | 终态 |
| `CANCELLED` | 用户取消 | cancel | 终态 |

`WAITING_USER` 是最重要的运行时语义：它不是失败，而是持久化暂停。任务不占运行进程，等待用户通过 `/reply` 恢复。

`SuspendReason` 是 `WAITING_USER` 的结构化原因。它不决定任务是否能运行，真正决定运行入口的仍是 `TaskRunStatus.WAITING_USER`；它用于前端展示、审计解释和选择合适的恢复表单。

当前已实现的 `SuspendReason`：

| 原因 | 稳定中文表达 | 触发条件 | 编排走向影响 | 是否对用户外显 |
|---|---|---|---|---|
| `MISSING_INPUT` | 缺少必填输入 | 执行前缺 `env_code`、场景必填入参，或 reply 后仍缺必填入参 | 任务保持 `WAITING_USER`，等待 `SUPPLY_INPUT` 或携带输入的选择/审批回复 | 是 |
| `NEED_APPROVAL` | 等待用户批准 | 已选定的场景有写副作用且未批准 | 任务保持 `WAITING_USER`，等待 `APPROVE` 或带 `approved=true` 的选择回复 | 是 |
| `NEED_SCENE_SELECTION` | 等待选择或指定场景 | 多候选、低置信候选、零候选或候选失效 | 任务保持 `WAITING_USER`，等待 `SELECT_SCENE` 或 `SUPPLY_SCENE_CODE` | 是 |
| `UNKNOWN_STATE_CONFIRMATION` | 等待确认执行结果未知 | 场景写请求超时、连接断开或结果未知 | 任务保持 `WAITING_USER`，等待 `CONFIRM_UNKNOWN_STATE`，禁止补输入重放写请求 | 是 |
| `NEED_EVIDENCE` | 缺少可判定证据 | 执行完成后 Evidence 缺少业务判定所需事实 | 任务保持 `WAITING_USER`，等待后续人工处理或补充证据路径 | 是 |

### 2.2 PlanStep：任务步骤

第一阶段只有一个步骤，但已经引入 `StepStatus`：

| 状态 | 中文语义 | 当前用途 |
|---|---|---|
| `PENDING` | 步骤已创建，未开始 | `create_single_step()` 后 |
| `RUNNING` | 步骤正在执行 | Action 开始前 |
| `DONE` | 步骤完成 | Verdict 为 `DONE` |
| `FAILED` | 步骤失败 | Verdict 为 `FAILED` |
| `BLOCKED` | 步骤阻塞 | Verdict 为 `UNKNOWN_STATE` 或 `NEED_USER` |

`PlanStep` 状态用于解释“卡在哪个业务步骤”，不是用户入口状态。用户入口仍看 `TaskRunStatus`。

### 2.3 Action：准备执行的动作

第一阶段只有一种动作：`EXECUTE_SCENE`。

`ActionStatus`：

| 状态 | 中文语义 | 当前用途 |
|---|---|---|
| `PLANNED` | 动作已计划，未执行 | `make_scene_action()` 后 |
| `RUNNING` | 正在调用外部 Scene | `run_action()` 前 |
| `SUCCEEDED` | 技术执行成功 | Scene 返回 `SUCCESS` |
| `FAILED` | 技术执行失败 | Scene 返回失败或调用校验失败 |
| `UNKNOWN_STATE` | 写操作结果未知 | 超时、连接断开等 |

注意：`ActionStatus.SUCCEEDED` 只表示技术调用完成，不等于任务完成。任务是否完成必须看 `Evidence -> Verdict`。

### 2.4 ActionAttempt：执行尝试

`AttemptStatus`：

| 状态 | 中文语义 | 何时出现 |
|---|---|---|
| `RUNNING` | 尝试开始 | 创建 attempt 时 |
| `SUCCEEDED` | 本次调用成功 | Scene 返回 `SUCCESS` |
| `FAILED` | 本次调用失败 | Scene 返回失败、幂等冲突、校验失败 |
| `UNKNOWN_STATE` | 本次调用结果未知 | 超时、连接断开 |

`AttemptStatus` 是 `ActionStatus` 的来源之一。当前 `runner.py` 会把 attempt 同步到 action：

```text
Attempt SUCCEEDED -> Action SUCCEEDED
Attempt FAILED -> Action FAILED
Attempt UNKNOWN_STATE -> Action UNKNOWN_STATE
```

### 2.5 Observation / Evidence / Verdict：判定链

当前链路是：

```text
ActionAttempt
-> Observation 原始观察
-> Evidence 可判定证据
-> Verdict 结果判定
-> TaskRun / PlanStep 业务收口
```

这里的核心是 `VerdictType`：

| Verdict | 中文语义 | TaskRun 走向 | Step 走向 | Action 走向 |
|---|---|---|---|---|
| `DONE` | 证据证明目标完成 | `COMPLETED` | `DONE` | 不由 Verdict 修改，保留执行尝试同步出的技术状态 |
| `FAILED` | 证据证明失败 | `FAILED` | `FAILED` | 不由 Verdict 修改，保留执行尝试同步出的技术状态 |
| `UNKNOWN_STATE` | 写操作结果未知 | `WAITING_USER`，`SuspendReason=UNKNOWN_STATE_CONFIRMATION` | `BLOCKED` | 不由 Verdict 修改，通常已由 Attempt 同步为 `UNKNOWN_STATE` |
| `NEED_USER` | 证据不足，需要用户补充或确认 | `WAITING_USER`，`SuspendReason=NEED_EVIDENCE` | `BLOCKED` | 不由 Verdict 修改 |

这张表是第一阶段最关键的编排语义。尤其要记住：

- `UNKNOWN_STATE` 不等于失败。
- `NEED_USER` 不等于失败。
- `Evidence.missing_facts` 只表示证据不完整；只要存在缺失事实，就应进入 `NEED_USER`，即使已有事实里没有任何通过项，也不能直接收口为 `FAILED`。
- `Action SUCCEEDED` 不等于 `TaskRun COMPLETED`。
- `Verdict` 不修改 `ActionStatus`；`ActionStatus` 只表达技术执行结果，由 `ActionAttempt` 同步。
- `TaskRun COMPLETED` 必须有 `final_verdict_id`。

### 2.6 Reply 类型

当前代码里的 `ReplyTaskRunRequest.reply_type` 有五种：

| reply_type | 中文语义 | 当前状态 |
|---|---|---|
| `SUPPLY_INPUT` | 补充启动前缺失的输入 | 已实现 |
| `CONFIRM_UNKNOWN_STATE` | 用户确认未知状态后停止任务，避免重放 | 已实现 |
| `SELECT_SCENE` | 在候选中选择场景 | 已实现 |
| `SUPPLY_SCENE_CODE` | 零候选时手动指定场景 | 已实现 |
| `APPROVE` | 批准已选定场景执行 | 已实现 |

当前 `SUPPLY_INPUT` 有一个重要 guard：

```text
如果已有 attempts，说明写请求已经发起过，不能通过补输入重放。
```

这条 guard 是防止重复造数的核心保护。

### 2.7 Variable / LMProposal

`Variable` 当前用于记录用户输入变量，保留 provenance 地基：

| 变量来源 | 当前含义 |
|---|---|
| `USER_INPUT` | 用户输入 |
| `SCENE_OUTPUT` | 场景输出，后续阶段使用 |
| `CONTEXT` | 历史上下文，后续阶段使用 |

`LMProposal` 是反向语义：它不是事实。所有事实写入和状态转移都应拒绝 `LMProposal`。这条规则防止 LLM 直接把任务标成完成、失败或已选择。

### 2.8 审计持久化和场景运行下钻

当前代码已把 Runtime 执行账本从纯内存扩展为数据库可恢复账本。新增的是审计语义，不是新的编排状态：

| 字段 / 对象 | 中文语义 | 当前代码已实现 | 是否影响流程走向 | 是否对用户外显 |
|---|---|---|---|---|
| `ActionAttempt.scene_run_id` | 关联的场景执行记录 ID | 是 | 否，只用于从 Agent 尝试下钻到场景运行详情 | 是，审计详情页可展示为“场景运行记录” |
| `StepExecutionResult.requestSnapshot` | 场景步骤实际执行请求快照 | 是 | 否，只用于审计 HTTP / SQL 请求内容 | 是，审计详情页可展示 |
| `df_agent_runtime_*` | Agent Runtime 数据库账本表 | 是 | 否，恢复和查询历史用；状态仍以 TaskRun / Requirement / Verdict 为准 | 否，前端通过 API 展示 |
| `df_agent_runtime_payload` | 完整请求、响应、输入或错误 payload | 是 | 否，只用于详情追溯 | 默认不外显，需详情/审计权限 |

下钻链路是：

```text
TaskRun timeline
-> ActionAttempt.scene_run_id
-> SceneExecutionResult.stepResults
-> requestSnapshot + rawResponse
```

HTTP 步骤的 `requestSnapshot` 记录实际 URL、method、headers、query、body、bodyType；`rawResponse.response` 记录状态码、响应头、响应体、Cookie 和耗时。

SQL 步骤的 `requestSnapshot` 记录实际 envCode、sysCode、datasourceCode、operation、sqlText、parameters、safety、options、outputMapping；`rawResponse` 记录 SQL 执行结果、返回列、返回行、影响行数、生成键、耗时和错误。

这些字段不应该出现在产品主语言里驱动用户选择。推荐对用户说：

```text
查看本次场景运行详情
查看该步骤实际请求
查看该步骤响应结果
```

不要说：

```text
scene_run_id 已满足
requestSnapshot 状态
payload 状态
```

### 2.9 决策账本：为什么这样选择

当前代码已引入 `DecisionRecord`，用于回答“系统为什么做出这个选择”。它是审计解释账本，不是新的控制流状态。

| 字段 / 枚举 | 推荐中文 | 当前代码已实现 | 是否影响流程走向 | 是否对用户外显 |
|---|---|---|---|---|
| `DecisionRecord` | 决策记录 / 决策审计记录 | 是 | 否，只解释选择过程 | 是，审计详情页可展示 |
| `DecisionKind` | 决策类型 | 是 | 否 | 是，建议展示中文标签 |
| `DecisionSource` | 决策来源 | 是 | 否 | 是，建议展示中文标签 |
| `DecisionStatus` | 决策记录状态 | 是 | 否，不等同于 TaskRunStatus | 是，建议展示中文标签 |
| `DecisionOption` | 决策候选项 | 是 | 否 | 是 |
| `DecisionRejection` | 未选候选及原因 | 是 | 否 | 是 |

`DecisionKind` 当前稳定中文表达：

| 枚举 | 中文表达 | 当前插桩 |
|---|---|---|
| `SCENE_SEARCH` | 场景检索决策 | 是 |
| `SCENE_SELECTION` | 场景选择决策 | 是 |
| `APPROVAL_REQUIREMENT` | 审批要求决策 | 是 |
| `CONFIG_WRITEBACK` | 配置写回决策 | 是，MVP4-B 第一刀用于记录自动创建并发布 Scene 的结果 |

以下决策类型属于计划中语义，不进入当前代码枚举：步骤类型选择决策、HTTP 源选择决策、SQL 源选择决策、字段映射决策、步骤顺序决策、失败恢复选择决策。

`DecisionSource` 当前稳定中文表达：

| 枚举 | 中文表达 |
|---|---|
| `RULE` | 规则决策 |
| `CATALOG` | 场景目录 / Catalog 决策 |
| `LLM` | 模型建议经校验采纳 |
| `USER` | 用户选择 |
| `SYSTEM_DEFAULT` | 系统默认 |

`DecisionStatus` 当前稳定中文表达：

| 枚举 | 中文表达 |
|---|---|
| `DECIDED` | 已形成决策 |
| `WAITING_USER` | 等待用户参与决策 |
| `SUPERSEDED` | 已被后续决策取代 |
| `FAILED` | 决策失败 |

决策账本和流程状态的关系：

```text
DecisionStatus.WAITING_USER = 这条决策记录说明当时需要用户参与
TaskRunStatus.WAITING_USER  = 任务运行真的暂停等待用户
```

两者不能混用。前者用于解释，后者才驱动 `/reply` 恢复。

当前决策审计链路是：

```text
Requirement
-> Proposal
-> DecisionRecord(SCENE_SEARCH)
-> DecisionRecord(SCENE_SELECTION)
-> 可选 DecisionRecord(APPROVAL_REQUIREMENT)
-> Action / Attempt / SceneRun
```

对用户建议说：

```text
查看为什么选择这个场景
查看还有哪些候选没有被选
查看为什么需要审批
```

不建议说：

```text
DecisionStatus 已满足
DecisionKind 驱动流程
```

## 3. 第二阶段当前已实现语义

第二阶段设计来源：`docs/20260611/gdpagentMVP实施计划2.md`。

这些语义已进入当前 `backend/app/gdp/agent_runtime/` 主线代码，用来支持不传 `scene_code` 时的场景搜索、候选选择、人工补场景和审批恢复。

### 3.1 Requirement：资源缺口

`Requirement` 用来表达“当前为了完成步骤，还缺一个资源”。第二阶段只允许一种缺口：

```text
RequirementLayer.SCENE = 缺一个可执行的已发布场景
```

`RequirementStatus`：

| 状态 | 推荐中文 | 编排含义 |
|---|---|---|
| `PENDING` | 尚未产出候选 | 刚创建缺口，或零候选后仍等待用户手动补场景 |
| `RESOLVING` | 正在解决 / 已有候选待选 | 已搜索到候选，等待自动选择或用户选择 |
| `SATISFIED` | 缺口已满足 / 已选定资源 | 已确定 scene_code；是否能执行还要看缺参和审批 gate |
| `FAILED` | 缺口无法满足 | 用户放弃或资源缺口收口失败 |

建议对外不要说 `SATISFIED`，说“已选定场景”或“缺口已满足”。

### 3.2 SceneCandidate：候选场景

`SceneCandidate` 是 Catalog 搜索出来的事实，不是 LLM 建议。

关键字段：

| 字段 | 中文语义 | 是否影响流程 |
|---|---|---|
| `scene_code` | 候选场景编码 | 是，最终执行哪个场景 |
| `score` | 规则评分 | 是，影响是否自动选 |
| `reasons` | 命中理由 | 主要展示 |
| `missing_inputs` | 缺失入参 | 是，非空就不能执行 |
| `requires_confirmation` | 是否需要审批 | 是，决定是否暂停等用户 |
| `contract_hash` | 契约快照哈希 | 后续用于漂移检测 |

### 3.3 RequirementProposal：候选集

`RequirementProposal` 记录“一次搜索产出的候选集”。

`ProposalStatus`：

| 状态 | 中文语义 | 编排含义 |
|---|---|---|
| `PENDING` | 候选集待选择 | 用户或规则还没有选定 |
| `SELECTED` | 已选定候选 | 有一个 scene_code 被选定 |
| `REJECTED` | 候选集被拒绝 | 用户放弃或全部候选不采纳 |

`ProposalStatus` 不应该和 `RequirementStatus` 混用：

```text
Proposal SELECTED = 这批候选中选了一个
Requirement SATISFIED = 当前资源缺口被满足了
```

### 3.4 SelectionOutcome：选择决策结果

`SelectionOutcome` 是 `decide_selection()` 的临时返回值，不一定要持久化。

| outcome | 中文语义 | 后续 |
|---|---|---|
| `AUTO_SELECTED` | 单候选高置信自动选定 | 直接进入执行 gate |
| `NEED_USER` | 需要用户选择、补参或批准 | TaskRun 进入 `WAITING_USER` |
| `NO_CANDIDATE` | 没有候选 | TaskRun 进入 `WAITING_USER`，允许手动补 scene_code 或放弃 |

这是第二阶段最像“编排分岔口”的新语义。

### 3.5 SelectionSource：选择来源

`SelectionSource` 是审计语义，不应该驱动主流程：

| 来源 | 中文语义 |
|---|---|
| `AUTO` | 规则自动选 |
| `USER` | 用户选择 |
| `LLM` | LLM 建议被规则采纳 |
| `EXPLICIT` | 启动时显式传入 scene_code |

不建议产品讨论里说“LLM 选择了场景”。应该说：“LLM 给过建议，但最终由规则校验后采纳。”

### 3.6 第二阶段新增 reply 类型

| reply_type | 中文语义 | 使用场景 |
|---|---|---|
| `SELECT_SCENE` | 选择候选场景 | 多候选、低置信、需审批候选 |
| `SUPPLY_SCENE_CODE` | 手动指定场景 | 搜索零候选时，用户直接给 scene_code |
| `APPROVE` | 批准已选定场景执行 | 已选定但有副作用，需要单独批准 |

推荐规则：

```text
SELECT_SCENE 解决“选哪个”
APPROVE 解决“允不允许执行有副作用的那个”
SUPPLY_SCENE_CODE 解决“没搜到，但用户知道 scene_code”
```

不要把 `APPROVE` 写成状态。它是用户命令，不是任务状态。

## 4. 第三阶段当前已实现语义

第三阶段历史计划位置：`docs/20260611/gdpagentMVP实施计划3.md`。

这些语义已进入当前代码的最小纵切片：`planner.py` 负责确定性多步骤计划，`bindings.py` 负责步骤入参绑定，`variables.py` 负责场景输出变量抽取，`workflows/start_workflow.py` 已能在命中 recipe 时串行推进多个已有 Scene。第三阶段不新增主状态枚举，只把第一阶段已经预留的 `PlanStep`、`StepEdge`、`Variable.provenance` 真正用于多步骤串联。

当前已实现范围：

- 明确目标“创建订单并支付”可生成“创建订单 -> 支付订单 -> 查询订单状态”三个步骤。
- 未命中 recipe 或显式传入 `scene_code` 时，保持第二阶段单步骤链路。
- 步骤执行前解析 `USER_INPUT / VARIABLE / CONST` 入参绑定；缺用户输入进入 `WAITING_USER`，缺计划变量进入 `FAILED`。
- 步骤 `DONE` 后按 `SceneOutputBinding` 从 Evidence 支撑的输出中写入 `Variable`，并更新 `StepEdge.variable_ids`、`PlanStep.consumes / produces`、`Variable.consumed_by`。
- timeline 已展示 `task_run`、`step_edges` 和安全变量投影；变量完整值引用 `value_ref` 不对前端外显。
- 多步骤 `WAITING_USER` 后，`SUPPLY_INPUT`、`SELECT_SCENE`、`SUPPLY_SCENE_CODE`、`APPROVE` 已按 `active_step_id` 恢复当前步骤，并在当前步骤完成后继续推进后续待执行步骤。
- 数据库账本已覆盖多步骤 Step、Requirement、Proposal、Variable 和 `PlanStepSpec` payload 的落库恢复；恢复后的 `WAITING_USER` 可继续当前步骤。
- 多步骤执行已覆盖必需输出缺失失败收口、当前步骤失败阻断后续步骤、`UNKNOWN_STATE` 挂起并阻断后续步骤。

当前仍属于计划中语义：

- Source / Infra 配置写入、回退重跑、ContextItem 跨任务复用、Capability Graph。

### 4.1 多步骤计划

推荐中文：多步骤计划。

多步骤计划不是新的任务状态，而是从用户目标生成一组 `PlanStep`：

```text
创建订单并支付
-> Step1 创建订单
-> Step2 支付订单
-> Step3 查询订单状态
```

编排含义：

- `TaskRun.step_ids` 从一个步骤变成多个步骤。
- `TaskRun.active_step_id` 表示当前正在推进的步骤。
- 当前步骤没有完成前，后续步骤不能执行。
- 所有步骤完成后，TaskRun 才能完成。

对用户建议说：

```text
当前在执行第 2 步：支付订单
前置步骤已完成
后续步骤等待当前步骤完成
```

不要新增 `MULTI_STEP_RUNNING` 之类状态；继续使用 `TaskRunStatus.RUNNING` 和 `PlanStep.status`。

### 4.2 StepInputBinding：步骤入参绑定

推荐中文：步骤入参绑定。

`StepInputBinding` 描述当前步骤的 Scene 入参从哪里来：

| 来源 | 推荐中文 | 编排含义 |
|---|---|---|
| `USER_INPUT` | 用户输入 | 缺失时可以等待用户补充 |
| `VARIABLE` | 任务变量 | 缺失时本阶段失败收口，不执行当前步骤 |
| `CONST` | 固定值 | 只允许非敏感、非环境相关字段 |

这不是用户入口状态，也不是 Requirement 层级。它只影响“能不能创建 Action”：

```text
绑定成功 -> 创建 Action
缺用户输入 -> TaskRun WAITING_USER
缺计划变量 -> 当前 Step FAILED，TaskRun FAILED
```

### 4.3 SceneOutputBinding：场景输出变量

推荐中文：场景输出变量。

`SceneOutputBinding` 描述成功步骤如何从 Scene 输出抽取变量：

| 字段 | 中文语义 | 编排含义 |
|---|---|---|
| `output_path` | 输出路径 | 从 Observation / finalOutput 取值 |
| `variable_name` | 变量名 | 写入 TaskRun 变量账本 |
| `semantic_type` | 变量语义类型 | 后续绑定和展示使用 |
| `sensitive` | 是否敏感 | 决定 preview 是否脱敏 |
| `required` | 是否必需 | 缺失时是否让当前步骤失败 |

变量只有在当前步骤 Verdict 为 `DONE` 后才能写入事实账本。LLM 不能直接写变量事实。

### 4.4 StepEdge / Variable provenance：跨步骤传递

推荐中文：步骤依赖边、变量来源。

第三阶段开始正式使用：

```text
Step1 produces order_id
Step2 consumes order_id
TaskRun.step_edges 记录 Step1 -> Step2，携带 variable_ids
Variable.provenance 指向产出它的 Action / Evidence
```

编排含义：

- 后续步骤只能消费未污染变量。
- 变量 `value_ref` 不对用户外显。
- timeline 只展示变量名、语义类型、预览、来源步骤和消费步骤。

本阶段不做污染传播和回退，只保留 `tainted` guard：如果变量已经 tainted，不能自动绑定。

### 4.5 第三阶段不新增的语义

第三阶段刻意不新增：

```text
RequirementLayer.SOURCE
RequirementLayer.INFRA
UPSTREAM_RESOURCE_MISMATCH
CURRENT_STEP_WRONG_RESOURCE
CONTRACT_DRIFT
ContextItem
Capability Graph
RollbackPlan
```

其中 `RequirementLayer.SOURCE / INFRA` 已在 MVP4-A 只读发现中引入；Scene 配置写入和父缺口回弹已由 MVP4-B 第一刀接续实现；其余语义留给后续 MVP4-B 子任务 / MVP5 / MVP6。第三阶段只回答一个问题：已有 Scene 能不能被多个 PlanStep 串起来，并通过变量账本完成一个真实目标。

## 4A. MVP4-A 当前已实现语义：Source / Infra 只读发现

MVP4-A 目标是“只读发现”，不是自动写配置。当前代码已让 Runtime 在 Scene 零候选时继续向下发现已有 HTTP / SQL Source 和基础配置线索，并把“缺什么、已有候选是什么、下一步需要用户做什么”结构化记录到账本和 timeline。

### 4A.1 RequirementLayer 扩展

MVP4-A 当前新增：

| 枚举 | 推荐中文 | 触发条件 | 编排影响 | 是否对用户外显 |
|---|---|---|---|---|
| `SOURCE` | 缺 Source / 缺原子能力 | `SCENE` 缺口零候选，且需要查看是否已有 HTTP / SQL Source 可作为后续场景设计素材 | 创建 Source 子缺口，搜索只读 Source Catalog，最终仍 `WAITING_USER` | 是，展示“没有完整场景，但发现可用 Source / 未发现 Source” |
| `INFRA` | 缺基础配置 | Source 依赖系统、环境、服务端点或数据源不完整 | 创建 Infra 子缺口，解析只读基础配置，最终仍 `WAITING_USER` | 是，展示缺失字段，如系统、环境、服务端点、数据源 |

继续复用 `RequirementStatus`：

```text
PENDING   = 缺口已创建，尚未完成发现
RESOLVING = 已有候选或诊断结果，等待用户处理
SATISFIED = 当前层缺口已满足
FAILED    = 当前层缺口无法满足
```

不要为 Source / Infra 新增一批同义状态。

### 4A.2 父子缺口

MVP4-A 当前给 `Requirement` 增加：

```text
parent_requirement_id
```

编排含义：

```text
SCENE 缺口
  -> SOURCE 子缺口
      -> INFRA 子缺口
```

MVP4-A 本阶段只记录父子关系和展示路径，不做自动回弹执行。前端运行台按 `parent_requirement_id` 展示 `SCENE -> SOURCE -> INFRA` 缺口树，并把每层 proposal / Source / Infra 摘要挂到对应缺口上。MVP4-B 第一刀已接续处理“基于已有 Source 发布 Scene 后回到父缺口继续执行”。

### 4A.3 SourceCandidate

`SourceCandidate` 是已有 HTTP / SQL Source 的只读候选，不是将要自动保存的配置草稿。

当前字段：

| 字段 | 中文语义 | 是否影响流程 | 是否对用户外显 |
|---|---|---|---|
| `source_type` | Source 类型，HTTP 或 SQL | 是，决定后续看服务端点还是数据源 | 是 |
| `source_code` | Source 编码 | 是，后续人工建 Scene 时可引用 | 是 |
| `source_name` | Source 名称 | 展示 | 是 |
| `score` | 规则评分 | 影响排序，不直接定案 | 是 |
| `reasons` | 命中理由 | 展示 | 是 |
| `missing_inputs` | 缺失入参 | 是，提示该 Source 仍需哪些输入 | 是 |
| `requires_confirmation` | 未来执行是否需要审批 | 是，表达副作用风险 | 是 |
| `sys_code` | 所属系统编码 | 是，用于 Infra 解析 | 是 |
| `method` / `path` | HTTP 方法和路径 | 展示和诊断 | 是 |
| `datasource_code` / `operation` | SQL 数据源和操作类型 | 展示和诊断 | 是 |
| `contract_hash` | Source 契约快照哈希 | 后续 MVP5 漂移检测 | 否 |

注意：`requires_confirmation` 不等于 `WAITING_APPROVAL`，审批仍通过 `TaskRun.status = WAITING_USER` 和 `SuspendReason.NEED_APPROVAL` 表达。

### 4A.4 InfraCandidate

`InfraCandidate` 更接近基础配置诊断结果，用来回答“这个 Source 依赖的基础配置是否已具备”。

当前字段：

| 字段 | 中文语义 | 是否影响流程 | 是否对用户外显 |
|---|---|---|---|
| `resource_type` | HTTP 或 SQL | 是，决定检查服务端点还是数据源 | 是 |
| `ready` | 基础配置是否满足 | 是，提示能否继续人工建 Source/Scene | 是 |
| `confidence` | 解析置信度 | 展示和排序 | 是 |
| `missing_fields` | 仍缺字段 | 是，提示用户下一步补什么 | 是 |
| `matched_systems` | 命中的系统摘要 | 展示 | 是，摘要 |
| `matched_environments` | 命中的环境摘要 | 展示 | 是，摘要 |
| `matched_service_endpoints` | 命中的服务端点摘要 | 展示 | 是，不能含凭据 |
| `matched_datasources` | 命中的数据源摘要 | 展示 | 是，不能含密码、token、完整连接串 |

### 4A.5 MVP4-A 流程

```text
Scene 搜索零候选
-> 创建 SOURCE 子缺口
-> 只读搜索 HTTP / SQL Source
-> 可选解析 INFRA 依赖
-> 记录 Source / Infra proposal
-> TaskRun WAITING_USER
-> 提示用户：没有完整场景，但已有 Source / 缺 Source / 缺基础配置
```

本阶段不做：

```text
自动生成并发布 Scene（已由 MVP4-B 第一刀接续实现，不属于 MVP4-A）
自动保存 Source
自动保存基础配置
Capability Graph
回退重跑
```

## 4B. MVP4-B 当前第一刀语义：配置写入与父缺口回弹

MVP4-B 的新增语义是“写入配置后回弹父缺口”，不是“等待人工审批”。Owner 已确认：Source / Infra / Scene 配置写入不需要人工确认；实现不得把人工确认作为默认门禁，也不要新增 `WAITING_APPROVAL`、`ASK_ALWAYS`、`DELEGATED`、`FULL_ACCESS` 一类审批模式来阻塞写入。

当前代码已实现的第一刀只覆盖：Scene 零候选后，已有 Source 候选且 Infra ready 时，Runtime 基于这些 Source 自动创建并发布组合 Scene，记录 `CONFIG_WRITEBACK` 决策审计，然后用新 `scene_code` 回弹父 SCENE 缺口并继续走现有契约解析、选择门禁和执行链路。

当前已实现语义：

| 语义 | 推荐中文 | 触发条件 | 编排影响 | 是否对用户外显 |
|---|---|---|---|---|
| Scene 配置写入 | 自动创建并发布组合 Scene | SCENE 零候选，Source 候选非空，InfraCandidate 均 ready 且无 missing_fields，SceneDefinition 发布校验通过 | 通过 datagen SceneService 创建和发布 Scene；Runtime 不直接写数据库表 | 是，展示写入结果和失败原因 |
| 父 SCENE 缺口回弹 | 回到上层缺口继续解析 | Scene 写入成功并返回 target scene_code | 父 Requirement 进入现有 resolve/select/execute 路径，最终仍由 `RequirementStatus`、`TaskRunStatus`、`VerdictType` 收口 | 是，展示“已补齐子资源，继续处理父目标” |
| 写入审计 | 配置写回决策 | 自动写入成功、失败或跳过且能形成结构化结果 | 新增 `DecisionKind.CONFIG_WRITEBACK`，只解释写入过程，不作为主流程状态 | 可在审计页外显 |

后续仍属于计划中语义：

| 语义 | 推荐中文 | 说明 |
|---|---|---|
| Source 配置写入 | 自动创建 HTTP / SQL Source | 第一刀不做，后续再基于更完整的安全边界和契约校验实现 |
| Infra 配置写入 | 自动创建系统、环境、服务端点或数据源 | 第一刀不做，后续需要明确权限、环境和敏感字段边界 |
| 配置写入专用账本实体 | 写入审计事实 | 第一刀先复用 `DecisionRecord` 安全记录，后续可升级为独立 `ConfigWritebackRecord` |

第一刀写入前必须满足：

- 确定性契约校验通过：Source 候选非空，Infra 无阻塞缺口，生成的 SceneDefinition 可发布。
- 权限和环境边界通过：只能写入当前运行环境允许的 GDP/datagen Scene 配置范围。
- 敏感信息不进入 timeline 明文投影。
- 写入成功、失败、跳过都要有审计记录。

写入失败时不要静默降级为成功，也不要让 LLM 直接写业务事实；应保持缺口可诊断，并给出可修复原因。

## 5. 编排流程走向总表

### 5.1 第一阶段当前流程

```text
创建 TaskRun
-> CREATED
-> start(scene_code, inputs)
-> RUNNING
-> 启动前校验
   -> 缺 env_code / 缺硬编码必填输入
      -> WAITING_USER
      -> SUPPLY_INPUT 后恢复
   -> 校验通过
      -> 创建 PlanStep
      -> 创建 Action(EXECUTE_SCENE)
      -> run_action
      -> Attempt / Observation
      -> Evidence
      -> Verdict
      -> apply_verdict
```

`apply_verdict` 决定收口：

```text
DONE          -> TaskRun COMPLETED
FAILED        -> TaskRun FAILED
UNKNOWN_STATE -> TaskRun WAITING_USER，SuspendReason=UNKNOWN_STATE_CONFIRMATION，等待 CONFIRM_UNKNOWN_STATE
NEED_USER     -> TaskRun WAITING_USER，SuspendReason=NEED_EVIDENCE，等待用户处理缺失证据
```

### 5.2 第二阶段当前实现流程

```text
创建 TaskRun
-> start(goal, inputs, scene_code?)
-> 如果 scene_code 有值
   -> 解析场景契约
   -> 合成单候选 Proposal
   -> 缺参/需审批则 WAITING_USER
   -> 否则执行 Scene

-> 如果 scene_code 为空
   -> 创建 Requirement(SCENE)
   -> 搜索 Catalog
   -> 产出 Proposal
      -> 零候选：WAITING_USER，允许 SUPPLY_SCENE_CODE
      -> 单候选高置信且不缺参且无需审批：AUTO_SELECTED，执行
      -> 多候选/低分/缺参/需审批：WAITING_USER
   -> 用户 SELECT_SCENE / APPROVE 后再执行
```

第二阶段不改变第一阶段的执行判定链：

```text
选定 Scene 后
-> Action
-> Attempt
-> Observation
-> Evidence
-> Verdict
-> TaskRun 终态或 WAITING_USER
```

### 5.3 第三阶段当前实现流程

```text
创建 TaskRun
-> start(goal, inputs, scene_code?)
-> 如果命中多步骤计划
   -> 创建多个 PlanStep
   -> active_step_id 指向第一个步骤
   -> 当前步骤绑定输入
   -> 当前步骤创建 Requirement(SCENE)
   -> 复用第二阶段搜索 / 选择 / 审批 / 执行链路
   -> Verdict DONE 后抽取 Scene 输出变量
   -> 变量写入 Variable 账本
   -> 更新 step_edges / consumes / produces
   -> 推进下一个依赖满足的步骤
   -> 所有步骤 DONE 后 TaskRun COMPLETED

-> 如果未命中多步骤计划
   -> 继续走第二阶段单步骤流程
```

第三阶段失败收口规则：

```text
当前步骤 FAILED        -> TaskRun FAILED，后续步骤不执行
当前步骤 UNKNOWN_STATE -> TaskRun WAITING_USER，后续步骤不执行
缺用户输入             -> TaskRun WAITING_USER
缺计划变量             -> 当前步骤 FAILED，TaskRun FAILED
```

## 6. 哪些术语应该收敛

### 6.1 用户和产品文档只保留中文动作

建议把这些内部术语藏起来：

| 不建议外显 | 建议替代 |
|---|---|
| `SELECT_SCENE` | 选择候选场景 |
| `SUPPLY_SCENE_CODE` | 手动指定场景 |
| `APPROVE` | 批准执行 |
| `SATISFIED` | 已选定场景 / 缺口已满足 |
| `AUTO_SELECTED` | 自动选定 |
| `NEED_USER` | 需要用户处理 |
| `NO_CANDIDATE` | 未找到候选场景 |
| `StepInputBinding` | 步骤入参绑定 |
| `SceneOutputBinding` | 场景输出变量 |
| `StepEdge` | 步骤依赖边 |

### 6.2 代码里可以保留，但要分组

代码枚举建议按职责分组：

```text
编排主状态：
- TaskRunStatus
- RequirementStatus
- VerdictType

执行账本状态：
- StepStatus
- ActionStatus
- AttemptStatus

交互命令和恢复说明：
- ReplyType
- SuspendReason

审计说明：
- SelectionSource
- ProposalStatus

安全边界：
- LMProposal
- approval_record
- idempotency_key
```

### 6.3 第二阶段最容易混淆的三组词

第一组：`RequirementStatus.SATISFIED` 和 `ProposalStatus.SELECTED`

```text
Proposal SELECTED：在这一批候选里选中了某个 Scene。
Requirement SATISFIED：当前 SCENE 缺口已经被满足。
```

当前 `Requirement.selected_scene_code`、`Proposal.selected_scene_code` 和执行前的 `Action.scene_code` 必须一致。
代码只能通过 `apply_selection()` 写选定事实；执行前会再次校验三者一致，避免账本事实漂移后继续发写请求。

第二组：`ActionStatus.SUCCEEDED` 和 `VerdictType.DONE`

```text
Action SUCCEEDED：外部调用技术成功。
Verdict DONE：证据证明业务目标完成。
```

第三组：`APPROVE` 和 `SELECT_SCENE`

```text
SELECT_SCENE：选择哪个场景。
APPROVE：批准已选场景产生副作用。
```

### 6.4 第三阶段最容易混淆的三组词

第一组：`PlanStep.status` 和 `TaskRun.status`

```text
PlanStep DONE：某个业务步骤完成。
TaskRun COMPLETED：所有步骤完成，整个任务完成。
```

第二组：`Variable.value_ref` 和 `Variable.value_preview`

```text
value_ref：完整值的安全引用，不能直接展示。
value_preview：可展示摘要，敏感值必须脱敏。
```

第三组：`StepInputBinding` 和 `Requirement`

```text
StepInputBinding：当前步骤入参怎么绑定。
Requirement：当前步骤缺哪个可执行资源。
```

## 7. 建议的最小主语言

后续讨论和文档尽量只用下面这套中文主语言：

```text
任务运行
任务步骤
资源缺口
候选场景
选择候选
批准执行
步骤入参绑定
场景输出变量
步骤依赖边
执行动作
执行尝试
原始观察
可判定证据
结果判定
等待用户
执行结果未知
任务完成
任务失败
```

对应代码名放括号里即可：

```text
任务运行（TaskRun）
资源缺口（Requirement）
结果判定（Verdict）
等待用户（WAITING_USER）
执行结果未知（UNKNOWN_STATE）
```

这样既不丢失工程精度，也不会让需求文档被枚举名淹没。

## 8. 下一步收敛建议

1. 第二阶段已把 `ReplyType` 固化为内部回复语义；后续新增 reply 类型时，必须同步写清稳定中文表达和触发条件。
2. `APPROVE` 已是当前可执行回复类型；后续文档不要再把它写成计划中能力。
3. 前端和接口响应尽量展示中文标签，不直接展示 enum。
4. `RequirementStatus.SATISFIED` 如果继续让人困惑，可以在代码注释中固定中文为“缺口已满足”，不要解释成“审批已完成”。
5. 后续文档里每次首次出现 `SELECT_SCENE / APPROVE / SATISFIED` 时，必须带中文解释。
6. 第三阶段不要新增任务状态；多步骤只启用 `PlanStep`、`StepEdge`、`Variable` 的既有语义。
7. MVP4-A 已新增 SOURCE/INFRA；后续扩展配置写入或回弹时不要新增同义状态，继续复用 `RequirementStatus`，只补明确的层级语义和用户回复语义。
8. MVP4-B 配置写入不需要人工确认；不要把“审批策略”设计成写入默认门禁，写入安全靠确定性校验、权限/环境边界和审计。
