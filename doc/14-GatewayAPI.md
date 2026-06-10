# 14 Gateway API

对应字幕：`14-GatewayAPI_哔哩哔哩_bilibili_BV1SVdHBEEhZ_P字幕 (1).srt`

## 本章目标

前面章节都在讲 Agent 内部，这一集从系统边界看请求如何进入 DeerFlow、运行结果如何流回前端。

核心源码：

- `backend/app/gateway/app.py`
- `backend/app/gateway/deps.py`
- `backend/app/gateway/services.py`
- `backend/app/gateway/routers/thread_runs.py`
- `backend/app/gateway/routers/runs.py`
- `backend/app/gateway/routers/threads.py`
- `backend/app/gateway/routers/mcp.py`
- `backend/app/gateway/routers/skills.py`

## Gateway 的职责

当前源码中 Gateway 是 FastAPI 应用，承担：

- 鉴权和 CSRF。
- CORS。
- 初始化 LangGraph runtime 依赖。
- 管理 models、MCP、skills、memory、uploads、artifacts、agents、feedback。
- 提供 LangGraph Platform 兼容的 threads/runs API。
- 创建 run、桥接 SSE、处理取消和等待。
- 维护线程元数据、run 记录、事件存储。

这说明 Gateway 不是简单代理层，而是 DeerFlow 的应用边界。

## FastAPI 入口

`create_app()` 中注册：

- `AuthMiddleware`
- `CSRFMiddleware`
- 可选 `CORSMiddleware`
- 多个 router
- `/health`

`lifespan()` 中做启动初始化：

1. 加载 `AppConfig`。
2. 应用日志等级。
3. 创建 Gateway 配置。
4. 进入 `langgraph_runtime(app, startup_config)`。
5. 检查 admin bootstrap 和孤儿线程迁移。

## `langgraph_runtime`

文件：`deps.py`

它把运行时单例挂到 `app.state`：

- `stream_bridge`
- `checkpointer`
- `store`
- `run_store`
- `feedback_repo`
- `thread_store`
- `run_event_store`
- `run_manager`

注意：`AppConfig` 本身不缓存到 `app.state`。请求级配置通过 `get_config()` -> `get_app_config()` 获取，以支持 `config.yaml` 热重载。持有连接的 runtime 组件则绑定启动时 snapshot。

## Run 创建链路

以流式接口为例：

```text
POST /api/threads/{thread_id}/runs/stream
  -> thread_runs.stream_run()
  -> services.start_run()
  -> run_mgr.create_or_reject()
  -> build_graph_input()
  -> build_run_config()
  -> resolve_agent_factory()
  -> run_agent()
  -> StreamBridge
  -> sse_consumer()
```

`RunCreateRequest` 支持：

- `assistant_id`
- `input`
- `command`
- `metadata`
- `config`
- `context`
- `interrupt_before/after`
- `stream_mode`
- `stream_subgraphs`
- `on_disconnect`
- `multitask_strategy`

这些字段让 Gateway 尽量兼容 LangGraph Platform API，同时扩展 DeerFlow 自己的 context 参数。

## Agent 工厂选择

`resolve_agent_factory()`：

- 如果 `assistant_id` 是 `gdp_agent`，返回 GDP 业务图工厂 `make_gdp_agent`。
- 其他默认返回 `make_lead_agent`。

自定义 Agent 并不是单独的图，而是通过 `assistant_id` 归一化后写入 `agent_name`，由 `make_lead_agent` 在运行时加载对应配置。

## RunnableConfig 构造

`build_run_config()` 做几件事：

- 设置默认 `recursion_limit=100`。
- 合并客户端传入的 `configurable` 或 `context`。
- 注入 `thread_id`。
- 如果是自定义 Agent，注入 `agent_name`。
- 设置 `run_name`。
- 合并 metadata。

`merge_run_context_overrides()` 会把白名单字段同时写入 `configurable` 和 `context`，兼容 LangGraph 新旧版本和工具 runtime 读取方式。

白名单字段包括：

- `model_name`
- `mode`
- `thinking_enabled`
- `reasoning_effort`
- `is_plan_mode`
- `subagent_enabled`
- `max_concurrent_subagents`
- `agent_name`
- `is_bootstrap`

## SSE 流式输出

`format_sse()` 输出格式：

```text
event: <event>
data: <json>
id: <event_id>

```

`sse_consumer()` 从 `StreamBridge.subscribe()` 读取事件：

