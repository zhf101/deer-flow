# CODE_MAP.md

本文件用于快速定位 DeerFlow 代码位置。更完整的模块说明见 `docs/PROJECT_SKELETON_GUIDE_ZH.md` 和 `docs/PROJECT_ARCHITECTURE.md`。

## 仓库主结构

```text
deer-flow/
├─ backend/                    # Python 后端，FastAPI + LangGraph + Harness
├─ frontend/                   # Next.js 前端主应用
├─ gdpui/                      # Vue 版 GDP/datagen UI
├─ docs/                       # 仓库级设计文档和计划
├─ doc/                        # Agent/GDP 分析文档
├─ docker/                     # 容器和 nginx 部署配置
├─ scripts/                    # 检查、部署、辅助脚本
├─ skills/                     # 内置技能和自定义技能
├─ config.yaml                 # 本地主配置
└─ config.example.yaml         # 配置模板
```

## 后端入口

| 目标 | 位置 |
|---|---|
| FastAPI 应用入口 | `backend/app/gateway/app.py` |
| 运行时依赖装配 | `backend/app/gateway/deps.py` |
| Run 生命周期服务 | `backend/app/gateway/services.py` |
| Gateway 路由 | `backend/app/gateway/routers/` |
| GDP/datagen 总路由 | `backend/app/gdp/router.py` |
| Harness 核心包 | `backend/packages/harness/deerflow/` |
| Lead Agent 工厂 | `backend/packages/harness/deerflow/agents/lead_agent/agent.py` |
| 工具系统 | `backend/packages/harness/deerflow/tools/` |
| 沙箱系统 | `backend/packages/harness/deerflow/sandbox/` |
| 技能系统 | `backend/packages/harness/deerflow/skills/` |
| 记忆系统 | `backend/packages/harness/deerflow/agents/memory/` |
| 运行事件和 Run 存储 | `backend/packages/harness/deerflow/runtime/` |

## GDP/datagen 后端地图

| 模块 | 位置 | 职责 |
|---|---|---|
| datagen 路由聚合 | `backend/app/gdp/router.py` | 在 `/api/v1/datagen` 下挂载造数相关 API |
| 基础配置 | `backend/app/gdp/datagen/config/base/` | 系统、环境、服务端点、数据源配置 |
| HTTP 数据源 | `backend/app/gdp/datagen/config/httpsource/` | HTTP 源定义、测试和启停 |
| SQL 数据源 | `backend/app/gdp/datagen/config/sqlsource/` | SQL 源定义、解析、执行测试 |
| 场景编排 | `backend/app/gdp/datagen/config/scene/` | 场景模型、校验、保存、运行、历史 |
| 任务编排 | `backend/app/gdp/datagen/config/task/` | 任务、子任务、执行配置 |
| SQL 运行时 | `backend/app/gdp/datagen/runtime/sql/` | SQL 安全、参数、执行器注册和多数据库适配 |
| 造数 Agent | `backend/app/gdp/agent/` | LangGraph 节点、中间件、工具、LLM 决策、可观测性 |
| Agent 记忆 | `backend/app/gdp/datagen/agent_memory/` | GDP 造数专用事实记忆 |
| Agent 场景目录 | `backend/app/gdp/datagen/agent_catalog/` | 场景和数据源搜索、契约、基础设施解析 |

## 前端地图

| 模块 | 位置 | 职责 |
|---|---|---|
| Next.js 工作区 | `frontend/src/app/workspace/` | 主工作区路由、布局、聊天页面 |
| React 版 datagen | `frontend/src/gdp/datagen/` | 造数配置、数据源、场景、任务页面 |
| datagen 公共库 | `frontend/src/gdp/datagen/common/` | API、类型、校验、编辑器、表单复用 |
| Vue 版 datagen | `gdpui/src/datagen/` | Vue 管理端页面和组件 |
| 前端通用 API | `frontend/src/core/api/` | 请求客户端和 API 基础设施 |
| 工作区组件 | `frontend/src/components/workspace/` | 聊天、设置、产物、消息等产品组件 |
| UI 组件 | `frontend/src/components/ui/` | shadcn/Radix 风格基础组件 |

## 测试地图

| 测试范围 | 位置 |
|---|---|
| 后端单测和接口测试 | `backend/tests/` |
| GDP/datagen 后端测试 | `backend/tests/test_datagen_*.py`、`backend/tests/test_gdp_*.py` |
| Agent 后端测试 | `backend/tests/test_gdp_agent_*.py` |
| 阻塞 IO 检测 | `backend/tests/blocking_io/` |
| 前端单测 | `frontend/tests/unit/` |
| 前端 E2E 配置 | `frontend/playwright.config.ts` |

## 推荐搜索命令

```powershell
rg -n "关键字" backend/app/gdp backend/tests frontend/src/gdp
rg --files backend/app/gdp frontend/src/gdp backend/tests
rg -n "@router\\.(get|post|put|delete|patch)" backend/app/gdp backend/app/gateway/routers
```
