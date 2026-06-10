# IMPACT_MAP.md

本文件用于修改前影响分析和修改后回归测试建议。

## 总体依赖图

```text
Frontend / gdpui
    -> Gateway API
    -> GDP/datagen API
    -> Service
    -> Repository / Runtime
    -> Database / HTTP / SQL / LLM / MCP

Workspace Chat
    -> Gateway thread/run API
    -> RunManager
    -> Lead Agent
    -> Middlewares
    -> Tools / MCP / Sandbox / Subagents
    -> Run events / Artifacts / Memory
```

## GDP/datagen 影响图

```text
backend/app/gdp/router.py
  -> config/base/api.py
     -> service.py
     -> repository.py
     -> models.py
  -> config/httpsource/api.py
     -> service.py
     -> repository.py
     -> executor.py
     -> models.py
  -> config/sqlsource/api.py
     -> service.py
     -> repository.py
     -> parser.py
     -> runtime/sql/*
     -> models.py
  -> config/scene/api.py
     -> service.py
     -> repository.py
     -> executor.py
     -> validation.py
     -> models.py
  -> config/task/api.py
     -> service.py
     -> subtask_service.py
     -> repository.py
     -> models.py
  -> agent/*
     -> nodes/*
     -> middlewares/*
     -> tools/*
     -> llm/*
     -> mcp/*
     -> skills/*
```

## React datagen 影响图

```text
frontend/src/gdp/datagen/page.tsx
  -> common/shell/module-tab-bar.tsx
  -> baseconfig/*
  -> httpsource/*
  -> sqlsource/*
  -> scene/*
  -> task/*

common/lib/api.ts
  -> 所有 datagen 页面和表单

common/lib/types.ts
  -> defaults.ts
  -> validation.ts
  -> step-payload.ts
  -> scene/task/source 页面

common/source-forms/*
  -> httpsource/*
  -> sqlsource/*
  -> scene/*
```

## Gateway / Harness 影响图

```text
backend/app/gateway/app.py
  -> routers/*
  -> deps.py
  -> services.py

services.py
  -> RunManager
  -> StreamBridge
  -> Checkpointer / Store
  -> Lead Agent

Lead Agent
  -> model factory
  -> tools registry
  -> skills loader
  -> middlewares
  -> thread state

Middlewares
  -> memory
  -> sandbox
  -> uploads
  -> token usage
  -> title
  -> summarization
  -> loop detection
```

## 修改点到影响范围

| 修改点 | 上游入口 | 下游消费者 | 回归重点 |
|---|---|---|---|
| Pydantic 字段 | API 请求、前端表单、测试 fixture | Service、Repository、OpenAPI、前端类型 | 字段名、默认值、description、序列化 |
| Repository schema | Service、API、Agent 工具 | 数据库、测试数据、迁移/初始化 | 保存、查询、删除、旧数据清理 |
| datagen API 路径 | 前端 `common/lib/api.ts`、外部调用方 | Service、OpenAPI、测试 | HTTP 方法、参数位置、错误码 |
| SQL 执行器 | SQL 源测试、场景 SQL 步骤、Agent 工具 | 多数据库适配、安全策略 | 参数绑定、只读限制、超时、敏感信息遮蔽 |
| 场景步骤模型 | 场景编辑器、执行器、任务编排、Agent 草稿 | 校验、运行历史、结果映射 | 变量引用、断言、批量执行 |
| Agent 节点 | Agent API、图编排、中间件 | 工具、LLM 决策、事件 | 中断恢复、幂等、错误处理、进度 |
| 前端 common 类型 | 所有 datagen 页面 | 表单、校验、payload 构造 | 类型检查、默认值、保存 payload |
| Gateway run 服务 | 前端聊天、LangGraph SDK、无状态 runs | RunManager、SSE、事件、反馈 | 流式输出、取消、恢复、消息分页 |
| Harness 工具 | Lead Agent、子代理、技能 | 沙箱、MCP、审计、安全 | 工具权限、路径安全、输出预算 |

## 影响分析输出模板

```text
影响范围：
- 入口：
- 调用方：
- 被调用方：
- 数据影响：
- API 影响：
- 前端影响：
- 测试影响：
- 文档影响：
```
