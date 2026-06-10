# 12 MCP 协议集成

对应字幕：`12-MCP协议集成_哔哩哔哩_bilibili_BV1SVdHBEEhZ_字幕.srt`

## 本章目标

这一集讲为什么 DeerFlow 用 MCP 扩展外部工具，以及源码里如何加载、缓存、复用和调用 MCP 工具。

核心源码：

- `backend/packages/harness/deerflow/config/extensions_config.py`
- `backend/packages/harness/deerflow/mcp/client.py`
- `backend/packages/harness/deerflow/mcp/cache.py`
- `backend/packages/harness/deerflow/mcp/tools.py`
- `backend/packages/harness/deerflow/mcp/session_pool.py`
- `backend/packages/harness/deerflow/mcp/oauth.py`
- `backend/app/gateway/routers/mcp.py`

## MCP 解决的问题

没有 MCP 时，每个 Agent 框架都有自己的工具接入方式。一个企业内部数据库查询工具，如果要接入 LangChain、LlamaIndex、AutoGen 和 OpenAI API，可能要写四套胶水代码。

MCP 的价值是把工具实现和 Agent 框架解耦：

```text
工具服务实现 MCP Server
Agent 框架实现 MCP Client
二者通过标准协议交换工具 schema 和调用结果
```

DeerFlow 只需要实现 MCP Client 侧，就能连接任何兼容 MCP 的工具服务器。

## 配置文件

MCP 配置位于 `extensions_config.json`，字段模型在 `ExtensionsConfig`：

```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"}
    }
  }
}
```

每个 server 支持：

- `enabled`
- `type`: `stdio`、`sse`、`http`
- `command` / `args` / `env`
- `url` / `headers`
- `oauth`
- `description`

`ExtensionsConfig.from_file()` 会单独读取这个 JSON，并解析环境变量。

## 传输方式

`mcp/client.py` 的 `build_server_params()` 根据 `type` 构造 langchain-mcp-adapters 参数：

- `stdio`：本地子进程，通过 stdin/stdout 通信。需要 `command`。
- `sse`：HTTP SSE 服务。需要 `url`。
- `http`：标准 HTTP MCP 服务。需要 `url`。

不支持的类型会抛出 `ValueError`。

## 工具初始化和缓存

`mcp/cache.py` 维护全局缓存：

- `_mcp_tools_cache`
- `_cache_initialized`
- `_initialization_lock`
- `_config_mtime`

`initialize_mcp_tools()` 在启动时或懒加载时调用 `get_mcp_tools()`，并记录配置文件 mtime。

`get_cached_mcp_tools()` 会检查：

- 缓存是否初始化。
- `extensions_config.json` mtime 是否变化。
- 如果变化，调用 `reset_mcp_tools_cache()` 并关闭会话池。

这样前端通过 Gateway API 修改 MCP 配置后，下次请求可以重新加载工具。

## 工具加载流程

`mcp/tools.py` 的 `get_mcp_tools()`：

1. 导入 `MultiServerMCPClient`。
2. 重新读取 `ExtensionsConfig.from_file()`，保证拿到最新配置。
3. 通过 `build_servers_config()` 过滤启用的 server。
4. 注入 OAuth 初始 header。
5. 构造 OAuth 和自定义 interceptor。
6. 创建 `MultiServerMCPClient(..., tool_name_prefix=True)`。
7. 调用 `client.get_tools()` 发现工具。
8. stdio 工具包装为持久会话工具。
9. 为 async-only 工具补 sync wrapper。

`tool_name_prefix=True` 会把 server 名加入工具名前缀，避免不同 MCP server 工具重名。

## 为什么需要 session pool

默认 langchain-mcp-adapters 每次工具调用可能创建新 session。对无状态工具问题不大，但对 Playwright 这类有状态 MCP server 会出问题：第一次调用打开网页，第二次调用找不到之前的浏览器状态。

`MCPSessionPool` 按 `(server_name, scope_key)` 复用 session，`scope_key` 通常是 `thread_id`。

特点：

