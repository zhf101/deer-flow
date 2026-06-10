# ARCHITECTURE.md

本文件记录仓库级架构边界。详细全景见 `docs/PROJECT_ARCHITECTURE.md`，后端通用架构见 `backend/docs/ARCHITECTURE.md`。

## 一句话架构

DeerFlow 是一个全栈 Agent 平台：前端 Workspace 负责交互，Gateway 负责 HTTP、认证、线程和运行生命周期，Harness 负责 Agent 运行时、工具、技能、记忆、沙箱和子代理，GDP/datagen 是运行在应用层的造数业务域。

## 分层边界

```text
Frontend / GDP UI
        |
        v
Gateway API (backend/app/gateway)
        |
        +-- GDP/datagen 应用域 (backend/app/gdp)
        |
        v
Harness Core (backend/packages/harness/deerflow)
        |
        v
LLM / Tools / MCP / Sandbox / Persistence
```

## 依赖方向

- `backend/app/*` 可以依赖 `deerflow.*`。
- `backend/packages/harness/deerflow/*` 不能依赖 `backend/app/*`。
- GDP/datagen 业务代码统一放在 `backend/app/gdp` 下，避免散落到 Gateway 或 Harness。
- React 版 datagen 业务代码统一放在 `frontend/src/gdp/datagen` 下。
- 公共表单、类型、校验工具放在 `frontend/src/gdp/datagen/common`，业务页从 common 单向依赖。

## 核心运行链路

```text
用户输入
-> 前端 Workspace / datagen 页面
-> Gateway API
-> RunManager 或 GDP/datagen Service
-> Lead Agent / 造数服务 / SQL 运行时
-> 工具、数据源、沙箱、数据库
-> SSE 或 JSON 响应
-> 前端渲染消息、产物、场景结果
```

## Gateway 与 Harness

Gateway 是应用门面，负责：

- 认证、CSRF、用户隔离。
- 路由注册。
- 线程、运行、上传、产物、反馈、模型、技能、MCP 等 HTTP API。
- 将请求转换成 Harness 可执行的运行配置。

Harness 是通用 Agent 内核，负责：

- Lead Agent 工厂。
- LangGraph 状态和中间件链。
- 工具注册、MCP 接入、子代理委托。
- 沙箱、上传文件映射、产物路径。
- 记忆、摘要、标题、Token 统计和安全处理。

## GDP/datagen 业务架构

GDP/datagen 是应用层业务域，核心对象包括：

- 基础配置：系统、环境、服务端点、数据源。
- 数据源：HTTP 源、SQL 源。
- 场景：输入参数、编排步骤、运行上下文、断言、结果映射、批量配置。
- 任务：多个场景或子任务的组织和执行。
- Agent：基于现有场景、数据源和基础设施信息生成或辅助维护造数配置。

业务代码采用 API、Pydantic 模型、Service、Repository、Runtime 分层。Pydantic 模型是前后端契约的中心，字段说明必须能直接反映 OpenAPI 文档。

## 数据和状态

| 数据 | 位置 | 说明 |
|---|---|---|
| 全局配置 | `config.yaml`、`config.example.yaml` | 模型、工具、沙箱、扩展配置 |
| 用户线程文件 | `backend/.deer-flow/users/{user_id}/threads/{thread_id}/` | 上传、工作区、产物 |
| LangGraph 状态 | Checkpointer / Store | 消息、状态、checkpoint |
| Run 事件 | RunEventStore | SSE、审计、调试 |
| GDP/datagen 配置 | GDP persistence schema | 造数场景、数据源、任务等业务配置 |
| Agent 记忆 | memory storage / `agent_memory` | 通用记忆和 GDP 业务事实 |

## 架构变更原则

- 修改 Harness 前先确认是否能在 App/GDP 层解决。
- 修改 Gateway 路由前先确认是否影响 LangGraph SDK 兼容路径。
- 修改 datagen 模型时同步前端类型、API 调用、测试和文档。
- 新增跨模块能力时优先找现有中间件、工具注册、Service、Repository 模式。
- 目录迁移必须更新 `CODE_MAP.md`、`IMPACT_MAP.md` 和相关测试路径。
