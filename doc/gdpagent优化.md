# GDP Agent 优化总纲

本文基于 `D:\.adb\deer-flow\doc` 下已有 DeerFlow 源码分析文档整理，目标不是把 Lead Agent 设计原样搬到 GDP Agent，而是提炼 DeerFlow 的设计精髓，规划 GDP Agent 后续优化章节。

核心判断：

- DeerFlow Lead Agent 是通用长时序 Agent 运行时，围绕 `ThreadState + middleware + tools + memory + skills + subagents + Gateway` 建立可恢复、可观测、可扩展的执行体系。
- GDP Agent 是造数业务 Agent，业务事实权威来源应始终是 `TaskRun/TaskStep/TaskEvent/visibleVariables`，不能被 `messages`、memory、checkpoint、SSE 或子 Agent transcript 替代。
- GDP 应借鉴 DeerFlow 的生命周期治理、运行时边界、横切能力拆分、外部能力接入和恢复机制；但在 state、middleware、tools、memory、skills、MCP、subagent 上都应做 GDP 专用物理隔离。

## 总体优化目标

GDP Agent 优化的目标可以归纳为五点：

1. **目标不漂移**：长任务、多阶段、子 Agent 协作后，仍能持续锚定用户原始造数目标、当前阶段目标和未完成目标。
2. **状态不遗忘**：任务目标、计划、变量栈、步骤结果、用户确认、审批、子任务结果都以结构化状态保存，不依赖长消息历史。
3. **恢复不重跑**：异常中断、服务重启、用户稍后恢复时，能从最近的业务步骤继续，而不是从头执行。
4. **副作用可治理**：场景执行、Source 保存、Infra 保存、SQL/HTTP 调用等副作用都有权限、审批、幂等、审计和输出预算。
5. **能力可扩展**：后续接入 memory、skills、MCP、子 Agent 时，每一类能力都有独立生命周期和 GDP 专用策略。

## 总体架构原则

```text
Gateway
  负责 HTTP、安全、LangGraph runtime、thread/run/checkpoint、SSE

GDP Datagen API
  负责任务、场景、Source、基础配置、能力目录、业务权限

GDP Agent Graph
  负责读取 TaskRun 目标，推进 TaskStep，写 TaskEvent，更新 visibleVariables

GDP State
  负责图运行快照，不替代业务数据库

GDP Middleware
  负责上下文注入、恢复、审计、幂等、压缩、记忆、子任务、错误和中断治理

GDP Tools / Skills / MCP / Subagents
  负责受控业务能力扩展，所有结果回写 Task 生命周期
```

## 当前代码现状校准

结合 `D:\agent\deer-flow` 当前源码，原 `taskagent评审.md` 中大部分判断成立，但需要明确哪些是“当前已有能力”，哪些仍是“优化目标”。

当前已经成立的事实：

- `backend/app/gdp/agent/state.py` 中 `GDPState` 仍是轻量状态：`messages/task_run_id/user_intent/env_code/current_phase/pending_confirmation/confirmation_result/last_tool_result/user_inputs/inputs`，只有 `messages` 使用 `add_messages` reducer。
- `backend/app/gdp/agent/graph.py` 直接构造 `StateGraph(GDPState)` 并注册固定业务节点，没有 `create_agent(..., middleware=...)` 入口，也没有 GDP 专用 node wrapper。
- `make_gdp_agent(config, app_config)` 当前基本忽略 `config` 和 `app_config`，直接 `_build_services()` 后返回固定图。
- Gateway 已在 `resolve_agent_factory()` 中把 `assistant_id=gdp_agent` 路由到 `make_gdp_agent`，GDP 不是 Lead Agent 的 custom agent 分支。
- GDP 业务事实已经主要落在 `TaskRun/TaskStep/TaskEvent/visibleVariables`：任务模型中包含 `deerflowThreadId/deerflowRunId/lastCheckpointId/pendingInterrupts/goalStack/plan/visibleVariables`。
- `human_confirm` 使用 LangGraph `interrupt(payload)` 恢复用户回复，并把 TaskRun 从 `WAITING_USER` 切回业务阶段；但 state 返回值没有显式清空 `pending_confirmation`，后续应作为 P0 级状态语义修正。
- `build_scene_tools()`、`build_source_config_tools()`、`build_infra_config_tools()`、`build_task_tools()` 已存在，但当前主图节点主要直接调用 service/tool 函数，没有统一 `get_gdp_tools()` 和工具暴露策略。
- GDP 当前没有接入 Lead 的 `MemoryMiddleware`、`DynamicContextMiddleware`、Skills prompt 注入、MCP deferred tools 或 Lead `task` 子 Agent 机制。

因此，本文后续章节采用这个口径：当前 GDP 的“业务状态机 + 业务表权威”方向是正确的；需要优化的是运行时装配、状态生命周期、横切 middleware、恢复语义、记忆和能力扩展治理，而不是把 GDP 改造成 Lead Agent。

## 章节规划总览

