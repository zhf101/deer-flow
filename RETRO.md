# RETRO.md

本文件记录可复用的错误模式，不记录流水账。新增条目时写清现象、根因、解决方案和防护措施。

## 使用规则

- 每次开始任务先阅读本文件。
- 调试耗时超过 30 分钟、重复 Bug、错误决策、测试遗漏导致返工时新增条目。
- 同类问题累计出现 3 次及以上时，升级为 `AGENTS.md` 强制规则。
- 已升级的规则仍保留在这里，方便理解来源。

## API 类

### RETRO-001 datagen API 方法风格漂移 [已升级]

- 现象：datagen 相关接口容易沿用 FastAPI 常见 CRUD 风格，新增 PUT / DELETE / PATCH。
- 根因：通用 Gateway API 和 datagen 业务 API 的方法约束不同。
- 解决方案：datagen 查询用 GET，修改、删除、执行用 POST + JSON body。
- 防护措施：已升级到 `AGENTS.md` 和 `API.md`；新增或修改 datagen API 时，在 `backend/` 下运行 `uv run pytest tests/test_gdp_datagen_api_method_contract.py`。

### RETRO-002 Pydantic 字段缺少中文说明 [已升级]

- 现象：OpenAPI 中字段语义不清，前端和测试需要回读实现才能理解契约。
- 根因：字段说明写在实现注释或文档里，没有沉淀到 Pydantic 模型。
- 解决方案：类 docstring 描述模型用途，字段用 `Field(description=...)` 描述运行时含义。
- 防护措施：已升级到 `AGENTS.md` 和 `API.md`；新增或修改 datagen 模型时，在 `backend/` 下运行 `uv run pytest tests/test_gdp_datagen_pydantic_docs.py`。

## 架构类

### RETRO-003 Harness 与 App 边界混淆 [已解决]

- 现象：应用层业务能力容易被放到 Harness 核心包，或让 Harness 反向依赖 App。
- 根因：Agent 平台能力和具体产品业务都在同一仓库，目录边界需要显式提醒。
- 解决方案：通用运行时能力放 `backend/packages/harness/deerflow`，应用和 GDP 业务放 `backend/app`。
- 防护措施：改跨层依赖前阅读 `ARCHITECTURE.md`，在 `backend/` 下运行 `uv run pytest tests/test_harness_boundary.py`。

### RETRO-004 datagen 前端目录职责不清 [已解决]

- 现象：页面组件、业务组件和公共表单混在一个目录下，复用关系不清。
- 根因：早期按页面快速堆叠，HTTP/SQL 表单既被数据源页使用，也被场景编排使用。
- 解决方案：React 版 datagen 按 `common`、`baseconfig`、`httpsource`、`sqlsource`、`scene`、`task` 分层。
- 防护措施：公共能力放 `frontend/src/gdp/datagen/common`，业务目录只能单向依赖 common。

## 测试类

### RETRO-005 测试建议只覆盖正常流程 [已升级]

- 现象：修改后只验证 happy path，边界和异常场景遗漏。
- 根因：交付时没有固定测试建议结构。
- 解决方案：每次交付必须输出功能、边界、异常、回归测试建议。
- 防护措施：已升级到 `AGENTS.md`；按 `TEST_STRATEGY.md` 选择验证范围。

## 文档类

### RETRO-006 工程经验散落在临时分析文档 [已解决]

- 现象：长期经验写在一次性分析文档里，后续 Agent 进入项目时不会主动阅读。
- 根因：缺少根目录项目操作系统入口。
- 解决方案：将规则沉淀到 `AGENTS.md`，将代码地图、架构、API、测试策略、影响图拆成根目录文档。
- 防护措施：新增经验优先进入 `RETRO.md`，稳定规则再升级到 `AGENTS.md`。