- 最大 session 数 256。
- LRU 淘汰。
- 同一 event loop 内复用；跨 event loop 时关闭旧 session 并重建。
- 支持按 thread scope 关闭、按 server 关闭、全部关闭。

源码只对 `stdio` transport 做 session pool。HTTP/SSE 内部使用 anyio TaskGroup，跨任务关闭容易出错，所以不池化。

## OAuth 和拦截器

`extensions_config.json` 可配置 OAuth。`get_mcp_tools()` 会：

- 调用 `get_initial_oauth_headers()` 为工具发现/会话初始化注入授权头。
- 调用 `build_oauth_tool_interceptor()` 包装实际工具调用。
- 支持 `mcpInterceptors` 自定义拦截器路径。

这让认证对 Lead Agent 透明。Agent 仍然只是调用工具，认证由 DeerFlow 运行时处理。

## 与工具搜索结合

`get_available_tools()` 中，如果 `config.tool_search.enabled`，MCP 工具不会全部直接暴露给模型，而是注册到 `DeferredToolRegistry`，并把 `tool_search` 加入内置工具。

这样做的意义：

- 避免几十上百个 MCP 工具 schema 占满上下文。
- 降低模型工具选择噪声。
- 只在需要时提升工具进入可调用集合。

## Gateway 管理接口

`backend/app/gateway/routers/mcp.py` 提供：

- `GET /api/mcp/config`
- `PUT /api/mcp/config`

GET 会屏蔽敏感字段：

- `env` 值显示为 `***`
- `headers` 值显示为 `***`
- OAuth 的 `client_secret`、`refresh_token` 不返回

PUT 会合并 masked secrets：当前端 round-trip `***` 时，后端保留磁盘中的真实 secret，避免 UI 切换 enabled 时把密钥覆盖成星号。

## 本章结论

DeerFlow 的 MCP 集成不是简单调用 adapter。它包含配置隔离、mtime 缓存失效、工具名前缀、stdio 会话池、OAuth 拦截、自定义 interceptor、工具搜索延迟加载和 Gateway 管理。MCP 是外部工具扩展层，核心价值是让工具服务独立于 DeerFlow 源码演进。

## 结合当前源码的补充分析

上面是 MCP 集成的主线，但如果从 GDP Agent 视角看，最重要的不是“MCP 能接很多工具”，而是 DeerFlow 为这些工具补了几层运行时约束。

### 配置生命周期

`ExtensionsConfig` 把 MCP Server 和 Skills 放在同一个扩展配置模型里：

- `mcpServers` 通过 Pydantic alias 映射到 `mcp_servers`。
- `resolve_config_path()` 的优先级是显式参数、`DEER_FLOW_EXTENSIONS_CONFIG_PATH`、项目根目录 `extensions_config.json` / `mcp_config.json`，再到后端目录兜底。
- `from_file()` 每次从磁盘读取 JSON，并递归替换形如 `$TOKEN` 的环境变量占位符。
- `get_enabled_mcp_servers()` 只返回 `enabled=true` 的 server。

这里有一个细节：缺失的环境变量会被解析成空字符串，而不是失败。这对通用 DeerFlow 比较宽容，但对 GDP 这类会连接数据库、造数服务、审批系统的业务工具不一定合适。GDP 如果复用 MCP 配置，建议在 GDP 自己的策略层增加“必填 secret 校验”和“启动/调用前健康检查”，否则一个空 token 可能到工具调用阶段才暴露为难定位的认证失败。

### 工具加载生命周期

`mcp/tools.py` 的 `get_mcp_tools()` 没有使用全局缓存里的 `get_extensions_config()`，而是直接调用 `ExtensionsConfig.from_file()`。这是一个刻意设计：Gateway API 可能在另一个进程更新 `extensions_config.json`，工具加载必须读磁盘最新配置。

加载过程实际包含这些步骤：