| 章节 | 参考文档 | GDP 优化主题 | 优先级 |
| --- | --- | --- | --- |
| 1 | `00-源码分析教程总览.md` | 建立 GDP Agent 优化总地图 | P0 |
| 2 | `02-LangGraph核心概念.md` | 明确 GDP 是业务状态机，不是 while 循环 | P0 |
| 3 | `03-ThreadState状态管理.md` | 设计 GDPState v2 和字段生命周期 | P0 |
| 4 | `04-LeadAgent工厂模式.md` | 重构 GDP Agent 工厂和运行时装配 | P0 |
| 5 | `05-中间件链详解.md` | 建立 GDP 专用 middleware 链 | P0 |
| 6 | `06-工具系统.md` | 建立 GDP 专用工具和能力目录 | P1 |
| 7 | `07-沙箱执行系统.md` | 治理 SQL/HTTP/文件/脚本执行边界 | P1 |
| 8 | `08-子智能体系统.md` | 建立 GDP 子任务和子 Agent 协作模型 | P1 |
| 9 | `09-记忆系统.md` | 建立 GDP 专用记忆，不替代任务事实 | P1 |
| 10 | `10-配置系统.md` | 拆分部署配置、扩展配置和业务策略 | P1 |
| 11 | `12-MCP协议集成.md` | 接入 GDP 外部能力 registry 和 policy | P2 |
| 12 | `13-Skills技能系统.md` | 建立 GDP 阶段技能和方法论体系 | P2 |
| 13 | `14-GatewayAPI.md` | 完善 Gateway 接入、权限、SSE 和恢复边界 | P0 |
| 14 | 全部文档 | 分阶段落地路线和验收标准 | P0 |

## 1. GDP Agent 优化总地图

参考文档：`00-源码分析教程总览.md`

### DeerFlow 参考点

DeerFlow 的主链路是：

```text
Gateway API
  -> start_run / run_agent
  -> make_lead_agent
  -> LangGraph 图
  -> ThreadState + middleware chain
  -> tools / sandbox / MCP / subagents / skills / memory
  -> checkpointer + stream bridge + event store
```

### DeerFlow 为什么这样设计

这是为了解决长时序 Agent 的工程问题：状态持久、恢复、工具扩展、文件隔离、子任务、上下文压缩、记忆、流式事件和前端可观测性。

### GDP 优化方向

GDP 应建立自己的主链路：

```text
Datagen API / Gateway run
  -> make_gdp_agent
  -> GDP Agent factory
  -> GDP StateGraph
  -> GDPState + GDP middleware chain
  -> GDP tools / task services / capability registry / subagents
  -> TaskRun + TaskStep + TaskEvent + visibleVariables
  -> checkpoint + SSE 实时镜像
```

### 优化目标

形成一份 GDP 专用运行时地图，后续任何新能力都能明确挂在哪一层，而不是散落在节点里。

## 2. LangGraph 与 GDP 业务状态机

参考文档：`02-LangGraph核心概念.md`

### DeerFlow 参考点

LangGraph 不只是替代 while 循环，而是把 state、node、edge、checkpointer、reducer 和 stream 变成运行时能力。

### DeerFlow 为什么这样设计

手写循环无法可靠处理：

- 状态持久化。
- 并发状态合并。
- 流式消息替换。
- interrupt/resume。
- thread/run/event 生命周期。

### GDP 优化方向

GDP 当前使用 `StateGraph(GDPState)` 是正确方向。后续优化重点不是把 GDP 改成通用聊天 Agent，而是把显式业务节点做得更可恢复：

- 每个节点有明确输入、输出、副作用和恢复点。
- 每条条件边只依赖结构化状态和 TaskRun 阶段，不依赖自由文本判断。
- checkpoint 负责图恢复，TaskRun/TaskStep 负责业务恢复。

### 优化目标

GDP 图既保留业务状态机的确定性，又充分利用 LangGraph 的 checkpoint、interrupt、stream 和 reducer。

## 3. GDPState v2：字段生命周期设计

参考文档：`03-ThreadState状态管理.md`

### DeerFlow 参考点

`ThreadState` 的精髓不是字段多，而是每个字段有明确生命周期：

- 谁生产。
- 谁消费。
- 是否进入 checkpoint。
- reducer 如何合并。
- 什么时候清理。
- 是否只是运行快照，还是业务事实。

### DeerFlow 为什么这样设计

长任务中，状态会被节点、中间件、工具、子 Agent 和前端同时使用。如果字段没有生命周期，容易出现覆盖、遗忘、误清空、恢复失败和上下文膨胀。

### GDP 优化方向

GDP 不应机械继承 `ThreadState`。当前 `GDPState` 的问题不是字段少，而是字段语义还不够稳定：

- `inputs` 和 `user_inputs` 同时存在，入口契约容易含混。
- `pending_confirmation` 恢复后没有显式清空，checkpoint 中可能保留已经处理过的等待问题。
- `last_tool_result` 是大杂烩字段，长期会让节点间传递契约隐式化，也有 checkpoint 膨胀风险。
- 除 `messages` 外没有 reducer，后续一旦出现并行候选评分、并行子任务或多个 middleware 累积写入，默认覆盖语义会变得危险。

新增任何 GDPState 字段前，都必须能回答四个问题：

