# API.md

本文件记录仓库级 API 约定。完整后端 API 参考见 `backend/docs/API.md`，接口实现以代码和 OpenAPI 为准。

## 全局入口

| API 类别 | 前缀 | 说明 |
|---|---|---|
| Gateway API | `/api/*` | 模型、线程、运行、上传、产物、技能、MCP、记忆等 |
| Auth API | `/api/v1/auth/*` | 登录、注册、初始化、当前用户 |
| GDP/datagen API | `/api/v1/datagen/*` | 造数配置、数据源、场景、任务、Agent 辅助 |
| LangGraph 兼容 API | `/api/langgraph/*` | 面向 LangGraph SDK 的线程和运行接口 |

## datagen HTTP 方法规则

datagen 相关后端 API 只允许 GET / POST：

- 查询类接口：GET，参数放 path 或 query。
- 创建、修改、删除、测试、执行类接口：POST，参数放 JSON body。
- 不新增 PUT / DELETE / PATCH。
- 如果需要删除语义，使用 `POST /xxx/delete` 或 `POST /xxx/{id}/delete`。
- 如果需要更新语义，使用 `POST /xxx/update` 或语义化 POST 操作。

## datagen 模型文档规则

- API 请求和响应模型写在 Pydantic 层。
- 类 docstring 写整体用途。
- 字段用 `Field(description="中文说明")` 写前后端契约和运行时含义。
- OpenAPI 展示出来的字段说明应足以让前端和测试人员理解。

## 当前 GDP/datagen 路由组

所有路由通过 `backend/app/gdp/router.py` 挂到 `/api/v1/datagen`。

| 路由组 | 主要文件 | 说明 |
|---|---|---|
| 基础配置 | `backend/app/gdp/datagen/config/base/api.py` | 系统、环境、服务端点、数据源 |
| HTTP 源 | `backend/app/gdp/datagen/config/httpsource/api.py` | HTTP 源列表、创建、更新、测试、禁用、删除 |
| SQL 源 | `backend/app/gdp/datagen/config/sqlsource/api.py` | SQL 源列表、解析、测试、保存 |
| 场景 | `backend/app/gdp/datagen/config/scene/api.py` | 场景保存、查询、运行、运行历史 |
| 任务 | `backend/app/gdp/datagen/config/task/api.py` | 任务配置和执行 |
| 子任务 | `backend/app/gdp/datagen/config/task/subtask_api.py` | 任务下子任务配置 |
| Agent 目录 | `backend/app/gdp/datagen/agent_catalog/api.py` | 场景和数据源搜索、契约、基础设施解析 |
| Agent 记忆 | `backend/app/gdp/datagen/agent_memory/api.py` | 造数业务事实记忆 |
| Agent 场景 | `backend/app/gdp/agent/api.py` | 场景草稿、校验、发布、源配置、基础设施辅助 |
| Agent 技能 | `backend/app/gdp/agent/skills/api.py` | 阶段技能上下文 |
| Agent MCP | `backend/app/gdp/agent/mcp/api.py` | MCP 能力策略、规划和结果应用 |

## API 变更检查清单

修改 API 前后检查：

- 路由方法是否符合所在域规则。
- 请求模型、响应模型、字段描述是否同步。
- 前端 API 调用路径、方法、参数是否同步。
- 前端类型和表单默认值是否同步。
- 测试是否覆盖正常、边界、异常、回归。
- OpenAPI 是否能看懂中文字段含义。
- 若改 datagen 字段名，旧字段是否完全删除。

## 典型验证命令

```powershell
cd backend
uv run pytest tests/test_gdp_datagen_api_method_contract.py
uv run pytest tests/test_gdp_datagen_pydantic_docs.py
uv run pytest tests/test_datagen_task_api.py tests/test_datagen_task_service.py
```