1. `build_servers_config()` 先把配置转成 `MultiServerMCPClient` 参数。
2. `stdio` 必须有 `command`，`sse/http` 必须有 `url`，不支持的 transport 会报错。
3. 单个 server 配置失败时会被记录日志并跳过，不会拖垮所有 MCP 工具加载。
4. 对 HTTP/SSE server，初始化时会注入 OAuth Authorization header，用于工具发现和 session 初始化。
5. 构造 OAuth tool interceptor，保证实际工具调用时也能刷新和注入 token。
6. 读取顶层 `mcpInterceptors`，用反射加载自定义拦截器。
7. `MultiServerMCPClient(..., tool_name_prefix=True)` 发现工具，并给工具名加 server 前缀，避免不同 server 的工具重名。
8. `stdio` 工具会被二次包装成持久会话工具。
9. async-only 工具会补上 sync wrapper，适配 DeerFlow 同步流式调用场景。

这说明 MCP 在 DeerFlow 里不是“发现后直接给模型调用”。工具发现、认证、命名、会话、同步调用兼容都在运行时统一处理。

### 调用结果生命周期

`_convert_call_tool_result()` 把 MCP 的 `CallToolResult` 转成 LangChain `content_and_artifact`：

- 文本块转 text block。
- 图片块转 image block。
- resource link / embedded resource 按 MIME 转 image 或 file block。
- `structuredContent` 放入 artifact。
- `isError=true` 时抛 `ToolException`。
- 如果 interceptor 直接返回 `ToolMessage` 或 LangGraph `Command`，会原样透传。

这个转换对 Lead Agent 是合理的，因为 Lead Agent 的运行单位是消息和工具结果。但 GDP 不能只停留在 ToolMessage/artifact 层。GDP 的工具输出应该进一步归档到：

- `TaskEvent`：记录发生了什么。
- `TaskStep`：记录这是哪个业务步骤的结果。
- `visibleVariables`：把可复用的结果摘要化为变量栈。
- 业务配置表：例如 Source、Scene、Infra 的权威配置。

所以 GDP 可以复用 MCP 的底层调用结果转换，但不能让 MCP 输出直接成为 GDP 的业务事实。

### 缓存和失效生命周期

`mcp/cache.py` 的缓存只缓存“已发现的工具列表”，并记录配置文件 mtime。`get_cached_mcp_tools()` 会在每次读取时判断配置文件是否变化：

- 未初始化时懒加载。
- mtime 变化时重置工具缓存。
- 重置时会关闭并清空 MCP session pool。
- 如果当前已经在 event loop 中，懒加载会开线程执行 `asyncio.run()`，兼容 FastAPI / LangGraph Studio 等上下文。

这套机制适合 Lead Agent 的工具目录。但 GDP 需要再加一层“业务能力目录缓存”：

- MCP 工具变了，只说明外部能力 schema 变了。
- GDP 可用能力还取决于环境、阶段、审批策略、用户权限、Source/Scene 契约。
- 因此 GDP 不应该直接把 `_mcp_tools_cache` 当作可执行业务能力目录，而应该从 MCP 工具列表派生出 GDP 自己的 `CapabilityCatalog`。

## MCP 与 tool_search / deferred tools 的关系

MCP 工具数量可能很大，直接把所有 schema 绑定给模型会带来两个问题：上下文膨胀，以及模型在大量无关工具之间误选。因此 DeerFlow 引入了 `tool_search` 和 `DeferredToolFilterMiddleware`。

实际机制是：

1. `get_available_tools()` 仍然把 MCP 工具加入最终工具集合，让 `ToolNode` 具备执行路由能力。
2. 如果 `tool_search.enabled=true`，MCP 工具会先注册到 `DeferredToolRegistry`。
3. `DeferredToolFilterMiddleware.wrap_model_call()` 在模型绑定前移除仍处于 deferred 状态的工具 schema。
4. Prompt 里只暴露 deferred tool 的轻量名称列表。
5. 模型调用 `tool_search(query)` 后，`tool_search` 返回匹配工具的 OpenAI function schema。
6. 返回 schema 的同时，registry 会把这些工具 `promote()`，后续模型调用才会看到完整 schema。
7. 如果模型绕过 `tool_search` 直接调用仍 deferred 的工具，`wrap_tool_call()` 会返回错误 ToolMessage，阻止执行。