- heartbeat 输出 `: heartbeat`
- END_SENTINEL 输出 `event: end`
- 普通事件按 LangGraph Platform 格式输出

`on_disconnect` 控制断开行为：

- `cancel`：取消后台 run。
- `continue`：后台继续，事件丢弃。

字幕里强调 Nginx `proxy_buffering off` 的价值是对的：SSE 必须及时 flush，如果代理缓冲，前端就不能实时看到 Agent 进度。

## Threads API

`routers/threads.py` 管线程：

- `POST /api/threads` 创建线程。
- `POST /api/threads/search` 搜索线程。
- `GET /api/threads/{thread_id}` 获取线程。
- `GET /api/threads/{thread_id}/state` 获取最新状态。
- `POST /api/threads/{thread_id}/state` 更新状态，用于 human-in-the-loop resume 或标题更新。
- `POST /api/threads/{thread_id}/history` 获取 checkpoint 历史。
- `DELETE /api/threads/{thread_id}` 删除线程本地数据、checkpoint 和 thread_meta。

线程 metadata 会剥离 `owner_id/user_id` 等服务端保留字段，防止客户端伪造所有者。

## Runs API

`routers/thread_runs.py` 提供线程内 run：

- 创建 run。
- stream run。
- wait run。
- list/get/cancel/join run。
- 读取 run messages/events/token usage。

`routers/runs.py` 提供无预创建 thread 的 stateless run，会自动生成临时 thread_id，或者复用请求中的 `config.configurable.thread_id`。

## 扩展管理 API

Gateway 还提供：

- MCP 配置 GET/PUT，带敏感字段 masking 和 secret preservation。
- Skills 列表、启用、安装、编辑、历史、回滚。
- Memory 读取、导入、清空、fact 增删改。
- Uploads 上传和多格式转换。
- Artifacts 访问生成文件。
- Agents 自定义 Agent 管理。

这些都是不应该放进 LangGraph Agent 执行图里的应用边界能力。

## 本章结论

Gateway API 是 DeerFlow 的系统边界：它把 HTTP、鉴权、配置管理、文件上传、线程/run 元数据、SSE 和 LangGraph Agent 运行时连接起来。Lead Agent 专注“怎么执行任务”，Gateway 专注“请求如何安全、稳定、可观测地进入和离开系统”。

## 结合当前源码的补充分析

### 1. Gateway 是运行时控制面，不只是 LangGraph HTTP 壳

当前 `backend/app/gateway/app.py` 里，Gateway 同时挂载 DeerFlow 通用路由和 GDP 业务路由：

- 通用控制面：`models`、`mcp`、`memory`、`skills`、`artifacts`、`uploads`、`threads`、`runs`、`agents`、`feedback` 等。
- LangGraph Platform 兼容面：`/api/threads`、`/api/runs`、`/api/assistants`。
- GDP 业务面：`app.include_router(gdp_router)`，而 `gdp_router` 的前缀是 `/api/v1/datagen`。

这说明 GDP 不是绕过 Gateway 另起一个服务，而是已经被纳入 Gateway 的应用边界。这个设计是合理的：鉴权、CSRF、持久化初始化、LangGraph checkpointer/store、run manager、SSE bridge 都可以复用 Gateway 的成熟基础设施。

但这里也要划清边界：Gateway 只应该做“运行时控制面”和“HTTP 应用边界”，不能替代 GDP 的业务状态机。GDP 的业务事实仍应以 `TaskRun/TaskStep/TaskEvent/visibleVariables` 为准，Gateway 的 thread/run/checkpoint/event 是 Agent 运行时事实。

### 2. 配置热加载边界

`backend/app/gateway/deps.py` 的设计有一个重要细节：`AppConfig` 没有直接缓存到 `app.state`，请求级依赖通过 `get_config()` 调 `get_app_config()`，因此 `config.yaml` 可以热加载。

但 `langgraph_runtime(app, startup_config)` 创建的持连接组件是启动时快照：

- `stream_bridge`
- `checkpointer`
- `store`
- `run_store`
- `feedback_repo`
- `thread_store`
- `run_event_store`
- `run_manager`

其中 `run_events_config` 和 `run_event_store` 还刻意冻结在 startup snapshot，避免热加载后出现“新配置写旧存储”或“旧事件源读新配置”的 split-brain。

对 GDP 的启发是：配置要分层。

