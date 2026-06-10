# 04 LeadAgent 工厂模式

对应字幕：`04-LeadAgent工厂模式_哔哩哔哩_bilibili_BV1SVdHBEEhZ_字幕.srt`

## 本章目标

这一集讲 `make_lead_agent` 为什么是工厂函数，而不是启动时创建一个全局单例 Agent。

主要源码：

- `backend/packages/harness/deerflow/agents/lead_agent/agent.py`
- `backend/packages/harness/deerflow/agents/factory.py`
- `backend/app/gateway/services.py`

## 两个工厂函数

源码里有两层工厂。

### `create_deerflow_agent`

文件：`backend/packages/harness/deerflow/agents/factory.py`

这是 SDK 级纯参数工厂，输入是 `model`、`tools`、`system_prompt`、`features`、`middleware`、`checkpointer` 等普通 Python 参数。它不主动读取 YAML，也不依赖全局配置，适合测试和嵌入。

它的设计重点是：

- `middleware` 表示完全接管中间件链。
- `features` 表示声明式开启默认能力。
- `extra_middleware` 通过 `@Next` / `@Prev` 插入到默认链。
- 默认 `state_schema` 是 `ThreadState`。

### `make_lead_agent`

文件：`backend/packages/harness/deerflow/agents/lead_agent/agent.py`

这是应用级图工厂，签名是：

```python
def make_lead_agent(config: RunnableConfig):
```

它兼容 LangGraph Server / Gateway 的调用方式，只接收一个 `RunnableConfig`。真正的实现委托给 `_make_lead_agent(config, app_config=...)`。

## 为什么不是全局单例

全局单例会破坏 DeerFlow 的几个核心需求：

- 每请求模型选择：请求可以传 `model_name`、`thinking_enabled`、`reasoning_effort`。
- 自定义 Agent：不同 `agent_name` 对应不同配置、技能和工具组。
- 热重载：`get_app_config()` 会按 `config.yaml` mtime 重新加载配置。
- 无共享可变状态：每个请求构造自己的 graph/runtime 组合，避免并发污染。

如果把 Agent 做成单例，模型、工具、技能、middleware 这些运行时选项都会变成共享状态，多个用户请求会互相影响。

## 动态参数怎么进来

Gateway 在 `app.gateway.services.build_run_config()` 中构造 `RunnableConfig`。关键参数放入：

- `config["configurable"]`
- 或 LangGraph 新版本推荐的 `config["context"]`

`_get_runtime_config()` 会把两者合并：

```python
cfg = dict(config.get("configurable", {}) or {})
context = config.get("context", {}) or {}
if isinstance(context, dict):
    cfg.update(context)
```

这样老路径和新路径都能读到同一批运行时参数。

## 模型解析顺序

`_resolve_model_name()` 的优先级：

1. 请求中的 `model_name` 或 `model`。
2. 自定义 Agent 配置里的 `model`。
3. `config.yaml` 中 `models:` 列表第一个模型。

如果请求的模型不在配置里，会回退到默认模型并记录 warning。这样前端传错模型不会导致整个运行时崩溃。

## 工具和技能绑定

`_make_lead_agent()` 会：

1. 读取 `agent_name` 对应的自定义 Agent 配置。
2. 解析可用技能集合。
3. 调用 `get_available_tools()` 加载工具。
4. 使用 `filter_tools_by_skill_allowed_tools()` 根据技能 `allowed-tools` 过滤工具。
5. 传入 `create_agent()`。

自定义 Agent 不是另一套运行时，而是同一个 Lead Agent 工厂根据 `agent_name` 加载不同配置。

## 中间件组装

`_build_middlewares()` 根据配置和请求参数组装链条，包含：

- 基础运行时中间件：线程数据、上传、沙箱、错误处理、审计等。
- 动态上下文中间件。
- 摘要中间件。
- 计划模式 `TodoMiddleware`。
- token 使用统计。
- 自动标题。
- 记忆。
- 图像注入。
- 延迟工具过滤。
- 子 Agent 并发限制。
- 循环检测。
- 自定义中间件。
- 安全 finish reason 处理。
- 最后的 `ClarificationMiddleware`。

这个顺序不是随意的，后续中间件章节会细讲。

## 和 Gateway 的关系

HTTP 请求不会直接调用 `make_lead_agent`。实际链路是：

