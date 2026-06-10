# 03 ThreadState 状态管理

对应字幕：`03-ThreadState状态管理_final_哔哩哔哩_bilibili_BV1SVdHBEEhZ_字幕.srt`

## 本章目标

这一集聚焦 `ThreadState`。字幕中“threat state”应统一校正为 `ThreadState`。

源码入口：

`backend/packages/harness/deerflow/agents/thread_state.py`

`ThreadState` 是 DeerFlow Agent 运行时的数据总线。中间件、工具、标题生成、沙箱、上传文件和产出物都通过它共享状态。

## 为什么用 TypedDict 状态

`ThreadState` 继承 `AgentState`，并使用 `TypedDict` 风格定义字段。相比全局字典，它有几个优点：

- 可序列化：checkpointer 要把状态落到持久化后端。
- schema 明确：字段名和类型能在开发阶段暴露错误。
- 避免共享可变状态：节点和中间件返回局部更新，由 LangGraph 统一应用。
- 支持 reducer：不同节点并发写同一字段时，运行时知道如何合并。

## 字段总览

```python
class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: Annotated[list | None, merge_todos]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
```

继承的 `messages` 是最重要字段，由 LangChain Agent 状态管理。DeerFlow 自己增加的字段服务于工作区、UI 展示和长时序能力。

## 字段生命周期

### `messages`

来源：用户输入、模型输出、工具结果、中间件插入的隐藏消息。

作用：保存完整对话历史，也是模型每轮推理的输入基础。`DeerFlowSummarizationMiddleware` 会在上下文过长时把旧消息压缩成 `HumanMessage(name="summary")`。

### `thread_data`

写入者：`ThreadDataMiddleware`。

字段：

- `workspace_path`
- `uploads_path`
- `outputs_path`

这个字段把当前 `thread_id` 映射到宿主机上的线程目录。源码在 `ThreadDataMiddleware.before_agent()` 中根据 runtime context 或 `configurable.thread_id` 获取线程 id，并按当前用户隔离目录。

### `sandbox`

写入者：`SandboxMiddleware` 或工具首次调用时的懒初始化逻辑。

字段：

- `sandbox_id`

它记录当前线程关联的沙箱实例。沙箱工具通过这个 id 找到实际执行环境。

### `title`

写入者：`TitleMiddleware`。

标题只在第一次完整交互后生成。`TitleMiddleware._should_generate_title()` 会检查是否已有标题、是否有一条用户消息和至少一条 AI 消息。失败时回退为用户首条消息截断。

### `artifacts`

写入者：产出物相关工具，例如 `present_files`。

reducer：`merge_artifacts` 合并并去重，避免多个工具结果覆盖彼此。

### `todos`

写入者：计划模式下的 `TodoMiddleware`。

reducer：`merge_todos` 的语义是“`None` 表示未触碰，非 `None` 表示显式更新”。这让空列表也能作为有效更新。

### `uploaded_files`

写入者：`UploadsMiddleware`。

它读取最后一条用户消息的 `additional_kwargs.files`，并扫描历史 uploads 目录，把 `<uploaded_files>` 块注入到用户消息前面。这样模型不用猜文件路径。

### `viewed_images`

写入者：`ViewImageMiddleware`。

reducer：`merge_viewed_images` 支持普通合并，也支持传入空字典清空已有图片上下文。

## Reducer 设计

字幕里提到 reducer 解决并发写入和静默覆盖问题。源码中的设计很克制：

- 会被多个来源追加的字段才加 reducer，例如 `artifacts`。
- 需要“显式覆盖”语义的字段定制 reducer，例如 `todos`。
- 普通运行元数据用 `NotRequired`，减少无意义合并逻辑。

这说明 `ThreadState` 不是“大而全的全局对象”，而是对运行时共享数据做最小化建模。

## 和中间件的关系

`ThreadState` 本身不做业务逻辑，中间件才是字段生命周期的主要操作者：