- Gateway/AppConfig 级配置：模型白名单、运行时存储、事件存储、CORS、鉴权等，涉及连接和长期对象的变更应要求重启。
- GDP 业务配置：系统、环境、服务端点、数据源、HTTP Source、SQL Source、场景定义等，应通过 Datagen API 和数据库热更新。
- GDP Agent 运行配置：任务的 `envCode`、`userIntent`、`visibleVariables`、`goalStack`、`plan` 应进入 TaskRun 业务状态，不应塞进 Gateway AppConfig。

这样才能避免把“基础设施配置热加载”和“造数业务配置热更新”混为一谈。

### 3. 安全边界：Auth、CSRF、权限和 owner

Gateway 的安全设计不是只靠路由里手写判断，而是分层完成：

- `AuthMiddleware` 对非公开路径 fail-closed，公共路径只包括 `/health`、docs/openapi、少量 auth bootstrap 接口。
- 鉴权成功后写入 `request.state.user`、`request.state.auth`，同时设置 DeerFlow 的 `user_context`，让仓储层可以做 owner 过滤。
- `CSRFMiddleware` 对状态变更方法做 double-submit cookie 校验，并对 auth POST 做 origin 校验，防止 login CSRF/session fixation。
- `require_permission()` 在 threads/runs 等路由上做权限检查和 owner_check，变更类接口通常要求 `require_existing=True`，避免已删除或未纳管 thread 被继续操作。

GDP 当前挂在 Gateway 下，所以已经继承了全局 Auth/CSRF 保护；同时从 `backend/app/gdp/datagen/config/task/api.py` 看，创建任务时会通过 `get_current_user()` 把当前用户写入 `createdBy`。

但 GDP 还没有像 threads/runs 那样形成显式的 Datagen 权限模型和资源 owner 校验。开发阶段可以接受；如果进入多人协作或生产环境，建议补一层 GDP 专用权限：

- `datagen:read`：读取任务、场景、Source、基础配置。
- `datagen:write`：创建或修改场景、Source、基础配置。
- `datagen:execute`：创建任务、继续任务、执行场景。
- `datagen:approve`：审批或确认高风险造数动作。

资源 owner 也应以 GDP 业务资源为单位，而不是直接复用 thread owner。典型 owner 维度包括 `taskRunId`、`createdBy`、`sysCode`、`envCode`、数据源权限和审批域。

### 4. Run 生命周期和 GDP 接入方式

Gateway 的 run 创建链路集中在 `backend/app/gateway/services.py`：

```text
start_run()
  -> 校验 model_name 是否在 allowlist
  -> run_mgr.create_or_reject()
  -> build_graph_input()
  -> build_run_config()
  -> resolve_agent_factory()
  -> inject_authenticated_user_context()
  -> asyncio.create_task(run_agent(...))
```

这里有几个关键点：

- `normalize_input()` 会把客户端 message 转成 LangChain message，避免 API 层直接把任意结构塞进图。
- `build_graph_input()` 支持 `input` 和 `command`，其中 `command` 用于 LangGraph interrupt resume。
- `build_run_config()` 同时兼容 `context` 和 `configurable`，并注入 `thread_id`、`run_name`、metadata。
- `resolve_agent_factory()` 根据 `assistant_id` 选择图工厂，`gdp_agent` 会进入 `make_gdp_agent`，其他默认进入 `make_lead_agent`。
- `inject_authenticated_user_context()` 服务端注入用户上下文，不信任客户端传入的 user_id。

GDP 任务控制面已经在使用这条链路：

- `POST /tasks/runs/{taskRunId}/continue` 创建 `RunCreateRequest(assistant_id="gdp_agent", input={"task_run_id": taskRunId}, on_disconnect="continue")`。
- `POST /tasks/runs/{taskRunId}/user-reply` 在任务处于 `WAITING_USER` 时创建 `RunCreateRequest(assistant_id="gdp_agent", command={"resume": body.reply})`。
- 创建成功后通过 `bind_deerflow_run()` 把 `deerflowRunId` 绑定回 TaskRun，并记录 `CONTINUE_RUN_REQUESTED` 或 `RESUME_REQUESTED` 事件。

这个设计方向是对的：GDP 不自己造一套 LangGraph run runtime，而是通过 Gateway 的 run manager 启动和恢复业务图。