```text
POST /api/threads/{thread_id}/runs/stream
  -> thread_runs.stream_run()
  -> services.start_run()
  -> resolve_agent_factory()
  -> make_lead_agent()
```

`start_run()` 同时负责创建 `RunRecord`、合并上下文参数、注入认证用户、启动后台 `run_agent()` 任务，并把事件交给 `StreamBridge`。

## 本章结论

Lead Agent 的工厂模式服务于动态运行时，而不是为了“设计模式好看”。DeerFlow 每个请求都需要根据模型、Agent、技能、工具组、plan mode、subagent 开关、用户和线程上下文组装不同的执行图。工厂函数让这些差异局部化，同时避免全局单例带来的并发污染。

## 结合当前源码的补充分析

从当前源码看，Lead Agent 的工厂模式不是单一函数，而是两层边界：

- `backend/packages/harness/deerflow/agents/factory.py` 里的 `create_deerflow_agent()` 是 SDK 级工厂。
- `backend/packages/harness/deerflow/agents/lead_agent/agent.py` 里的 `make_lead_agent()` 是应用级工厂。

这两层解决的问题不同。`create_deerflow_agent()` 尽量只接受普通 Python 参数，不主动读取 YAML，也不绑定全局单例；它的目标是把 `langchain.agents.create_agent()` 包成一个可复用、可测试的 DeerFlow Agent 构造器。`make_lead_agent()` 则站在 Gateway / LangGraph Server 的请求边界上，把每次运行的动态配置、用户上下文、模型、工具、技能、中间件、Prompt、Tracing 元数据全部解析成一次具体的图实例。

### 应用级工厂的生命周期边界

`make_lead_agent(config)` 先调用 `_get_runtime_config()` 合并两类运行时参数：

- `config["configurable"]`：旧路径或部分调用方仍在使用。
- `config["context"]`：LangGraph 新版本推荐的运行时上下文。

这个合并动作很关键。后续所有运行时决策都从同一个 `cfg` 读取，避免同一参数在不同调用链里有两种来源。`make_lead_agent()` 还允许调用方通过 runtime context 注入 `app_config`；没有注入时才回退到 `get_app_config()`。这让测试、LangGraph Server、Gateway 热加载配置可以走同一条工厂路径。

进入 `_make_lead_agent(config, app_config)` 后，Lead Agent 会在一次构造过程中完成这些决策：

1. 解析 `thinking_enabled`、`reasoning_effort`、`model_name/model`、`is_plan_mode`、`subagent_enabled`、`max_concurrent_subagents`、`is_bootstrap`。
2. 通过 `validate_agent_name()` 校验 `agent_name`，避免自定义 Agent 名称直接进入文件路径。
3. 非 bootstrap 模式下用 `load_agent_config(agent_name)` 读取自定义 Agent 配置。
4. 计算当前 Agent 可见的技能集合：bootstrap 只能看到 `bootstrap`，自定义 Agent 可用自己的 `skills` 白名单，默认 Agent 可见所有启用技能。
5. 按“请求模型 > 自定义 Agent 模型 > 全局默认模型”的顺序解析模型。
6. 如果请求打开 thinking，但实际模型不支持 thinking，则降级关闭 thinking 并记录 warning。
7. 构造工具列表、技能策略过滤、中间件链和最终系统 Prompt。

这里的设计精髓是：所有“本次运行是什么样的 Agent”都在工厂边界一次性决定，而不是散落到节点、工具或中间件里临时判断。

### metadata 和 callbacks 不是装饰项

`_make_lead_agent()` 会主动修改 `config["metadata"]`，写入：

- `agent_name`
- `model_name`
- `thinking_enabled`
- `reasoning_effort`
- `is_plan_mode`
- `subagent_enabled`
- `tool_groups`
- `available_skills`

这些字段不是业务状态，而是观测和运行时解释所需的元数据。它们应该跟随 LangGraph run 进入 tracing、日志和调试链路，但不应该进入 `ThreadState` 参与模型上下文演化。

同一个函数还把 `build_tracing_callbacks()` 追加到 `config["callbacks"]`。源码文件顶部专门写了 tracing invariant：Tracing callback 必须挂在图调用根部，图内部所有 `create_chat_model(...)` 都必须传 `attach_tracing=False`。原因有两个：