- `ThreadDataMiddleware` 写 `thread_data`，并给用户消息补 `run_id`、`timestamp`。
- `UploadsMiddleware` 写 `uploaded_files`，并改写最后一条用户消息。
- `SandboxMiddleware` 写 `sandbox`。
- `TitleMiddleware` 写 `title`。
- `MemoryMiddleware` 读 `messages`，将会话加入记忆更新队列。
- `ViewImageMiddleware` 写 `viewed_images`。

## 常见误区

不要把 `ThreadState` 理解成业务数据库。它是“当前 Agent 图运行所需的状态快照”，由 checkpointer 管理版本和恢复。线程列表、运行记录、反馈、用户等持久化数据则走 Gateway 侧的 repository / store。

也不要绕过 `ThreadState` 去写全局变量。那会绕开 checkpointer、reducer 和用户/线程隔离。

## 本章结论

`ThreadState` 是 DeerFlow 的状态总线。它把 LangGraph 的状态合并能力、DeerFlow 的线程目录、沙箱、产出物、上传文件、标题和视觉上下文串起来。理解它之后，再读中间件链会清楚很多：中间件本质上是在不同钩子里读写这个状态。

## 结合当前源码的补充分析

`ThreadState` 的设计精髓不是字段多，而是每个字段都有清楚的生命周期：谁生产、谁消费、是否进入 checkpoint、是否可被 reducer 合并、什么时候需要显式清理。当前源码里，这一点比粗略看字段定义更重要。

### `ThreadState` 是 Agent 图的 channel schema

`backend/packages/harness/deerflow/agents/thread_state.py` 里 `ThreadState` 继承 `langchain.agents.AgentState`。`AgentState` 提供最核心的 `messages` 通道，DeerFlow 在此基础上增加：

```python
class ThreadState(AgentState):
    sandbox: NotRequired[SandboxState | None]
    thread_data: NotRequired[ThreadDataState | None]
    title: NotRequired[str | None]
    artifacts: Annotated[list[str], merge_artifacts]
    todos: Annotated[list | None, merge_todos]
    uploaded_files: NotRequired[list[dict] | None]
    viewed_images: Annotated[dict[str, ViewedImageData], merge_viewed_images]
```

Lead Agent 和子 Agent 都显式使用这个 schema：

- `backend/packages/harness/deerflow/agents/lead_agent/agent.py` 创建 Lead Agent 时传 `state_schema=ThreadState`。
- `backend/packages/harness/deerflow/subagents/executor.py` 创建内置子 Agent 时也传 `state_schema=ThreadState`。
- `backend/packages/harness/deerflow/client.py` 会从 checkpoint 的 `channel_values` 中读取 `title`、`messages`、`artifacts` 等，用于线程列表、历史状态和流式结果。

所以 `ThreadState` 不是普通 Python dict，而是 LangGraph checkpoint 里的状态通道定义。字段一旦进入这里，就会参与状态合并、持久化快照、恢复和前端可见状态。

### `messages` 的生命周期

`messages` 是最重要、也最容易膨胀的字段。它的生产者很多：

- 用户输入：客户端或 runtime worker 构造 `HumanMessage`。
- 模型输出：LangChain Agent 模型节点追加 `AIMessage`。
- 工具结果：ToolNode 追加 `ToolMessage`。
- middleware 注入：动态上下文、上传文件、Todo reminder、ViewImage 等都会追加或替换消息。

几个关键 middleware 对 `messages` 有特殊处理：