1. 谁写入这个字段。
2. 谁读取这个字段。
3. 这个字段何时清理或覆盖。
4. 这个字段是否应该进入 checkpoint。

推荐把 `GDPState v2` 设计成轻量状态总线，而不是 Task 表副本：

```python
class GDPRuntimeContext(TypedDict, total=False):
    thread_id: str
    run_id: str
    user_id: str | None
    operator: str | None
    assistant_id: str


class GDPTaskContext(TypedDict, total=False):
    task_run_id: str
    status: str
    phase: str
    env_code: str | None
    deerflow_thread_id: str | None
    deerflow_run_id: str | None
    last_checkpoint_id: str | None


class GDPConfirmation(TypedDict, total=False):
    question_id: str
    question_type: str
    phase: str
    resume_phase: str | None
    question: str
    details: dict[str, Any]
    emitted: bool


class GDPResultRef(TypedDict, total=False):
    ref_type: str
    task_step_id: str | None
    scene_run_id: str | None
    scene_code: str | None
    source_code: str | None
    artifact_id: str | None
    summary: dict[str, Any]


class GDPState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]

    runtime_context: Annotated[GDPRuntimeContext, merge_dict]
    task_context: Annotated[GDPTaskContext, merge_dict]

    user_intent: str
    env_code: str
    user_inputs: Annotated[dict[str, Any], merge_user_inputs]

    current_phase: str
    phase_history: Annotated[list[dict[str, Any]], append_bounded_dedupe]
    node_attempts: Annotated[dict[str, int], merge_counter]

    pending_confirmation: GDPConfirmation | None
    confirmation_result: Any | None

    decision_context: Annotated[dict[str, Any], merge_dict]
    last_result_ref: GDPResultRef | None
    result_refs: Annotated[list[GDPResultRef], append_bounded_dedupe]

    errors: Annotated[list[dict[str, Any]], append_bounded]
```

关键规则：

- checkpoint 里只放恢复图执行需要的轻量状态。
- 能从 TaskRun/TaskStep/TaskEvent 重建的，不在 state 保存完整值。
- HTTP 响应、SQL 结果、场景执行全量输出、候选资源长列表不进 state，只保存引用和摘要。
- `messages` 是平台兼容通道，不是 GDP 业务状态主干。
- `pending_confirmation` 在 resume 后必须显式写回 `None`。
- `inputs` 应逐步废弃，入口统一归一化为 `user_inputs`。
- `last_tool_result` 应拆成 `decision_context/last_result_ref/result_refs`。

推荐 reducer：

```python
def merge_dict(existing: dict | None, new: dict | None) -> dict:
    if existing is None:
        return dict(new or {})
    if new is None:
        return existing
    return {**existing, **new}


def merge_user_inputs(existing: dict | None, new: dict | None) -> dict:
    merged = dict(existing or {})
    merged.update(new or {})
    return merged


def merge_counter(existing: dict[str, int] | None, new: dict[str, int] | None) -> dict[str, int]:
    result = dict(existing or {})
    for key, value in (new or {}).items():
        result[key] = result.get(key, 0) + int(value)
    return result
```

注意：reducer 必须是纯函数，不读写数据库、不生成 UUID、不读当前时间。稳定 ID 应由 middleware 或节点在写入 state 前生成。

推荐迁移顺序：

1. 第一阶段修正状态语义：引入 `runtime_context/task_context`，统一 `user_inputs`，让 `pending_confirmation` 支持显式清空。
2. 第二阶段拆掉 `last_tool_result`：新增 `decision_context/last_result_ref/result_refs`，完整结果落 TaskStep/SceneRun/TaskEvent。
3. 第三阶段引入 GDP middleware 链，让 context binding、failure、interrupt、output budget、guardrail audit 不再散落在节点里。
4. 第四阶段等 LLM 节点变多后，再引入 context compression 和 memory context。

### 优化目标

让 GDPState 成为图运行快照，而不是业务数据库；让每个字段都能从 TaskRun/TaskStep/TaskEvent 重建或校验。

## 4. GDP Agent 工厂重构

参考文档：`04-LeadAgent工厂模式.md`

### DeerFlow 参考点

Lead Agent 工厂在每次 run 入口统一装配：

- runtime config。
- model。
- tools。
- skills。
- middleware。
- metadata。
- callbacks/tracing。
- state schema。

### DeerFlow 为什么这样设计

Agent 不做全局单例，是为了避免跨请求共享可变状态；动态参数从 `configurable/context` 进入，是为了适配 Gateway 和 LangGraph runtime。

### GDP 优化方向

当前 `make_gdp_agent(config, app_config)` 基本忽略 `config` 和 `app_config`。后续建议拆成：

```python
def make_gdp_agent(config: RunnableConfig, app_config: AppConfig):
    runtime = _get_gdp_runtime_config(config)
    services = _build_gdp_services(app_config, runtime)
    policy = _build_gdp_policy(app_config, runtime)
    middlewares = _build_gdp_middlewares(app_config, runtime, policy)
    metadata = _build_gdp_metadata(config, runtime)
    return create_gdp_graph(
        services=services,
        middlewares=middlewares,
        policy=policy,
        metadata=metadata,
    )
```

