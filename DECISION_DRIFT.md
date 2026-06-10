# DECISION_DRIFT.md

本文件记录架构决策和漂移防护。准备重构、迁移目录、改变依赖方向或替换核心方案时先阅读。

## ADR-001 Harness 与 App 分层

- 决策：`backend/packages/harness/deerflow` 是通用 Agent Harness，`backend/app` 是应用层。
- 原因：Harness 需要保持可复用，不能被 GDP、Gateway 业务细节污染。
- 约束：App 可以导入 Harness，Harness 不能导入 App。
- 漂移信号：在 Harness 中出现 `app.*` 导入，或把 GDP 业务模型放到 Harness。
- 验证：在 `backend/` 下运行 `uv run pytest tests/test_harness_boundary.py`。

## ADR-002 Gateway 嵌入 Agent 运行时

- 决策：Gateway 直接承载 LangGraph 兼容运行时，不默认拆出单独 LangGraph Server。
- 原因：统一认证、线程、上传、产物、SSE、用户隔离和部署入口。
- 约束：`/api/langgraph/*` 兼容 SDK，Gateway 内部仍走本地运行服务。
- 漂移信号：新增一套绕过 Gateway 认证和用户隔离的运行入口。

## ADR-003 GDP/datagen 放在 App 层

- 决策：造数业务代码统一放在 `backend/app/gdp`。
- 原因：datagen 是具体业务域，不属于通用 Harness。
- 约束：Gateway 只负责挂载 GDP 路由，不承载业务逻辑。
- 漂移信号：datagen Service、Repository、业务模型出现在 `backend/app/gateway` 或 Harness。

## ADR-004 datagen API 仅使用 GET / POST

- 决策：datagen 后端 API 只新增 GET / POST。
- 原因：当前业务处于开发期，前后端约定追求简单统一，避免 CRUD 方法风格分裂。
- 约束：查询 GET，修改/删除/执行 POST + JSON body。
- 漂移信号：`backend/app/gdp` 下出现新的 `@router.put`、`@router.delete`、`@router.patch`。
- 验证：在 `backend/` 下运行 `uv run pytest tests/test_gdp_datagen_api_method_contract.py`。

## ADR-005 Pydantic 是 datagen 契约中心

- 决策：datagen API 契约说明沉淀在 Pydantic 模型层。
- 原因：OpenAPI、前端、测试都能直接消费模型说明，减少文档和代码漂移。
- 约束：类 docstring 和 `Field(description=...)` 必须写中文说明。
- 漂移信号：新增字段没有 description，或只在代码注释中解释字段。
- 验证：在 `backend/` 下运行 `uv run pytest tests/test_gdp_datagen_pydantic_docs.py`。

## ADR-006 React datagen 前端按业务域分层

- 决策：React 版 datagen 位于 `frontend/src/gdp/datagen`，按 common、baseconfig、httpsource、sqlsource、scene、task 分层。
- 原因：场景编排、数据源配置和任务管理共享大量表单与类型，需要清晰依赖方向。
- 约束：公共能力进 common，业务模块可以依赖 common，common 不依赖业务模块。
- 漂移信号：公共 HTTP/SQL 表单被放到某个业务目录，或业务模块之间相互导入。

## ADR-007 开发期允许破坏性重构

- 决策：当前开发阶段不为旧数据、旧字段、旧 API 背兼容包袱。
- 原因：业务模型仍在快速演进，保持新模型一致性比兼容旧方案更重要。
- 约束：破坏性变更必须前后端、测试、文档一起改。
- 漂移信号：为了兼容旧字段保留双模型、双 API、双数据路径，导致逻辑分叉。

## ADR-008 根目录文档作为 Agent 入口

- 决策：根目录保留短文档入口，长分析文档放 `docs/`、`doc/` 或专题 Markdown。
- 原因：Agent 进入项目时需要稳定阅读顺序，不能依赖临时分析文件。
- 约束：根目录文档写规则、地图和索引；长篇细节链接到专题文档。
- 漂移信号：新的长期规则只写在一次性计划文档，未进入 `AGENTS.md` 或 `RETRO.md`。