- `DynamicContextMiddleware` 在 `before_agent` 阶段把 memory 和当前日期作为隐藏 `HumanMessage` 注入，并使用 ID-swap 技巧保持第一条用户消息位置稳定。
- `UploadsMiddleware` 在 `before_agent` 阶段改写最后一条用户消息，把 `<uploaded_files>` 块前置到内容里。
- `DeerFlowSummarizationMiddleware` 在 `before_model` 阶段根据 token 阈值触发压缩，返回 `RemoveMessage(id=REMOVE_ALL_MESSAGES)` 加摘要消息和保留尾部消息。
- `TodoMiddleware` 在 todo 工具调用被摘要挤出上下文后，用隐藏 `todo_reminder` 消息把当前 todo 状态重新告诉模型。
- `ViewImageMiddleware` 在 `before_model` 阶段把 `viewed_images` 里的 base64 图片注入为新的多模态 `HumanMessage`。
- `TokenUsageMiddleware` 在 `after_model` 阶段改写最后一条 `AIMessage.additional_kwargs`，添加 token attribution。

这说明 `messages` 不只是“聊天记录”。它也是 middleware 给模型注入运行时上下文的载体。正因为如此，Lead Agent 才需要消息压缩、隐藏消息标记、动态上下文保护、skill rescue 等细节，防止重要运行时上下文被错误压缩或展示给用户。

### `thread_data` 的生命周期

`thread_data` 由 `ThreadDataMiddleware` 生产。它在 `before_agent` 阶段根据 `thread_id` 和当前 `user_id` 计算：

- `workspace_path`
- `uploads_path`
- `outputs_path`

`lazy_init=True` 时只计算路径，不立即创建目录；`lazy_init=False` 时会在进入 Agent 前创建目录。当前 Lead runtime 默认使用 lazy 初始化，这是为了避免每次对话都做不必要的文件系统操作。

`ThreadDataMiddleware` 还会改写最后一条 `HumanMessage`，补充：

- `run_id`
- `timestamp`
- 默认 `name="user-input"`

消费者主要是：

- sandbox 工具：把 `/mnt/user-data/workspace`、`/uploads`、`/outputs` 映射到宿主机线程目录，并做路径校验和脱敏。
- `present_files`：要求文件必须在当前线程 outputs 目录下，最终写入 `artifacts`。
- `view_image`：只允许读取 workspace/uploads/outputs 下的图片，并依赖 `thread_data` 做路径解析和安全校验。
- 子 Agent：`SubagentExecutor` 会把父 Agent 的 `thread_data` 透传给子 Agent，让子 Agent 使用同一工作区。

这里的设计重点是：`thread_data` 是线程级运行资源定位，不是业务数据。它可以从 `thread_id + user_id + Paths` 推导出来，因此即使 checkpoint 里有它，也不是业务事实权威。

### `sandbox` 的生命周期

`sandbox` 记录当前线程关联的沙箱实例：

```python
class SandboxState(TypedDict):
    sandbox_id: NotRequired[str | None]
```

它有两种生产路径：

1. `SandboxMiddleware(lazy_init=False)` 在 `before_agent` 阶段提前 acquire sandbox 并写入 `{"sandbox": {"sandbox_id": ...}}`。
2. 当前默认的 `lazy_init=True` 不在 Agent 启动时创建 sandbox；sandbox 工具首次调用 `ensure_sandbox_initialized()` 时 acquire，并直接写入 `runtime.state["sandbox"]`。

消费者是所有需要真实执行环境的 sandbox 工具，例如 bash、读写文件、目录浏览、搜索等。`SandboxMiddleware.after_agent` 会根据 state 或 runtime context 里的 `sandbox_id` release sandbox。

这个字段的精髓是懒加载和复用：没有工具需要沙箱时不创建；同一个线程内多次工具调用复用同一 sandbox；释放由 middleware 统一处理。

### `artifacts` 的生命周期

`artifacts` 是“展示给用户的产物引用”，不是所有输出文件。

生产者是 `present_files` 工具。该工具会把传入路径规范化为 `/mnt/user-data/outputs/*`，并拒绝 outputs 目录之外的文件。成功后返回：

```python
Command(update={
    "artifacts": normalized_paths,
    "messages": [ToolMessage("Successfully presented files", ...)],
})
```