需要注意的是，`RunCreateRequest` 的 schema 暴露了 `multitask_strategy` 的 `"enqueue"`，但当前 `RunManager.create_or_reject()` 实际支持的是 `reject`、`interrupt`、`rollback`。GDP 现在使用 `reject`，这对“同一个任务同一时刻只允许一个 GDP run 推进”是合理的；如果后续要支持任务队列或父 Agent 等待子 Agent，不能简单依赖 `enqueue`，需要先把 runtime 层的排队语义真正补齐，或者在 GDP Task 层实现业务队列。

### 5. SSE/Event 边界

Gateway 的流式输出通过 `StreamBridge` 和 `sse_consumer()` 实现：

- 支持 `Last-Event-ID` 断线重放。
- 支持 heartbeat，避免长任务期间连接被认为空闲。
- 结束时输出 `event: end`。
- 响应头设置 `Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`。
- `on_disconnect=cancel` 时断开会取消后台 run，`on_disconnect=continue` 时后台继续执行。

这套机制解决的是“前端如何实时看到 Agent run 的输出”。它不是业务审计来源。

对 GDP 来说，`TaskEvent` 应是审计和回放权威，Gateway SSE 是实时镜像。推荐关系是：

```text
GDP Agent 节点推进业务
  -> 写 TaskRun/TaskStep/TaskEvent
  -> Gateway/LangGraph SSE 推送实时状态
  -> 前端可用 SSE 提升实时体验，但刷新和恢复必须回读 TaskRun/TaskStep/TaskEvent
```

这样即使 SSE 断线、浏览器刷新、Gateway 进程重启，用户仍能从 GDP 业务表恢复任务进度。

### 6. Thread/checkpoint API 的定位

`backend/app/gateway/routers/threads.py` 提供了线程创建、搜索、状态读取、状态更新和 checkpoint history。它还会剥离 `owner_id/user_id` 等服务端保留 metadata，避免客户端伪造所有者。

这对 Lead Agent 很重要，因为 Lead 的上下文主要就是 thread state、messages、todos、artifacts、sandbox 等。GDP 的情况不同：GDP 的关键业务状态已经在数据库任务表里，包括：

- `userIntent`
- `normalizedGoal`
- `envCode`
- `status`
- `phase`
- `pendingInterrupts`
- `goalStack`
- `plan`
- `visibleVariables`
- `reflection`
- `finalSummary`

因此 GDP 不应把 Gateway checkpoint 当业务数据库用。更合适的定位是：

- checkpoint 负责 LangGraph 节点级恢复。
- TaskRun 负责业务级恢复。
- TaskStep 负责步骤级断点和执行结果。
- TaskEvent 负责审计、排障和 UI 回放。

`DatagenTaskRunResponse` 里已经预留 `deerflowThreadId`、`deerflowRunId`、`lastCheckpointId`。后续如果要做到“异常中断后只从中断步骤继续运行”，需要把这三个字段的生命周期写完整：

- 创建 TaskRun 时确定或绑定 `deerflowThreadId`。
- 每次提交 GDP Agent run 时更新 `deerflowRunId`。
- GDP run 完成、interrupt 或关键节点落点时更新 `lastCheckpointId`。
- 恢复时优先读 TaskRun/TaskStep 判断业务断点，再用 thread/checkpoint 恢复 LangGraph 运行点。

### 7. Datagen API 的形态评估

`backend/app/gdp/router.py` 把 GDP 业务 API 聚合在 `/api/v1/datagen` 下：

- 基础配置：系统、环境、服务端点、数据源。
- Source 配置：HTTP Source、SQL Source。
- 场景配置：场景创建、更新、校验、发布、运行。
- 任务控制面：TaskRun 创建、继续、取消、用户回复、步骤、事件、摘要。
- Agent 能力目录：场景契约、Source 契约、基础配置解析。
- Agent 辅助接口：草稿生成、Source 保存、配置解析、测试执行。

从当前路由扫描看，GDP/Datagen 路由已经基本遵守“只使用 GET/POST”的风格：

- 查询类接口使用 GET，例如 `/tasks/runs`、`/tasks/runs/{taskRunId}`、`/tasks/runs/{taskRunId}/events`。
- 搜索、创建、更新、删除、禁用、执行、继续、取消、用户回复都使用 POST。
- 没有像 Gateway 通用管理 API 那样使用 PUT/DELETE/PATCH。

这个差异应该保留。Gateway 为了兼容 LangGraph Platform 和通用资源管理，可以保留 PUT/DELETE/PATCH；GDP/Datagen 作为业务 API，应继续按项目约束使用 GET/POST，修改和删除统一用 POST + JSON body。