### 优化目标

GDP 工厂从“返回固定图”升级为“按本次任务上下文装配业务 Agent runtime”。节点只处理业务逻辑，不再自己解析各种运行期开关。

## 5. GDP 专用 Middleware 链

参考文档：`05-中间件链详解.md`

### DeerFlow 参考点

Lead middleware 把复杂能力拆成横切关注点，例如上下文注入、工具错误、摘要、记忆、循环检测、子 Agent 限流、澄清中断、标题生成和 token 观测。

### DeerFlow 为什么这样设计

这些能力如果散落在节点或工具里，会导致顺序不可控、错误处理不一致、状态字段被乱写、恢复语义分叉。

### GDP 优化方向

GDP 不应直接复用 Lead 的 `AgentMiddleware`。建议新增物理隔离的 GDP middleware：

```text
backend/app/gdp/agent/middlewares/
```

建议链路：

1. `GDPRuntimeContextMiddleware`：解析 thread/run/user/task/env/model。
2. `GDPTaskRunSyncMiddleware`：节点前刷新 TaskRun，节点后同步 checkpoint/run。
3. `GDPGoalGuardMiddleware`：保护原始目标、父目标和当前阶段目标。
4. `GDPTaskEventAuditMiddleware`：统一记录节点开始、结束、异常。
5. `GDPIdempotencyMiddleware`：保护场景执行、Source 保存、Infra 保存等副作用。
6. `GDPBusinessGuardrailMiddleware`：审批、环境、敏感字段、危险 SQL、写操作策略。
7. `GDPMemoryInjectionMiddleware`：注入常用环境、系统别名、字段映射、常用 SQL。
8. `GDPContextCompressionMiddleware`：压缩长任务和子任务结果，保留目标锚点。
9. `GDPSubtaskMiddleware`：子任务创建、等待、归并、失败处理。
10. `GDPProgressLoopDetectionMiddleware`：检测阶段振荡和重复执行。
11. `GDPErrorHandlingMiddleware`：异常分类，可恢复异常进入等待或重试。
12. `GDPInterruptMiddleware`：统一 WAITING_USER、pendingInterrupts、resume。

Lead middleware 对 GDP 的取舍建议：

| Lead middleware | DeerFlow 解决的问题 | GDP 处理方式 |
| --- | --- | --- |
| `ToolOutputBudgetMiddleware` | 大工具输出外置，防止消息爆上下文 | 改写成 `GDPOutputBudgetMiddleware`，HTTP/SQL/场景结果完整落库或落文件，state 只放摘要和引用。 |
| `ThreadDataMiddleware` | 注入 thread/run/user/workspace 路径 | 改写成 `GDPRuntimeContextMiddleware`，注入 thread/run/user/task/env，不复制 `thread_data` 语义。 |
| `UploadsMiddleware` | 上传文件进入最后用户消息 | 不原样复用；GDP 附件应进入任务资源/附件模型，Prompt 只拿摘要或引用。 |
| `SandboxMiddleware` | 沙箱获取和释放 | 仅在 GDP 需要脚本/文件沙箱时适配，不默认接入。 |
| `DanglingToolCallMiddleware` | 修复 AI tool_call 与 ToolMessage 配对 | GDP 主图不适用；仅当某个 GDP 子 Agent 内部使用 `create_agent` 工具循环时考虑复用。 |
| `LLMErrorHandlingMiddleware` | LLM 错误分类、重试、熔断 | 思路可复用到 GDP LLM 节点 wrapper。 |
| `GuardrailMiddleware` | 工具调用安全检查 | 改写成业务 guardrail：环境、审批、敏感字段、危险 SQL、写操作策略。 |
| `SandboxAuditMiddleware` | shell 命令审计 | GDP 更需要 SQL/HTTP/Source/Scene 执行审计。 |
| `ToolErrorHandlingMiddleware` | 工具错误转 ToolMessage | GDP 不输出 ToolMessage；应转 TaskRun FAILED、TaskEvent 和可恢复状态。 |
| `DynamicContextMiddleware` | 日期、memory 等隐藏上下文注入 | 改写成领域上下文注入：环境、系统别名、字段映射、常用 SQL、能力目录。 |
| `DeerFlowSummarizationMiddleware` | 聊天消息压缩和 skill rescue | GDP 不压缩业务表；只生成目标锚点、进度摘要、变量摘要和子任务摘要。 |
| `TodoMiddleware` | 未完成 todo 不允许结束 | GDP 用 TaskRun.phase、TaskStep 状态和 goalStack 实现“未完成阶段不允许结束”。 |
| `TokenUsageMiddleware` | token 和行为归因 | 改写成 GDP 节点成本、子任务成本和 LLM 调用成本归因，落 TaskEvent 或成本字段。 |
| `TitleMiddleware` | 生成线程标题 | GDP 任务标题应来自造数目标、环境、场景和 finalSummary。 |
| `MemoryMiddleware` | 会话结束后异步抽取长期记忆 | 不原样复用；GDP 记忆来自 TaskEvent/TaskStep/用户确认/资源选择。 |
| `DeferredToolFilterMiddleware` | 大量工具按需提升 | 可改写为 GDP capability search，不把所有场景/Source/MCP tool 直接暴露。 |
| `SubagentLimitMiddleware` | 限制并发 task tool call | 改写成 GDP subtask 并发、单阶段创建数量和超时限制。 |
| `LoopDetectionMiddleware` | 检测重复工具调用 | 改写成阶段振荡、重复候选确认、重复配置失败和重复执行场景检测。 |
| `ClarificationMiddleware` | ask_clarification 转图中断 | GDP 已有 WAITING_USER + TaskEvent + `interrupt()`，应做 GDPInterruptMiddleware。 |

