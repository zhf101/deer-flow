# GDP Agent Runtime — 架构边界（贡献者必读）

本目录是 GDP 造数任务编排引擎的**纯 Python 核心**。以下边界由可执行测试
`backend/tests/test_gdp_agent_runtime_boundaries.py` 自动守护——违反会让 CI 红，
不依赖人工 review。修改本目录前请先读这些规则，详细架构见
`docs/20260623/gdp-agent-runtime-架构地图.md`。

## 不可破坏的不变量

1. **纯 Python 核心，零 LangGraph**
   `agent_runtime/` 任何文件都不得 `import langgraph`。LangGraph 只能在未来的
   薄壳层引入（见 `docs/20260623/gdp-langgraph-回归与分层说明.md` §1）。
   核心永远是壳调用核心，不是核心依赖壳。

2. **不复活已删除的旧实现**
   旧 LangGraph 厚实现 `app.gdp.agent` 已删除。`app/gdp` 下任何代码都不得重新
   import 它。回归请走薄壳三层重写，不复用旧节点（回归说明 §2）。

3. **LLM 永不直接驱动状态机**
   每个 `domain/transitions.py::transition_*` 守卫都必须调用 `reject_lm_proposal`。
   LLM 输出只能作为 `LMProposal` 参与候选排序/建议，绝不直接写
   TaskRun/Action/Requirement/Verdict/Variable 等事实状态。

4. **DDD 内向分层依赖**
   依赖只能向内/向下，不能向外/向上：
   ```
   api  →  application  →  workflows  →  {execution, evidence, verdict, adapters, ledger}  →  domain
                                                                                              ↑
                                                                              support / ports（叶子工具）
   ```
   - `domain` / `support` / `ports`：叶子层，不 import 任何业务子层。
   - `execution/evidence/verdict/adapters/ledger`：用 `domain`，不得 import `api/application/workflows`。
   - `workflows`：不得 import `api/application`。
   - `application`：不得 import `api`。
   - 根级模块（`models.py/store.py/runner.py/transitions.py/...`）是**有意的公开门面层**，
     re-export 子目录真身——import 走根级，改实现去子目录，详见架构地图 §2。

## 验证

```powershell
cd backend
uv run pytest tests/test_gdp_agent_runtime_boundaries.py -q
```

新增/修改后至少跑这条 + 相关 `test_gdp_agent_runtime_*.py`。