Pydantic 契约也应继续保持当前方向：类 docstring 写整体用途，字段用 `Field(description=...)` 写前端/后端契约和运行时含义。`DatagenTaskRunResponse`、`VisibleVariable`、`DatagenTaskEventResponse` 这类模型已经体现了这个风格，后续新增 GDP API 不应退回到无说明字段。

### 8. Gateway 机制对 GDP Agent 的借鉴边界

| Gateway 机制 | GDP 是否应借鉴 | 建议 |
| --- | --- | --- |
| Auth/CSRF | 应直接继承 | GDP 已挂在 Gateway 下，继续复用全局中间件。 |
| threads/runs API | 应作为运行时外壳复用 | GDP 不要自建 LangGraph run runtime，继续通过 `assistant_id="gdp_agent"` 接入。 |
| RunManager 并发策略 | 可借鉴但不能高估 | 当前适合防止同一 thread 并发推进；排队和父子 Agent join 需要另做业务层设计。 |
| StreamBridge/SSE | 应复用实时能力 | SSE 只做实时展示，TaskEvent 才是可恢复审计。 |
| Thread checkpoint | 应用于图恢复 | 不应替代 TaskRun/TaskStep/TaskEvent。 |
| MCP/Skills/Memory API | 借鉴控制面形态 | GDP 的能力目录、常用配置、记忆和技能应有自己的业务边界。 |
| Gateway 通用 PUT/DELETE/PATCH 风格 | 不应复制到 Datagen | Datagen 继续坚持 GET/POST。 |

### 9. 对长任务、子 Agent 和恢复能力的建议

用户关注的核心目标是：Agent 不能偏离任务目标，不能遗忘用户目标，异常中断后能从中断步骤继续，而不是从头开始。

Gateway 只能解决其中一部分：

- 通过 thread/checkpoint 解决 LangGraph 运行点恢复。
- 通过 RunManager 解决 run 级状态、取消和冲突。
- 通过 SSE bridge 解决实时事件推送和断线重放。
- 通过 startup reconcile 把孤儿 running/pending run 标记为 error，避免 UI 永远显示运行中。

GDP 还需要在业务层补齐：

- 父任务目标：`TaskRun.userIntent`、`normalizedGoal`、`goalStack` 必须在每个阶段可读。
- 步骤断点：每个可恢复步骤都应落 `TaskStep`，状态从 `PENDING/RUNNING/WAITING_USER` 推进到终态。
- 子 Agent 协作：父 `TaskStep` 应记录子 agent 的 `deerflowThreadId/deerflowRunId/taskRunId`、join 状态、结果摘要和失败原因。
- 长时间等待：主 Agent 等待子 Agent 或外部审批时，应把 TaskRun 置为 `WAITING_USER` 或新的等待阶段，而不是让一个 run 长时间空转。
- 恢复入口：恢复时先读 TaskRun 和最新非终态 TaskStep，再决定是 `Command(resume=...)`、重新提交 GDP run，还是只继续业务队列。
- 审计回放：所有关键动作都写 TaskEvent，UI 刷新后从 TaskEvent 重建进度，而不是依赖上一次 SSE 是否完整收到。

换句话说，Gateway 给 GDP 提供“运行时可靠性底座”，但 GDP 的“任务目标保持、步骤恢复、父子 Agent 编排”必须落在 Datagen Task 控制面。

## 本章对 GDP 的最终结论

Gateway API 的设计是合理且值得 GDP 复用的，尤其是 Auth/CSRF、run 创建、thread/checkpoint、SSE、断线处理和 orphan run 恢复。但 GDP 不能把 Gateway 当作业务状态中心。

更优雅的 GDP 设计应该是：

```text
Gateway
  负责 HTTP、安全、LangGraph runtime、SSE、thread/run/checkpoint

GDP Datagen API
  负责造数任务、场景、Source、基础配置、能力目录、业务权限

GDP Agent
  负责读取 TaskRun 目标，推进 TaskStep，写 TaskEvent，更新 visibleVariables

GDP middleware/state
  负责把用户目标、任务状态、记忆、压缩消息、工具上下文注入 Agent 运行
  但不取代 TaskRun/TaskStep/TaskEvent 的业务权威地位
```

这也是 GDP 借鉴 DeerFlow Lead Agent 时最重要的边界：基础设施复用 Gateway，Agent 编排可学习 Lead，中间件可以参考 Lead 甚至复制代码后物理隔离；但业务事实、恢复语义、权限模型和造数能力目录必须由 GDP 自己定义。