- 避免图根和模型层各自创建一套重复 span。
- 保证 Langfuse 这类 handler 能在 root chain start 时传播 `session_id/user_id` 等属性。

这说明 Lead Agent 工厂承担了“观测根”的职责。Tracing 不应该由每个节点、每个模型调用自己随手挂，否则很容易出现重复 trace 或用户/线程信息丢失。

### Prompt 和技能不是静态字符串拼接

`apply_prompt_template()` 根据 `subagent_enabled`、`max_concurrent_subagents`、`agent_name`、`available_skills` 和 `app_config` 生成最终系统 Prompt。它不是简单模板替换，而是在工厂解析出的能力边界基础上决定：

- 是否注入 subagent 编排说明。
- subagent 并发上限写入 Prompt。
- 当前 Agent 能看到哪些 skill。
- 是否暴露 deferred tools。
- 自定义 Agent 是否注入 `SOUL.md` 和 self-update 规则。

同时，当前日期和 memory 没有直接拼进静态系统 Prompt，而是通过 `DynamicContextMiddleware` 以 `<system-reminder>` 注入到首条 HumanMessage。源码注释明确说明这样可以让系统 Prompt 更稳定，利于 prefix cache 复用。这是一个容易忽略的细节：工厂负责生成稳定的大 Prompt，中间件负责注入每轮变化的小上下文。

### SDK 级工厂的价值

`create_deerflow_agent()` 的价值在于把“怎么组装 DeerFlow 风格 Agent”沉到一个纯参数 API：

- 如果传 `middleware`，表示完全接管中间件链。
- 如果传 `features`，表示声明式启用默认能力。
- 如果传 `extra_middleware`，通过 `@Next` / `@Prev` 插入默认链。
- 默认 `state_schema` 是 `ThreadState`。
- 默认组装会按 feature 注入工具，例如 `view_image`、`task`、`ask_clarification`。

`RuntimeFeatures` 的默认值也体现了 DeerFlow 对默认运行时的判断：`sandbox=True`、`loop_detection=True`，但 `memory=False`、`summarization=False`、`subagent=False`、`vision=False`、`auto_title=False`。也就是说，SDK 工厂默认提供安全执行和循环保护，但不会默认打开会改变上下文、成本或行为边界的能力。

`extra_middleware` 的插入算法也不是简单 append。`_insert_extra()` 会检查：

- 同一个 middleware 不能同时声明 `@Next` 和 `@Prev`。
- 多个外部 middleware 不能抢同一个 anchor。
- anchor 找不到要报错。
- 外部 middleware 之间出现循环依赖要报错。
- 未声明位置的外部 middleware 默认插到 `ClarificationMiddleware` 前面。
- 插入后仍强制 `ClarificationMiddleware` 留在最后。

这说明 DeerFlow 把 middleware 顺序当成运行时契约，而不是可随意调整的列表。尤其是 Clarification 最后，是因为它需要在模型和其他 middleware 都处理完后统一拦截澄清请求。

### bootstrap、默认 Agent、自定义 Agent 是同一工厂的三种分支

Lead Agent 没有为 bootstrap、默认 Agent、自定义 Agent 各写一套运行时，而是在同一个应用级工厂里分支：

- bootstrap：只允许 bootstrap skill，额外暴露 `setup_agent`，使用最小化初始化能力。
- 默认 Agent：没有 `agent_name`，不能看到 `update_agent`。
- 自定义 Agent：读取用户隔离目录下的配置和 `SOUL.md`，可以使用 `update_agent` 更新自己的配置。

这种设计的好处是能力差异集中在工厂，不会让工具层、中间件层、Prompt 层各自判断“我现在是不是 bootstrap / custom”。这也是工厂模式在 DeerFlow 里的实际价值：把运行时分支收敛在入口。

## 对 GDP Agent 工厂的设计启发

当前 GDP Agent 的工厂在 `backend/app/gdp/agent/graph.py`。它和 Lead Agent 的差异非常大：

```python
def make_gdp_agent(config: RunnableConfig, app_config: AppConfig):
    _ = (config, app_config)
    return make_gdp_graph(_build_services())
```