### 优化目标

把 GDP 的恢复、审计、幂等、压缩、记忆、子任务、错误和中断从业务节点中抽出来，形成可测试、可替换、顺序明确的运行时链路。

## 6. GDP 工具与能力目录

参考文档：`06-工具系统.md`

### DeerFlow 参考点

Lead 工具系统集中收集配置工具、内置工具、MCP 工具、ACP 工具、子 Agent 工具，并通过 tool groups、skills allowed-tools、deferred tool 和 sandbox policy 控制暴露面。

### DeerFlow 为什么这样设计

工具数量会膨胀，工具副作用和输出大小不可控。如果每个节点随意拼工具，模型会看到过多 schema，也难以统一做权限、审计和错误处理。

### GDP 优化方向

GDP 应建立专用 `get_gdp_tools()`，但区分两类能力：

- 内部能力函数：业务节点确定性调用。
- 模型可见工具：LLM 可以选择调用，必须带权限、审批、幂等、审计和输出预算。

建议工具元数据：

```python
class GDPToolSpec(BaseModel):
    name: str
    phase: list[DatagenTaskPhase]
    sideEffectLevel: Literal["NONE", "CONFIG_WRITE", "BUSINESS_WRITE"]
    requiresApproval: bool
    idempotencyKeyFields: list[str]
    outputTarget: Literal["STATE", "TASK_STEP", "TASK_EVENT", "VARIABLE_STACK", "STORAGE_REF"]
    sensitiveOutput: bool = False
```

### 优化目标

GDP 工具不是“让模型能做更多事”，而是“让模型只能做当前阶段允许、可审计、可恢复、可审批的业务动作”。

## 7. 执行边界与沙箱思想

参考文档：`07-沙箱执行系统.md`

### DeerFlow 参考点

DeerFlow 沙箱通过用户/线程目录、虚拟路径、路径校验、输出脱敏、host bash 开关和 provider 隔离，把文件和命令执行变成可治理能力。

### DeerFlow 为什么这样设计

Agent 一旦能读写文件或执行命令，就会涉及用户隔离、敏感路径泄露、并发覆盖、命令逃逸和输出污染。

### GDP 优化方向

GDP 不一定要照搬 `/mnt/user-data` 模型，但应该吸收“执行边界”思想：

- SQL 执行、HTTP 调用、场景运行、脚本处理都要有执行上下文。
- 环境、系统、数据源、endpoint 必须来自受控配置。
- 原始响应和大结果要脱敏、摘要化、外置存储。
- 写操作要有审批和幂等键。
- 错误信息不能暴露敏感连接串、token、真实路径或生产数据。

### 优化目标

让 GDP 的 SQL/HTTP/场景执行像 DeerFlow 沙箱一样有清晰边界：能执行，但只能在授权的环境、资源和策略内执行。

## 8. GDP 子 Agent 与子任务系统

参考文档：`08-子智能体系统.md`

### DeerFlow 参考点

Lead 通过 `task` 工具创建子 Agent，子 Agent 有独立上下文、工具集合、超时、并发限制和结果收敛。

### DeerFlow 为什么这样设计

复杂任务需要分治：父 Agent 不应该把所有细节都塞进一个上下文；子 Agent 能隔离探索、并行执行、减少主上下文膨胀。

### GDP 优化方向

GDP 不应直接复用 Lead 的 `task` 工具。建议建立 `DatagenTaskSubtask`：

- `taskRunId`
- `subtaskId`
- `parentStepId`
- `phase`
- `subagentType`
- `goal`
- `operationId`
- `status`
- `inputSnapshot`
- `resultSummary`
- `resultPayload`
- `resultRef`
- `tokenUsage`
- `errorType/errorMessage`

GDP 子 Agent 类型建议：

- `scene-discovery-agent`
- `source-analysis-agent`
- `sql-source-design-agent`
- `http-source-design-agent`
- `infra-resolver-agent`
- `scene-validation-agent`
- `data-quality-reflection-agent`

### 优化目标

让 GDP 子 Agent 成为可持久化、可恢复、可审计、可限流的业务子任务，而不是进程内临时工具调用。

## 9. GDP 记忆系统

参考文档：`09-记忆系统.md`

### DeerFlow 参考点

DeerFlow memory 不是聊天记录，而是异步、防抖、按用户/Agent 隔离、带置信度的长期事实和摘要。

### DeerFlow 为什么这样设计