这个设计有两个精髓：

- **工具执行能力和工具可见性分离**：ToolNode 可以执行全部工具，但模型一开始看不到全部工具 schema。
- **可见性是单次运行上下文的一部分**：`DeferredToolRegistry` 用 `ContextVar` 保存，避免并发请求互相污染；同一次运行内子 agent 重新构造工具集时，会尽量复用已有 registry，避免已提升工具又被重新隐藏。

GDP 后续如果做 middleware 链，建议借鉴这个机制，但不要直接共用 Lead Agent 的 `DeferredToolRegistry`。原因不是这套机制不能用，而是 GDP 的 deferred 对象不应该只是“LangChain BaseTool”，而应该是“带业务生命周期的能力”。

GDP 更适合做成自己的物理隔离版本：

```text
Lead Agent:
MCP BaseTool -> DeferredToolRegistry -> tool_search -> DeferredToolFilterMiddleware

GDP Agent:
MCP BaseTool -> GDPMCPToolAdapter -> GDPCapabilityRegistry -> gdp_capability_search -> GDPToolPolicyMiddleware
```

隔离的价值是：

- 避免两个 agent 共用 ContextVar 导致运行时可见性互相影响。
- GDP registry 可以带 `taskRunId`、`phase`、`envCode`、`approvalRequired`、`sideEffectLevel`、`outputSensitivity` 等业务字段。
- GDP middleware 可以在工具调用前后写 `TaskStep/TaskEvent`，而 Lead 的 middleware 不关心 GDP 审计。
- GDP 可以按阶段暴露能力，例如 `SCENE_DESIGN` 只允许 Source/Scene 设计相关能力，`SCENE_EXECUTING` 才允许执行类能力。

## OAuth、拦截器和安全边界

`oauth.py` 目前支持两类 grant：

- `client_credentials`
- `refresh_token`

`OAuthTokenManager` 会按 server 缓存 access token，并用 server 级 `asyncio.Lock` 避免并发刷新同一个 token。过期判断会提前 `refresh_skew_seconds` 秒刷新。`build_oauth_tool_interceptor()` 则在每次工具调用前把 Authorization header 注入 request。

Gateway 管理接口还有一层脱敏：

- GET 时，`env` 和 `headers` 的值统一返回 `***`。
- OAuth 的 `client_secret`、`refresh_token` 不返回。
- PUT 时，如果前端把 `***` 原样传回，后端会用磁盘中的真实 secret 合并，避免 UI round-trip 把 secret 覆盖成星号。
- 顶层未知 key，例如 `mcpInterceptors`，会在写回时保留。

这套能力对 GDP 很有参考价值，但 GDP 需要更强的业务安全边界：

- 读能力和写能力要分级，不能只靠工具描述让模型判断。
- 造数、写库、调用业务接口、审批通过都应标注副作用等级。
- 敏感输出不能直接进入 messages，应进入变量栈摘要或外置存储引用。
- 需要把“谁授权、授权了什么、在哪个任务阶段调用、调用结果是什么”落入 `TaskEvent`。
- 对写操作应有幂等键，避免中断恢复或重试时重复造数。

## 为什么 Lead MCP 链不能直接用于当前 GDP 图

当前 GDP 图是显式 `StateGraph(GDPState)` 节点编排：`intake -> scene_fulfillment -> scene_design/source_config/infra_config -> scene_execute -> progress_reflection`。节点内部直接调用 GDP service 和业务工具函数，权威状态落在 `TaskRun/TaskStep/TaskEvent/visibleVariables`。

Lead Agent 的 MCP 链默认假设运行结构是：

```text
模型节点 -> middleware.wrap_model_call -> ToolNode -> middleware.wrap_tool_call -> messages
```

而 GDP 当前结构更接近：

```text
业务阶段节点 -> GDP service/tool 函数 -> TaskRun/TaskStep/TaskEvent -> 下一阶段路由
```

所以问题不是“Lead MCP 能不能用”，而是它不能原样解决 GDP 的核心问题：

