# TEST_STRATEGY.md

本文件用于把代码变更映射到验证范围。具体测试命令以当前 `backend/pyproject.toml`、`frontend/package.json`、`gdpui/package.json` 为准。

## 通用验证原则

- 先运行最小相关测试，再按影响范围扩大。
- API 或模型变更必须覆盖契约测试。
- 运行时、线程、Agent 中间件变更必须覆盖回归测试。
- 前端表单、类型、API 调用变更必须至少做构建或相关单测。
- 交付时说明已执行验证和未执行验证。

## 后端常用命令

```powershell
cd backend
uv run pytest tests/test_datagen_task_api.py
uv run pytest tests/test_datagen_task_service.py
uv run pytest tests/test_gdp_agent_graph.py
uv run pytest tests/test_harness_boundary.py
uv run ruff check .
```

## 前端常用命令

```powershell
cd frontend
pnpm build
pnpm typecheck
pnpm test
```

Vue 版 `gdpui/` 常用命令：

```powershell
cd gdpui
pnpm build
pnpm type-check
pnpm test:unit
```

如果本机没有 pnpm，也可以使用当前项目可用的包管理器运行同名脚本，但提交验证结果时要写清实际命令。

## 变更到测试的映射

| 变更类型 | 必测范围 |
|---|---|
| datagen API 方法、路径、请求响应 | `test_gdp_datagen_api_method_contract.py`、对应 `test_datagen_*_api.py` |
| datagen Pydantic 模型字段 | `test_gdp_datagen_pydantic_docs.py`、对应 service/api 测试、前端类型检查 |
| datagen Service/Repository | 对应 `test_datagen_*_service.py`、持久化相关测试 |
| 场景编排执行 | `test_datagen_scene_sql_execution.py`、`test_scene_step_models.py`、场景 API 测试 |
| SQL 执行器 | `test_datagen_sql_execution.py`、`test_datagen_sql_dbapi_executors.py`、数据库类型分支测试 |
| GDP Agent 节点 | `test_gdp_agent_graph.py`、`test_gdp_agent_llm_nodes.py`、相关节点工具测试 |
| GDP Agent 中间件 | 对应 `test_gdp_agent_*_middleware.py` 或中间件专项测试 |
| Agent MCP 能力 | `test_gdp_agent_mcp_registry.py`、MCP API/规划/结果应用测试 |
| Gateway thread/run | `test_threads_router.py`、`test_runs_api_endpoints.py`、`test_run_manager.py` |
| Harness 边界 | `test_harness_boundary.py` |
| 认证和用户隔离 | `test_auth*.py`、`test_owner_isolation.py`、`test_*_user_isolation.py` |
| React datagen 前端 | 相关 TS 单测、`pnpm typecheck`、`pnpm build` |
| Vue gdpui 前端 | `gdpui/package.json` 中的 build/type/test 脚本 |
| 文档变更 | 链接、路径、命令是否仍真实存在；不需要业务测试 |

## 测试建议模板

交付时按以下结构给出：

- 功能测试：正常创建、保存、查询、执行或渲染流程。
- 边界测试：空输入、重复编码、非法编码、极长字段、空步骤、无数据源。
- 异常测试：依赖不可用、SQL 执行失败、HTTP 调用失败、权限不足、模型返回无效结构。
- 回归测试：根据 `IMPACT_MAP.md` 覆盖上游入口和下游消费者。

## datagen 专项检查

- API 方法只出现 GET / POST。
- Pydantic 模型字段有中文 description。
- 前端类型和后端字段名一致。
- 默认值在前端 defaults、后端模型、测试 fixture 中一致。
- 删除语义通过 POST body 表达。
- 执行类接口返回足够的错误上下文，但不泄露敏感信息。