记忆同步更新会拖慢当前响应；把所有聊天原文塞进记忆会无限膨胀；上传文件路径等线程级上下文不适合长期保存。

### GDP 优化方向

GDP memory 应记录跨任务可复用偏好和知识：

- 用户常用环境。
- 系统别名。
- 业务域偏好。
- 字段语义映射。
- 常用造数目标表达。
- 审批偏好。
- 常用造数场景。
- 常用基础配置接口。
- 常用 SQL。

但这些不能替代 `TaskRun/TaskStep/TaskEvent`。

更细的 GDP typed memory 分类：

| category | 适合记录的内容 | 参与决策的方式 |
| --- | --- | --- |
| `environment_preference` | 用户常用环境、环境别名、业务域默认环境 | 用户未显式指定环境时作为候选，不能覆盖当前请求。 |
| `system_alias` | 系统别名、业务域到 `sysCode` 的映射 | 补强场景、Source、Infra 搜索 query。 |
| `field_mapping` | 字段语义、入参别名、变量来源偏好 | 字段绑定时作为低于当前输入和变量栈的候选。 |
| `goal_pattern` | 常用造数目标表达和 canonical goal | 把自然语言目标归一化，预测场景链。 |
| `scene_preference` | 常用场景、场景链成功/失败统计 | 场景搜索排序加权，但不能引入无权限或禁用场景。 |
| `source_preference` | 常用 HTTP/SQL Source、基础配置引用 | 缺场景时优先生成或复用常用 Source。 |
| `sql_preference` | 常用 SQL Source、参数语义、数据源引用 | SQL Source 匹配和缺参提示。 |
| `approval_preference` | 审批提示偏好、风险说明偏好 | 影响审批文案，不跳过强制审批。 |
| `correction` | 用户纠错、负反馈、错误资源选择修正 | 高优先级影响排序和候选过滤。 |

GDP memory 不应记录：

- 单次任务产生的订单号、用户号、手机号、身份证、token、cookie、密码、连接串。
- 完整 HTTP 响应、SQL 查询结果、场景执行输出。
- 上传文件路径、临时工作目录和一次性入参。
- 未脱敏 header、body、SQL literal。
- 会绕过审批和权限控制的结论。
- 临时网络失败、偶发错误等不可泛化事实。

中期建议使用 GDP 专用 SQL 表，而不是只复用 Lead 的 `memory.json`：

```text
df_gdp_agent_memory_fact
  id
  user_id
  agent_name
  scope_type          -- USER / AGENT / ENV / SYS / RESOURCE
  scope_key
  category
  memory_key
  value_json
  confidence
  status              -- ACTIVE / DISABLED / SUPERSEDED
  source_task_run_id
  source_event_ids
  evidence_summary
  created_at
  updated_at
  last_used_at
  use_count
  success_count
  failure_count
  expires_at
```

建议的 GDP memory middleware：

1. `GDPMemoryContextMiddleware`：任务开始时按 `user_id + gdp_agent + user_intent + env_code + phase` 检索相关记忆，写入 `GDPState.memory_context` 和 `memory_trace`。
2. `GDPMemoryObservationMiddleware`：从 TaskEvent、TaskStep、用户确认、资源选择、执行结果中提取候选 observation。
3. `GDPMemoryRedactionMiddleware`：入队前脱敏 SQL、HTTP header/body、cookie、token、连接串和敏感字段。
4. `GDPMemoryUpdateQueue`：异步防抖，合并同一任务内 observation，不阻塞当前 run。
5. `GDPMemoryUpdater`：规则提取优先，LLM 只做自然语言泛化，输出 typed memory patch。
6. `GDPMemoryFeedbackMiddleware`：根据任务成功、失败和用户纠错更新 use/success/failure/confidence。

记忆参与 GDP 决策时的优先级：

1. 当前请求显式输入。
2. 本任务用户确认和补充。
3. TaskRun/TaskStep/TaskEvent/VisibleVariables。
4. 高置信 GDP memory。
5. AgentCatalog 和配置库默认匹配。
6. 低置信推断，不足时进入 `WAITING_USER`。

管理 API 应遵守 Datagen GET/POST 风格：

- `GET /api/v1/datagen/agent-memory/facts`
- `POST /api/v1/datagen/agent-memory/facts/create`
- `POST /api/v1/datagen/agent-memory/facts/update`
- `POST /api/v1/datagen/agent-memory/facts/disable`
- `POST /api/v1/datagen/agent-memory/facts/delete`
- `POST /api/v1/datagen/agent-memory/reload`

推荐落地顺序：

1. 先做只读检索上下文：从现有 Task 历史规则查询常用环境、场景、Source、SQL，不自动学习。
2. 再引入 typed memory 表和人工管理能力。
3. 再引入 observation middleware 和异步队列。
4. 最后引入 LLM 泛化和反馈闭环。

### 优化目标

memory 只用于提升默认选择、搜索排序、prompt 上下文和参数建议；任务事实、审计和恢复仍以数据库业务表为准。

## 10. GDP 配置与策略系统

参考文档：`10-配置系统.md`

### DeerFlow 参考点