`artifacts` 使用 `merge_artifacts` reducer：

- `existing is None`：返回新列表或空列表。
- `new is None`：保留已有 artifacts。
- 两边都有值：按顺序合并并去重。

这个 reducer 解决两个问题：

1. 多个工具或多个并行分支展示文件时不互相覆盖。
2. 后续节点没碰 `artifacts` 时不会把已展示产物清空。

前端和客户端只应该把 `artifacts` 当成可展示文件清单。文件本体仍在 outputs 目录，下载/查看走 artifacts router。

### `todos` 的生命周期

`todos` 是计划模式下的任务清单，由 LangChain 的 `TodoListMiddleware` 和 DeerFlow 自定义 `TodoMiddleware` 共同维护。

`merge_todos` 的语义非常关键：

- `new is None`：表示本次状态更新没有触碰 todo，保留 existing。
- `new` 是列表：表示显式更新，哪怕是空列表也要覆盖 existing。

这不是理论设计，测试里专门覆盖了一个回归问题：如果没有 reducer，某些下游节点的局部状态更新会带着 `todos=None`，导致已存在的 todo 被静默清掉。`tests/test_thread_state_reducers.py` 里把这个场景作为回归保护。

`TodoMiddleware` 还做了两件和状态生命周期相关的事：

- 当 `todos` 还在 state 里，但原始 `write_todos` tool call 已经被摘要压缩出 `messages`，它会注入隐藏 `todo_reminder`，让模型恢复对当前 todo 的认知。
- 当模型想直接给最终回答但 `todos` 仍未完成，它会通过 `jump_to="model"` 让图回到模型节点，并在下一次 model call 里临时追加 `todo_completion_reminder`。这个 reminder 不作为普通用户消息长期持久化，避免污染可见对话。

这说明 `todos` 是一个典型的“结构化状态比 messages 更可靠”的例子。即使消息被压缩，todo 仍然可以通过 state 恢复到模型上下文。

### `uploaded_files` 的生命周期

`uploaded_files` 由 `UploadsMiddleware` 写入。它不是文件本体，只是当前消息新上传文件的结构化摘要。

`UploadsMiddleware.before_agent` 会：

1. 读取最后一条 `HumanMessage.additional_kwargs.files`。
2. 根据 `thread_id` 找到 uploads 目录，并过滤不存在或非法文件名。
3. 扫描历史 uploads 目录，补充之前上传过但仍可用的文件。
4. 对转换出来的 Markdown 文件提取 outline 或 preview。
5. 把 `<uploaded_files>` 上下文块前置到最后一条用户消息。
6. 返回 `{"uploaded_files": new_files, "messages": updated_messages}`。

这里要注意两点：

- `uploaded_files` 只记录“本轮新文件”；历史文件通过目录扫描重新注入到消息上下文。
- memory 处理会过滤上传文件块，避免把 `<uploaded_files>` 这种运行时提示误写入长期记忆。

所以 `uploaded_files` 是 UI/上下文辅助字段，不是上传文件的权威索引。权威位置是线程 uploads 目录和客户端上传接口。

### `viewed_images` 的生命周期

`viewed_images` 由 `view_image` 工具写入。工具读取图片、校验大小、校验扩展名和 magic bytes 后，把 base64 和 mime type 写入：

```python
{"viewed_images": {
    image_path: {"base64": image_base64, "mime_type": mime_type}
}}
```

`ViewImageMiddleware` 读取这个字段，在确认上一条 AIMessage 里的 `view_image` tool call 都已有对应 ToolMessage 后，追加一个包含图片内容的多模态 `HumanMessage`，让支持视觉的模型真正“看到”图片。

`merge_viewed_images` 的 reducer 有一个特殊语义：

- 普通 dict：按 key 合并，新值覆盖旧值。
- `new == {}`：显式清空所有 viewed images。