也就是说，当前 `config` 和 `app_config` 基本没有参与 GDP 图构造。`make_gdp_graph()` 只接收 `GDPAgentServices` 和可选 `checkpointer`，然后固定注册 `intake`、`scene_fulfillment`、`scene_design`、`human_confirm`、`source_config`、`infra_config`、`scene_execute`、`progress_reflection` 这些业务节点。

这个设计对原型阶段是可接受的：GDP 图现在更像确定性业务流程图，核心状态也主要落在 `TaskRun/TaskStep/TaskEvent`，而不是依赖一条很长的聊天消息历史。但如果要向生产级 Agent 编排演进，GDP 工厂需要借鉴 Lead Agent 的分层思想，而不是直接复用 Lead Agent 的 `create_agent(..., middleware=...)`。

### 为什么 GDP 不能直接套 Lead Agent 工厂

Lead Agent 是 LangChain `create_agent()` 创建的通用对话 Agent，它的 middleware 类型是 `langchain.agents.middleware.AgentMiddleware`，主要围绕模型调用、工具调用、消息历史和 Agent state 运行。

GDP Agent 当前是 `StateGraph(GDPState)`，节点是确定的业务阶段，每个节点通过 `DatagenTaskService`、`SceneService`、`AgentCatalogService` 等服务读写数据库。它的权威状态不是 `messages`，而是：

- `DatagenTaskRunResponse`：任务目标、环境、阶段、变量栈、计划、中断、反思、完成/失败状态。
- `DatagenTaskStepResponse`：每一步执行的业务记录。
- `DatagenTaskEventResponse`：审计事件和可回放事件流。
- `GDPState`：图运行时的轻量路由状态和临时结果。

所以 GDP 不应该为了复用 Lead Agent middleware，把自身改造成通用聊天 Agent。更合理的方式是建立一套 GDP 专用 middleware 链，物理隔离在 `app/gdp/agent/middlewares` 之类的目录下，借鉴 Lead Agent 的顺序治理、开关治理、观测治理和生命周期治理。

### GDP 工厂应该借鉴的不是字段数量，而是生命周期归属

Lead Agent 的 `ThreadState` 字段多，是因为它要承载通用 Agent 的上传文件、沙箱、图片、artifact、todo、thread data 等生命周期。GDPState 的优雅设计不应该变成“复制 ThreadState 的字段”，而应该是每个字段都能回答三个问题：

1. 这个字段由谁创建。
2. 这个字段什么时候更新或清空。
3. 中断恢复时这个字段是否必须从 checkpoint 恢复，还是可以从数据库重建。

按这个标准，GDP 工厂应该把运行期信息分层：

- 图状态层：`task_run_id`、`current_phase`、`last_tool_result`、`pending_confirmation` 这类驱动路由和节点衔接的短生命周期字段。
- 业务事实层：`TaskRun/TaskStep/TaskEvent`，作为恢复、审计、前端展示和幂等判断的权威来源。
- 运行元数据层：`thread_id`、`run_id`、`checkpoint_id`、`user_id`、`model_name`、`env_code`、`task_run_id`，进入 `config["metadata"]` 和日志/tracing，不应随意塞进 Prompt。
- 可注入上下文层：用户偏好、常用环境、系统别名、字段语义映射、常用 SQL、常用造数配置等，后续可以通过 GDP memory middleware 注入。

这和 Lead Agent 的设计原则是一致的：字段多少不是重点，生命周期清晰才是重点。

### GDP 应该形成自己的应用级工厂

建议 GDP 后续把现在的单层工厂拆成更明确的内部步骤：

```python
def make_gdp_agent(config: RunnableConfig, app_config: AppConfig):
    runtime = _get_gdp_runtime_config(config)
    services = _build_gdp_services(app_config=app_config, runtime=runtime)
    middlewares = _build_gdp_middlewares(app_config=app_config, runtime=runtime)
    _attach_gdp_metadata(config, runtime)
    _attach_gdp_tracing_callbacks(config, app_config)
    return create_gdp_graph(
        services=services,
        middlewares=middlewares,
        checkpointer=runtime.checkpointer,
        app_config=app_config,
    )
```

这里的函数名字只是表达职责，不要求一次性全部实现。关键是把职责拆开：