- 它只知道 LangChain 工具 schema，不知道 GDP 阶段。
- 它只处理 ToolMessage，不负责 GDP 任务审计。
- 它按 `thread_id` 复用 stdio session，不知道 `taskRunId`、父子任务、恢复点。
- 它的 deferred promotion 是“工具 schema 可见”，不是“业务能力可执行”。
- 它不会自动做 Source/Scene/Infra 契约归一化，也不会把输出写入变量栈。

如果 GDP 后续引入类似 Lead 的 middleware 机制，建议参考 Lead 的思想和部分源码实现，但做 GDP 专用链路，而不是直接把 Lead 的 `get_available_tools()`、`tool_search`、`DeferredToolFilterMiddleware` 挂到 GDP 图上。

## GDP Agent 应如何借鉴 MCP 集成

GDP 应该把 MCP 定位为“外部能力接入层”，而不是“业务步骤本身”。推荐分四层设计。

### 第一层：复用 DeerFlow MCP Client 基础设施

可以复用：

- `ExtensionsConfig` 的 server 配置模型。
- `build_servers_config()` 的 transport 参数转换。
- `get_mcp_tools()` 的工具发现、OAuth、interceptor、结果转换。
- `MCPSessionPool` 的 stdio 持久会话能力。
- `tool_name_prefix=True` 的命名防冲突策略。

但 GDP 最好不要直接复用 Lead 的 `get_available_tools()`，因为它会把内置工具、MCP、ACP、subagent 工具混到一个 Lead 工具列表里。GDP 需要更小、更可控的工具入口。

建议新增类似：

```text
backend/app/gdp/agent/mcp/
  config.py          # GDP MCP 策略模型
  adapter.py         # MCP BaseTool -> GDPExternalCapability
  registry.py        # GDP 独立 ContextVar registry
  middleware.py      # 阶段、审批、审计、输出压缩
  tools.py           # gdp_capability_search / gdp_mcp_call
```

### 第二层：GDP MCP Policy

GDP 不应该按“server enabled”直接开放工具，而应该按业务策略筛选。一个可行的策略模型可以包含：

- `serverName`：来自 DeerFlow MCP server。
- `toolNamePattern`：允许的工具名或正则。
- `allowedPhases`：允许在哪些 `DatagenTaskPhase` 使用。
- `envCodes`：允许在哪些环境使用。
- `sideEffectLevel`：`READ_ONLY`、`WRITE_CONFIG`、`WRITE_DATA`、`EXTERNAL_MUTATION`。
- `approvalRequired`：是否需要用户确认。
- `idempotencyKeyTemplate`：写操作幂等键模板，例如 `${taskRunId}:${phase}:${toolName}:${inputHash}`。
- `outputSensitivity`：输出是否敏感。
- `outputVariablePolicy`：是否可写入 `visibleVariables`，以及如何生成 preview/schema/storageRef。
- `auditEventType`：调用前后写入的 `TaskEvent` 类型。

这样 GDP 的“能不能调用某个 MCP 工具”就不再由模型自由决定，而由阶段、环境、权限、副作用和审批共同决定。

### 第三层：GDP 能力搜索，而不是通用 tool_search

Lead 的 `tool_search` 返回 OpenAI function schema。GDP 可以借鉴“先轻量目录、后完整 schema”的模式，但搜索对象应该换成 GDP 能力目录：

```text
gdp_capability_search("查询订单造数相关能力")
-> 返回能力名称、适用阶段、输入契约、输出契约、风险等级、是否需要审批
-> promote 后才允许当前阶段调用
```

这样可以同时解决两个问题：

- 控制上下文大小，避免把大量 MCP schema 全塞给 GDP 主 agent。
- 强制模型先理解能力的业务语义，而不是看到一个外部工具就直接调用。

对 GDP 来说，能力搜索结果里最重要的不是原始 MCP 参数 schema，而是它能否映射到 GDP 的业务契约：

- 能否生成或补齐 HTTP Source。
- 能否生成或补齐 SQL Source。
- 能否查询基础配置。
- 能否执行造数场景。
- 能否产生可复用变量。
- 是否需要用户审批。