当前源码里主要生产路径是追加图片，测试里保护了空 dict 清理语义。这个设计为后续 middleware 在处理完图片后释放 base64 上下文留了出口，否则长对话里图片 base64 会持续撑大 checkpoint 和模型上下文。

### `title` 的生命周期

`title` 由 `TitleMiddleware` 在 `after_model` 阶段生成。触发条件很克制：

- title config 开启。
- 当前 state 还没有 title。
- 至少有一条用户消息和一条 AI 消息。
- 用户消息必须是真实用户消息，不能是动态上下文 reminder。

异步路径会用专门的 title model 调用生成标题；失败时退回到首条用户消息截断。runtime worker 还会在 run 结束后从 checkpoint 的 `channel_values.title` 同步到 thread metadata 的展示名。

因此 `title` 是会话 UI 元数据，生命周期是“一次生成、后续保留”。它不参与模型决策，也不应该被业务流程依赖。

### 哪些状态没有放进 ThreadState

源码里也有一些重要运行时状态没有进入 `ThreadState`：

- `TodoMiddleware` 的 completion reminder 计数和 pending reminder 队列，存在 middleware 实例内存里，并按 `(thread_id, run_id)` 清理。
- `LoopDetectionMiddleware` 的循环检测历史，也主要在 middleware 内存里维护。
- memory 更新队列在 `MemoryMiddleware.after_agent` 里异步排队，不写回 ThreadState。
- RunJournal、RunEventStore、checkpoint metadata、thread metadata 都走 runtime/persistence 层，不混进 ThreadState。

这说明 DeerFlow 并不是把所有东西都塞进 state。判断标准是：

- 需要 checkpoint 恢复、跨节点共享、前端 snapshot 展示的，进入 ThreadState。
- 只在一次 run 内做控制、防抖、统计、临时提醒的，可以放 middleware 内存。
- 业务事实、长期记忆、运行审计，走独立持久化存储。

## 对 GDPState 的设计启发

GDP 当前 `backend/app/gdp/agent/state.py` 只有轻量字段：

```python
class GDPState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    task_run_id: str
    user_intent: str
    env_code: str
    current_phase: str
    pending_confirmation: dict[str, Any]
    confirmation_result: Any
    last_tool_result: dict[str, Any]
    user_inputs: dict[str, Any]
    inputs: dict[str, Any]
```

这不一定错，因为 GDP 的业务事实主要在 TaskRun/TaskStep/TaskEvent/visibleVariables 中。但如果后续要引入类似 Lead 的 middleware、子 Agent、长任务恢复和上下文压缩，GDPState 需要按 ThreadState 的生命周期原则重新设计，而不是简单继承 ThreadState。

### GDP 不应机械继承 ThreadState

ThreadState 的字段服务于通用聊天 Agent：

- `thread_data` 服务文件工作区。
- `sandbox` 服务通用工具执行。
- `artifacts` 服务文件展示。
- `uploaded_files` 服务用户上传文件。
- `viewed_images` 服务多模态图片分析。
- `todos` 服务通用计划模式。
- `title` 服务会话列表展示。

GDP 是造数业务图，核心状态不是这些，而是：

- 用户造数目标。
- 当前业务阶段。
- 场景候选、Source 候选、基础配置缺口。
- 用户确认和审批。
- 可见变量栈。
- 已完成步骤、执行结果和反思结果。
- 子任务和恢复游标。

所以 GDPState 的优雅设计不是“像 ThreadState 一样字段多”，而是“像 ThreadState 一样每个字段都有明确生命周期”。

### GDPState v2 建议按状态职责分层

建议 GDPState 后续可以分成这些通道：

```python
class GDPState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]

    task_context: GDPTaskContext
    runtime_context: GDPRuntimeContext
    phase_state: GDPPhaseState
    user_input_state: GDPUserInputState
    result_state: GDPResultState
    subtask_state: GDPSubtaskState
    context_budget_state: GDPContextBudgetState
```

其中每个通道都要定义生命周期。

