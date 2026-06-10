# 02 LangGraph 核心概念

对应字幕：`02-LangGraph核心概念_哔哩哔哩_bilibili_BV1SVdHBEEhZ_字幕.srt`

## 本章目标

字幕这一集的主线是：为什么 DeerFlow 不用手写 `while` 循环驱动 Agent，而是基于 LangGraph / LangChain Agent 原语构建运行时。源码里有两种图形态：

- 通用 Lead Agent：`backend/langgraph.json` 把 `lead_agent` 注册到 `deerflow.agents:make_lead_agent`。
- 业务 GDP Agent：`backend/app/gdp/agent/graph.py` 显式使用 `StateGraph(GDPState)`、`add_node`、`add_edge`、`add_conditional_edges`。

## 为什么不用 while 循环

一个最小 Agent 循环通常是：

```text
messages -> 调 LLM -> 如果有 tool_calls 就执行工具 -> 追加 ToolMessage -> 再调 LLM
```

这个循环能跑 demo，但在 DeerFlow 这种长时序系统里会遇到几个硬问题：

- 状态持久化：用户刷新、断线、服务重启后，内存里的 `messages` 不可靠。
- 并发合并：多个工具或子 Agent 同时写状态时，普通列表/字典会覆盖或乱序。
- 流式输出：同一条 AI 消息需要在生成过程中按 id 替换更新。
- 中断恢复：澄清、人工确认、取消、恢复运行都需要可追踪 checkpoint。
- 多运行管理：前端需要 thread、run、event、message 的完整生命周期。

LangGraph 的价值不是“换一种写法”，而是把状态、路由、检查点和流式事件变成运行时能力。

## 四个核心概念

### State

State 是跨多次 LLM 调用持续存在的数据对象。DeerFlow 的核心状态在：

`backend/packages/harness/deerflow/agents/thread_state.py`

其中 `ThreadState` 继承 `langchain.agents.AgentState`，除了 `messages` 以外还增加了 `sandbox`、`thread_data`、`title`、`artifacts`、`todos`、`uploaded_files`、`viewed_images` 等字段。

### Node

Node 是状态处理单元。在 Lead Agent 路径里，`langchain.agents.create_agent` 帮 DeerFlow 生成 Agent 循环图；在 GDP 业务图里，节点是显式声明的：

```python
workflow.add_node("intake", build_intake_node(...))
workflow.add_node("scene_design", build_scene_design_node(...))
workflow.add_node("scene_execute", build_scene_execute_node(...))
```

这些节点都接收 `GDPState`，返回局部状态更新。

### Edge

Edge 决定节点执行顺序。GDP 图里有固定边：

```python
workflow.add_edge(START, "intake")
workflow.add_edge("intake", "scene_fulfillment")
```

也有条件边：

```python
workflow.add_conditional_edges(
    "scene_fulfillment",
    _route_after_scene_fulfillment,
    {
        "human_confirm": "human_confirm",
        "scene_design": "scene_design",
        "source_config": "source_config",
        "progress_reflection": "progress_reflection",
    },
)
```

这说明 DeerFlow 同时支持“通用 Agent 循环”和“业务状态机”两种模式。

### Checkpointer

`backend/langgraph.json` 中声明：

```json
"checkpointer": {
  "path": "./packages/harness/deerflow/runtime/checkpointer/async_provider.py:make_checkpointer"
}
```

Gateway 启动时也会在 `app.gateway.deps.langgraph_runtime()` 里创建 checkpointer。它让线程状态能被保存、读取历史、恢复、分叉或取消。

## Reducer 的意义

字幕里强调 reducer 不是语法装饰，而是并发状态合并策略。DeerFlow 的 `ThreadState` 里有几个典型 reducer：

- `merge_artifacts`：合并产出物路径，并去重保序。
- `merge_viewed_images`：合并已查看图片；特殊地，传入空字典表示清空。
- `merge_todos`：`None` 表示未更新，非 `None` 表示显式覆盖。

`messages` 字段来自 `AgentState`，由 LangGraph/LangChain 内置 reducer 管理，支持追加消息以及按 id 替换消息。这对流式输出尤其关键。

## 在 DeerFlow 里怎么落地

核心路径：

```text
Gateway 收到 run 请求
  -> app.gateway.services.start_run()
  -> resolve_agent_factory()
  -> deerflow.agents.lead_agent.agent.make_lead_agent()
  -> langchain.agents.create_agent()
  -> 编译后的 LangGraph Agent 图
```

`make_lead_agent(config)` 是 LangGraph Server / Gateway 嵌入运行时调用的图工厂。它只接收标准 `RunnableConfig`，所以运行时动态参数必须放在 `configurable` 或 `context` 里。

## 阅读源码抓手

先读这些文件：

1. `backend/langgraph.json`：看 DeerFlow 对外暴露了哪个图。
2. `backend/packages/harness/deerflow/agents/thread_state.py`：看状态字段和 reducer。
3. `backend/packages/harness/deerflow/agents/lead_agent/agent.py`：看 Lead Agent 如何被构造。
4. `backend/app/gdp/agent/graph.py`：看显式 `StateGraph` 的业务图示例。
5. `backend/app/gateway/services.py`：看 HTTP 请求如何转换成 LangGraph run。

## 本章结论

LangGraph 在 DeerFlow 里解决的是工程运行时问题：状态可持久、更新可合并、执行可恢复、事件可流式、图可组合。字幕中“为什么不用 while 循环”的答案，归根到底是：手写循环只能表达控制流，LangGraph 还管理长期状态和运行边界。