DeerFlow 把 `config.yaml` 和 `extensions_config.json` 分开：前者是部署核心配置，后者是运行时扩展状态。

### DeerFlow 为什么这样设计

核心配置包含模型、密钥、沙箱、存储等敏感部署项，不应被前端随意写；扩展配置需要 UI/API 管理，修改频率高。

### GDP 优化方向

GDP 应拆分三类配置：

- Gateway/AppConfig 级：模型、存储、SSE、checkpointer、认证、CORS。
- Datagen 业务配置：系统、环境、服务端点、数据源、Source、场景。
- GDP 策略配置：阶段能力、审批策略、工具白名单、MCP policy、skills policy、memory 开关、子任务并发。

### 优化目标

避免把业务配置、运行时连接配置和 Agent 策略混在一起；明确哪些可以热更新，哪些必须重启，哪些必须审批发布。

## 11. GDP MCP 外部能力接入

参考文档：`12-MCP协议集成.md`

### DeerFlow 参考点

Lead MCP 集成提供 MCP server 配置、工具发现、OAuth、interceptor、session pool、deferred tool 和缓存失效。

### DeerFlow 为什么这样设计

外部工具数量多、连接贵、schema 大、授权复杂，需要统一管理会话、缓存、OAuth 和工具暴露面。

### GDP 优化方向

GDP 不应直接暴露原始 MCP tools。建议建立：

```text
backend/app/gdp/agent/mcp/
  config.py
  adapter.py
  registry.py
  middleware.py
  tools.py
```

GDP MCP policy 至少包括：

- `allowedPhases`
- `envCodes`
- `sideEffectLevel`
- `approvalRequired`
- `idempotencyKeyTemplate`
- `outputSensitivity`
- `outputVariablePolicy`
- `auditEventType`

### 优化目标

MCP 对 GDP 是“外部能力接入层”，不是业务步骤本身。所有外部调用都必须绑定 `taskRunId`、phase、env、审批、幂等、TaskEvent 和 visibleVariables。

## 12. GDP Skills 方法论体系

参考文档：`13-Skills技能系统.md`

### DeerFlow 参考点

Lead Skills 用 Markdown 存储方法论，用 front matter 给程序读，用 `allowed-tools` 约束工具，用按需读取避免 prompt 膨胀。

### DeerFlow 为什么这样设计

工具告诉 Agent 能做什么，Skills 告诉 Agent 怎么做得好。方法论不适合写死在 Python 函数里，也不应该默认全量注入。

### GDP 优化方向

建立 GDP 专用 skills：

- `gdp-scene-design`
- `gdp-sql-source-design`
- `gdp-http-source-design`
- `gdp-infra-resolution`
- `gdp-approval-policy`
- `gdp-variable-stack`
- `gdp-task-recovery`

按阶段加载：

```text
SCENE_FULFILLMENT   -> gdp-scene-selection, gdp-variable-stack
SCENE_DESIGN        -> gdp-scene-design, gdp-sql-source-design, gdp-http-source-design
SOURCE_CONFIG       -> gdp-sql-source-design, gdp-http-source-design
INFRA_CONFIG        -> gdp-infra-resolution
SCENE_EXECUTING     -> gdp-approval-policy, gdp-task-recovery
PROGRESS_REFLECTION -> gdp-progress-reflection, gdp-variable-stack
```

### 优化目标

Skills 承载造数方法论，不承载任务事实。GDPState 只保存技能引用和版本；TaskEvent 记录本阶段采用了哪些技能；技能变更走 GDP 专用审批。

## 13. Gateway API 与 GDP 控制面

参考文档：`14-GatewayAPI.md`

### DeerFlow 参考点

Gateway 负责 HTTP、安全、配置、LangGraph runtime、thread/run、SSE、扩展管理、上传和 artifacts。

### DeerFlow 为什么这样设计

Agent 图只应该关心怎么执行任务；请求如何进入系统、如何鉴权、如何启动 run、如何流式返回、如何恢复和取消，应该由 Gateway 控制。

### GDP 优化方向

GDP 已挂在 Gateway 下，应继续复用：

- Auth/CSRF。
- `assistant_id="gdp_agent"` run 创建。
- thread/run/checkpoint。
- SSE heartbeat 和断线处理。
- startup orphan run reconcile。

但 GDP 需要补自己的业务控制面：

- Datagen 专用权限：`datagen:read/write/execute/approve`。
- 资源 owner：`taskRunId`、`createdBy`、`sysCode`、`envCode`、数据源权限。
- Datagen API 保持 GET/POST 风格。
- Pydantic docstring 和 `Field(description=...)` 保持中文契约说明。
- TaskEvent 作为审计和 UI 回放权威，SSE 只是实时镜像。

### 优化目标

Gateway 作为运行时可靠性底座，GDP Datagen API 作为业务控制面。两者职责不混用。

## 14. 分阶段落地路线

### P0：先修复运行时骨架和恢复语义

目标：确保 GDP Agent 长任务不偏离、不遗忘、可恢复。

建议工作：