`task_context`：

- 生产者：intake / recovery middleware。
- 内容：`task_run_id`、`user_intent`、`normalized_goal`、`env_code`、创建人、目标约束。
- 消费者：所有节点、LLM prompt builder、子 Agent context builder。
- 生命周期：任务级稳定上下文，除 normalized goal 的受控更新外不随节点随意覆盖。
- 权威来源：TaskRun。

`runtime_context`：

- 生产者：GDP runtime middleware。
- 内容：`thread_id`、`run_id`、`checkpoint_id`、trace_id。
- 消费者：事件记录、恢复、子任务 tracing。
- 生命周期：run 级上下文，可从 RunnableConfig 和 TaskRun 重建。
- 权威来源：LangGraph runtime + TaskRun.deerflowThreadId/lastCheckpointId。

`phase_state`：

- 生产者：每个业务节点。
- 内容：`current_phase`、`previous_phase`、`phase_entered_at`、`phase_reason`。
- 消费者：router、前端展示、恢复逻辑。
- 生命周期：节点边界更新，和 TaskRun.phase 同步。
- 权威来源：TaskRun.phase。

`user_input_state`：

- 生产者：intake、human_confirm、用户回复 API。
- 内容：结构化 `user_inputs`、最近一次 `confirmation_result`、输入来源。
- 消费者：场景匹配、Source 配置、基础配置、执行绑定。
- 生命周期：任务内累积，但需要能区分“用户明确输入”和“Agent 推断输入”。
- reducer：建议做 dict merge，但需要记录字段来源，避免后续回复无意覆盖关键输入。

`result_state`：

- 生产者：scene_fulfillment、scene_design、source_config、infra_config、scene_execute、progress_reflection。
- 内容：最近一次结构化结果摘要、结果引用、错误摘要。
- 消费者：下一节点、progress_reflection、前端状态。
- 生命周期：节点级短期状态，完整结果落 TaskStep/TaskEvent 或业务表。
- reducer：多数情况下 last-wins；大对象只放 `result_ref`。

`subtask_state`：

- 生产者：GDP 子任务 middleware / 子任务节点。
- 内容：活跃子任务 ID、类型、状态、结果摘要、result_ref。
- 消费者：等待节点、恢复 middleware、progress_reflection。
- 生命周期：子任务级；完整生命周期必须落库，state 只是运行时镜像。
- reducer：按 `subtask_id` merge，终态覆盖非终态。

`context_budget_state`：

- 生产者：GDP 上下文压缩 middleware。
- 内容：`goal_anchor`、`progress_summary`、`visible_variable_summary`、`history_refs`。
- 消费者：LLM 节点、子 Agent prompt builder。
- 生命周期：每个节点或若干事件后刷新；不能替代 TaskStep/TaskEvent。
- reducer：last-wins 或版本号较新的摘要覆盖旧摘要。

### GDP 字段是否进入 state 的判断标准

可以借鉴 ThreadState 的判断标准，为 GDP 建一套准入规则：

1. **跨节点必须共享**：进入 GDPState。
2. **恢复后必须继续使用**：进入 GDPState，但权威值还要能从数据库重建。
3. **前端实时快照需要展示**：进入 GDPState 或 TaskRun 响应模型。
4. **只是单个节点内部临时变量**：不要进入 GDPState。
5. **是业务事实或审计事实**：落 TaskRun/TaskStep/TaskEvent，不只放 GDPState。
6. **是大对象或完整 transcript**：放外部引用，GDPState 只保存 ref 和摘要。
7. **是 run 内控制计数，重启后不要求恢复**：可以放 middleware 内存。
8. **重启后必须恢复的等待/子任务/审批状态**：必须落库，不可只放 middleware 内存。

### GDP reducer 设计建议

当前 GDPState 只有 `messages` 使用 `add_messages`。后续如果加字段，不要默认 last-value-wins，应该按字段语义设计 reducer。

建议：