### 第四层：调用前后绑定 Task 生命周期

GDP MCP 调用建议按下面的生命周期落地：

1. 从 `GDPState` 和数据库读取 `taskRunId`、`current_phase`、`envCode`、`visibleVariables`。
2. 从 GDP capability registry 找到已允许、已提升、当前阶段可用的能力。
3. 校验副作用等级和审批状态。
4. 为写操作生成幂等键，检查是否已经执行过同一业务动作。
5. 调用底层 MCP tool。stdio session scope 建议优先绑定 `taskRunId`；如果必须和 DeerFlow thread 兼容，再显式记录 `deerflowThreadId`。
6. 将 MCP 原始输出做摘要、脱敏和结构化归一。
7. 写入 `TaskEvent`，必要时写入 `TaskStep`。
8. 将可复用结果写入 `visibleVariables`，大对象只保留 `valuePreview/valueSchema/valueSize/storageRef`。
9. 返回给模型的消息只保留下一步决策所需的短摘要，避免消息历史膨胀。
10. 任务完成、取消或失败时，按 `taskRunId` 清理相关 MCP session。

这条链路能同时服务三个目标：

- Agent 不偏离用户任务目标：每次外部调用都绑定 `taskRunId`、阶段和目标。
- Agent 不遗忘目标：恢复时从数据库 Task 状态和变量栈重建上下文，而不是依赖长 messages。
- 中断后可恢复：幂等键、TaskStep 状态和 checkpoint 共同决定从哪里继续，不需要从头跑。

## GDP 与子 Agent 协作时的 MCP 使用

如果后续 GDP 主 Agent 会等待子 Agent 执行 MCP 或外部任务，建议不要让子 Agent 只返回一段自然语言总结。更稳妥的契约是：

```text
ChildAgentResult:
  parentTaskRunId
  childTaskRunId
  capabilityName
  phase
  status
  outputSummary
  producedVariables
  auditEventIds
  retryable
  failureType
  failureMessage
```

子 Agent 可以在自己的任务里调用 MCP，但父 Agent 接收的应该是结构化结果和变量引用。这样父 Agent 不需要读取子 Agent 的完整消息历史，也不会因为长时间等待或大量执行细节而偏离主目标。

对 session scope 也要明确：

- 如果子 Agent 操作的是独立外部会话，scope 用 `childTaskRunId`。
- 如果子 Agent 必须继承父任务的外部上下文，scope 用 `parentTaskRunId`，但要在事件里记录共享原因。
- 子 Agent 完成后，父任务只接收摘要和变量，不接收完整 ToolMessage 流。

## 对当前 GDP 的落地判断

当前 GDP 暂时没有启用 MCP，并不是明显缺陷。因为现有 GDP 主要依赖数据库任务状态、场景目录、Source 配置、基础配置和变量栈，业务闭环还在本地服务内完成。

但一旦出现这些需求，GDP 就应该接入 MCP：

- 查询外部 CMDB / 注册中心来补齐系统、环境、服务端点、数据源。
- 查询测试平台、需求平台或工单系统来理解造数目标。
- 调用外部审批或发布系统。
- 使用企业内部 SQL/HTTP 能力仓库生成 Source。
- 使用浏览器、接口调试器、数据库元数据服务辅助设计场景。

接入方式建议是：

- 不把原始 MCP tools 直接暴露给 GDP 主 Agent。
- 不直接复用 Lead 的工具列表和 middleware ContextVar。
- 可以复用 MCP client/cache/session/oauth 的底层能力。
- 复制或改造 Lead 的 deferred tool 思路，做 GDP 专用 capability registry。
- 所有外部调用都必须穿过 GDP policy、approval、audit、variable summarization。

一句话结论：MCP 对 GDP 是有价值的，但 GDP 要接的是“经过业务策略包装后的 MCP 能力”，不是“Lead Agent 那套原始 MCP 工具链”。Lead 的设计精髓值得借鉴，尤其是配置隔离、延迟暴露、ContextVar 运行隔离、session scope 和拦截器链；真正落地时应物理隔离成 GDP 自己的 MCP middleware 链。