- `_get_gdp_runtime_config()`：合并 `configurable/context`，解析 `task_run_id`、`thread_id`、`user_id`、`env_code`、`model_name`、是否启用子任务、是否启用 memory、是否启用压缩。
- `_build_gdp_services()`：构造或注入 `DatagenTaskService`、`SceneService`、`AgentCatalogService` 等依赖，减少 `_build_services()` 对全局 session factory 的隐藏依赖。
- `_build_gdp_middlewares()`：组装 GDP 专用 middleware 链。
- `_attach_gdp_metadata()`：把 `agent_name="gdp"`、`task_run_id`、`env_code`、`phase`、`model_name`、`subtask_enabled` 等写入 tracing metadata。
- `_attach_gdp_tracing_callbacks()`：沿用 Lead Agent 的根级 tracing 原则，避免节点内部 LLM 调用各自挂 tracing。
- `create_gdp_graph()`：只负责注册节点、边、条件路由和 node wrapper。

这会让 GDP 的工厂从“返回一个固定图”升级为“按本次任务上下文组装一个业务 Agent runtime”。

### GDP middleware 应该是图节点包装器，而不是 AgentMiddleware

因为 GDP 是 `StateGraph`，推荐定义 GDP 自己的 middleware 协议，例如：

```python
class GDPGraphMiddleware(Protocol):
    async def before_node(self, node_name, state, config): ...
    async def after_node(self, node_name, state, result, config): ...
    async def on_node_error(self, node_name, state, error, config): ...
```

然后在 `make_gdp_graph()` 注册节点时统一包装：

```python
workflow.add_node("scene_execute", wrap_gdp_node("scene_execute", node, middlewares))
```

这样可以借鉴 Lead Agent 的 middleware 链治理，但不会把 GDP 业务图绑死在 LangChain AgentMiddleware 生命周期上。GDP middleware 可以优先解决这些问题：

- `TaskRunSyncMiddleware`：节点前从数据库刷新任务状态，节点后把 checkpoint/run 绑定回 TaskRun。
- `TaskEventAuditMiddleware`：统一记录节点开始、结束、异常事件。
- `GDPInterruptMiddleware`：统一把 WAITING_USER、pending interrupt、Command resume 映射到任务控制面。
- `GDPRecoveryMiddleware`：恢复时根据 TaskRun/TaskStep 判断从哪个阶段继续，避免从头执行。
- `GDPIdempotencyMiddleware`：对场景执行、Source 创建、配置写入等副作用节点做幂等键保护。
- `GDPMemoryInjectionMiddleware`：注入用户常用环境、系统别名、字段偏好、常用 SQL、常用造数场景。
- `GDPContextCompressionMiddleware`：当节点开始大量 LLM 推理或子 Agent 汇报时，压缩消息和执行摘要，但保留任务目标、当前阶段、计划、变量栈摘要和未完成目标。
- `GDPSubtaskMiddleware`：管理子任务/子 Agent 的创建、等待、结果归并和失败策略。

这些 middleware 可以参考 Lead Agent 的代码组织方式，甚至复制一部分实现思路，但包名、类型、状态字段、注入点都应该和 Lead Agent 物理隔离。

### GDP 对 Lead Agent 工厂的取舍

GDP 应该借鉴：

- 运行时参数统一从 `configurable/context` 合并。
- 工厂负责解析运行时能力，节点只消费已经归一化后的结果。
- metadata 和 tracing callbacks 在图根统一挂载。
- middleware 顺序作为契约管理，而不是随意 append。
- 可选能力通过 feature/config 打开，不在节点内部散落开关。
- Prompt 尽量保持稳定，动态上下文通过 middleware 注入。
- 自定义能力、memory、subtask、压缩都在工厂层有明确开关和生命周期。

GDP 不应该照搬：

- 不应该直接继承 `ThreadState` 只为了拿到字段。
- 不应该把 TaskRun/TaskStep/TaskEvent 的业务事实迁入 `messages`。
- 不应该用 Lead Agent 的通用 `task` 工具替代 GDP 的业务子任务模型。
- 不应该把所有 GDP 节点包成一个通用聊天 Agent 循环。
- 不应该让 memory 替代任务历史；memory 只记录跨任务偏好和可复用知识。

一句话总结：Lead Agent 工厂的精髓是“在请求入口把动态运行时收敛成一次可观测、可恢复、能力边界清晰的 Agent 图”。GDP 要学的是这个边界，而不是照搬 Lead Agent 的字段和 middleware 类型。