- `messages`：继续用 `add_messages`，但 GDP 不应把大量执行详情放进 messages。
- `user_inputs`：使用 dict merge reducer，并保留字段来源；用户回复优先级高于 Agent 推断。
- `context_refs`：使用去重追加 reducer，类似 `merge_artifacts`。
- `active_subtasks`：按 `subtask_id` merge，状态机必须单调，终态不能被 RUNNING 覆盖。
- `visible_variable_snapshot`：如果只是 TaskRun.visibleVariables 的镜像，建议 last-wins；真正变量栈仍以 TaskRun 为准。
- `pending_confirmation`：last-wins，但每次进入 WAITING_USER 前必须先落 TaskRun.pendingInterrupts。
- `progress_summary`：last-wins，并带 `summary_version` 或来源 eventNo，避免旧摘要覆盖新摘要。

ThreadState 的 `merge_todos` 给 GDP 的启发很大：`None` 不应该总是表示“清空”，很多时候只是“本节点没碰这个字段”。GDPState 里只要存在可累积字段，都应该明确区分：

- 未触碰：`None` 或不返回字段。
- 显式清空：返回空列表、空 dict 或带 `clear=True` 的结构。
- 显式更新：返回新值。

### GDP 与 ThreadState 字段的对应关系

GDP 不需要照搬字段，但可以借鉴模式：

| ThreadState 字段 | 解决的问题 | GDP 可借鉴的对应物 |
| --- | --- | --- |
| `messages` | 对话和模型上下文 | `messages` 只保留必要交互，业务执行详情走 TaskEvent |
| `thread_data` | 线程工作区定位 | `runtime_context.workspace_ref`，仅当 GDP 需要文件/产物时引入 |
| `sandbox` | 工具执行环境 | `execution_context`，用于 SQL/HTTP/脚本执行资源引用 |
| `artifacts` | 展示给用户的文件 | `result_refs/artifact_refs`，关联造数报告、样例数据、日志 |
| `todos` | 通用计划状态 | `plan/progress_summary`，权威来源是 TaskRun.plan/TaskStep |
| `uploaded_files` | 用户上传文件上下文 | `input_refs`，例如接口文档、SQL 文件、样例数据文件 |
| `viewed_images` | 多模态临时上下文 | GDP 暂时不需要，除非后续支持截图/表结构图片解析 |
| `title` | 会话 UI 标题 | TaskRun.finalSummary 或任务列表展示名 |

### GDP 最应该吸收的状态管理精髓

1. **状态是通道，不是杂物箱**：每个字段都要知道谁写、谁读、谁清理。
2. **结构化状态优先于消息回忆**：Todo 能在消息压缩后恢复，GDP 的目标、计划、变量栈和子任务结果也应该这样设计。
3. **reducer 是业务语义的一部分**：合并、保留、清空都必须显式表达。
4. **大对象不要塞 state**：工具大输出会外置到文件并回填引用；GDP 的 SQL 结果、接口响应、子 Agent transcript 也应如此。
5. **checkpoint 不是业务数据库**：ThreadState 可以恢复图状态，但业务事实仍应由 repository/store 管；GDP 更应该坚持 TaskRun/TaskStep/TaskEvent 为权威来源。
6. **隐藏上下文要有标记**：动态上下文、summary、todo reminder 都用 name 或 additional_kwargs 区分，GDP 后续的 goal anchor、progress summary 也应避免混成普通用户消息。
7. **run 内临时控制和可恢复状态要分开**：Lead 的一些 reminder 计数能放 middleware 内存；GDP 的子任务等待、审批、中断必须落库。

因此，GDPState 后续演进的方向不是继承 `ThreadState`，而是建立 GDP 自己的 `State` schema 和 middleware 生命周期契约：TaskRun/TaskStep/TaskEvent 管业务事实，GDPState 管图运行快照，middleware 管注入、压缩、恢复、幂等和子任务收敛。