1. 设计 `GDPState v2` 字段和 reducer。
2. 重构 `make_gdp_agent()`，引入 runtime config、policy、metadata。
3. 建立 GDP middleware 协议和 node wrapper。
4. 先实现 `GDPRuntimeContextMiddleware`、`GDPTaskRunSyncMiddleware`、`GDPTaskEventAuditMiddleware`、`GDPInterruptMiddleware`。
5. 明确 `deerflowThreadId/deerflowRunId/lastCheckpointId` 生命周期。
6. 完善 TaskStep 非终态恢复规则。
7. 修正 `pending_confirmation` 恢复后不清空的问题，避免旧确认残留在 checkpoint。
8. 统一入口输入为 `user_inputs`，逐步废弃 `inputs`。
9. 拆分 `last_tool_result` 为 `decision_context/last_result_ref/result_refs`。
10. 明确节点异常不能吞掉 LangGraph interrupt/control-flow 异常，普通异常统一转 TaskRun FAILED 和 TaskEvent。

验收标准：

- 服务重启后，运行中任务不会永久卡住。
- 用户从 WAITING_USER 恢复时，不从头跑。
- 每个节点开始、结束、失败都有 TaskEvent。
- TaskRun 中能看出当前阶段、最近 run、最近 checkpoint 和下一步恢复动作。
- checkpoint 中不会保留已经消费过的 `pending_confirmation`。
- 节点之间不再依赖未声明结构的 `last_tool_result` 大字典。

### P1：治理副作用、工具、子任务和 memory

目标：让 GDP 能安全扩展更多 LLM 决策和业务动作。

建议工作：

1. 建立 `get_gdp_tools()` 和 `GDPToolSpec`。
2. 对场景执行、Source 保存、Infra 保存加入幂等和审批。
3. 建立 `GDPBusinessGuardrailMiddleware`。
4. 建立 `DatagenTaskSubtask` 表和子任务 middleware。
5. 建立 GDP memory schema，先记录常用环境、系统别名、字段映射、常用 SQL。
6. 建立上下文压缩摘要：目标锚点、计划、变量栈、已完成步骤、未完成目标。
7. 建立 `GDPMemoryContextMiddleware` 和 `memory_trace`，先支持只读检索上下文。
8. 给 SQL/HTTP/场景执行结果增加预览、schema、size 和 storageRef 思路，避免大结果进入 Prompt。

验收标准：

- 副作用工具重复调用不会重复造数或重复保存配置。
- 长子任务可等待、恢复、失败重试或人工介入。
- memory 只影响推荐和注入，不改变 TaskRun 事实。
- LLM prompt 不直接携带大 SQL 结果、完整 HTTP 响应或敏感变量。
- 场景、Source、SQL 候选排序能说明是否受 memory 影响。

### P2：接入 MCP、Skills 和外部能力生态

目标：让 GDP 从本地业务能力扩展到企业外部能力，同时保持审计和恢复。

建议工作：

1. 建立 GDP MCP capability registry。
2. 建立 GDP MCP policy 和 approval/audit middleware。
3. 建立 GDP skills registry，按阶段加载技能。
4. 引入 `allowed-actions` 或 `metadata.gdp`。
5. 建立技能版本和 TaskEvent 审计。
6. 支持子 Agent 调用 MCP，但父 Agent 只接收结构化结果。

验收标准：

- MCP 原始工具不会直接暴露给 GDP 主 Agent。
- 每次外部调用都能追溯 taskRunId、phase、审批、输出变量和事件。
- 技能变更不影响历史任务恢复。
- 子 Agent 完成后父任务只消费摘要、变量和 resultRef。

## 15. 每章后续细化模板

后续如果逐章展开，可以统一使用这个结构：

```text
## 章节标题

### 参考文档

列出对应 DeerFlow 文档和关键源码。

### DeerFlow 设计参考点

说明 DeerFlow 做了什么。

### DeerFlow 为什么这样设计

说明它解决的工程问题。

### 当前 GDP 现状

说明当前 GDP 已有能力、缺口和风险。

### GDP 优化方向

说明要借鉴什么、不能照搬什么、要物理隔离什么。

### 目标设计

给出目标结构、接口、状态字段或流程。

### 落地步骤

按 P0/P1/P2 分拆。

### 验收标准

用可验证条件判断是否完成。
```

## 最终结论

GDP Agent 最应该借鉴 DeerFlow 的，不是某个字段、某个 middleware 类或某个工具函数，而是 DeerFlow 对长时序 Agent 的工程治理方式：

- 状态有生命周期。
- 工厂收敛运行时。
- middleware 承载横切能力。
- 工具有权限、预算和审计。
- 子 Agent 有隔离、限流和结果收敛。
- memory 只记长期偏好，不替代业务事实。
- skills 只承载方法论，不替代任务历史。
- MCP 是外部能力接入层，不是模型自由调用的工具池。
- Gateway 是运行时边界，TaskRun/TaskStep/TaskEvent 是 GDP 业务边界。

因此，GDP Agent 的优化路线应是：复用 Gateway 和 LangGraph runtime，学习 Lead Agent 的生命周期治理，把所有能力重建为 GDP 专用的 state、middleware、tools、memory、skills、MCP 和 subtask 体系。
