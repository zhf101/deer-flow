# GDP Agent Runtime — MVP 实施路线

> 版本：2026-06-24 · 基于现役代码状态
> 当前阶段：🚩 **MVP0–MVP3 已完成，MVP4-A 只读下探已完成，MVP4-B 配置写入主链路已实现待验收**

---

## 一、路线总图

```
MVP0 ████████████████████████████████████ 已完成
MVP1 ████████████████████████████████████ 已完成
MVP2 ████████████████████████████████████ 已完成
MVP3 ████████████████████████████████████ 已完成
MVP4 ████████████████████████████░░░░░░░░ MVP4-A 已完成，MVP4-B 配置写入主链路已实现待验收
MVP5 ████████████████████████████████░░░░ 契约漂移 + UNKNOWN_STATE 对账主链路已实现待验收
MVP6 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 远期
MVP7 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 远期
```

---

## 二、已完成阶段（MVP0–MVP3）

### MVP0：运行骨架

**目标**：建立独立目录、TaskRun 账本、状态机守卫、基础 API、时间线投影。

**交付物**：
- `backend/app/gdp/agent_runtime/` 独立目录，零 LangGraph 依赖
- TaskRun CREATED→RUNNING→COMPLETED/FAILED/CANCELLED
- 状态机 `transition_*` 守卫 + `reject_lm_proposal` 阻断
- 9 个 GET/POST API 端点
- 内存账本 + timeline 前端投影

**验收标准**：
- ✅ HTTP 创建/查询/取消 TaskRun
- ✅ 状态机拒绝非法迁移（含 LLM 直接写状态）
- ✅ 时间线返回脱敏安全投影

---

### MVP1：显式 Scene 执行闭环

**目标**：用户明确传 `scene_code`，执行已有 Scene，记录 Action/Attempt/Observation，证据判定，UNKNOWN_STATE 不重放。

**交付物**：
- PlanStep/Requirement/Action/Attempt/Observation/Evidence/Verdict 实体
- `run_action` 唯一外部写执行入口
- Evidence 抽取 + judge 判定
- Verdict apply：COMPLETED/FAILED/UNKNOWN_STATE 三路
- 超时/断连 → UNKNOWN_STATE → 等用户确认后失败收口

**验收标准**：
- ✅ 显式 `scene_code` 执行完成 → COMPLETED
- ✅ 场景执行失败 → FAILED
- ✅ 超时/断连 → UNKNOWN_STATE 不重放
- ✅ 用户 CONFIRM_UNKNOWN_STATE → 失败收口

---

### MVP2：Catalog 驱动 Scene 选择

**目标**：用户不传 scene_code 时搜索已发布 Scene，自动选或让用户选，支持审批、补参、补 scene_code。

**交付物**：
- Catalog adapter `search_scenes`
- `RequirementProposal` + `SceneCandidate`（评分/理由/缺参/副作用/合约 hash）
- 自动选择策略：单候选高置信无缺参无副作用 → 自动执行
- WAITING_USER 挂起：MISSING_INPUT / NEED_APPROVAL / NEED_SCENE_SELECTION
- Reply 恢复：SELECT_SCENE / SUPPLY_SCENE_CODE / APPROVE / SUPPLY_INPUT
- 失败 Scene 黑名单
- 决策审计记录

**验收标准**：
- ✅ 无 scene_code 启动→搜索→自动选→执行
- ✅ 多候选→WAITING_USER→用户选择→执行
- ✅ 缺参→WAITING_USER→补参→执行
- ✅ 有副作用→WAITING_USER→审批→执行
- ✅ 零候选→用户手动补 scene_code→执行
- ✅ 执行失败→scene_code 入黑名单

---

### MVP3：多步骤 Scene 串联

**目标**：多 PlanStep 串联，上游产出变量绑定到下游，active step 推进，中间步骤失败阻断。

**交付物**：
- `build_plan` 确定性 recipe → 多 PlanStepSpec
- `create_plan_steps` + `depends_on` 依赖关系
- `active_step_id` 驱动当前步骤
- StepInputBinding：USER_INPUT / VARIABLE / CONST
- SceneOutputBinding + `extract_scene_output_variables`
- Variable（provenance / value_ref / value_preview / sensitive / consumed_by）
- StepEdge 跨步骤变量传递
- `continue_multistep` 循环推进
- 中间步骤 FAILED/UNKNOWN_STATE → 阻断后续
- SQL ledger hydrate 后恢复 multi-step

**验收标准**：
- ✅ 「创建订单并支付」recipe 全链路走通
- ✅ 步骤 1 产出变量绑定到步骤 2 输入
- ✅ 步骤 1 失败 → 步骤 2 不执行
- ✅ WAITING_USER 冻结 → 回复 → 继续剩余步
- ✅ 服务重启后从 SQL 恢复完整状态

---

## 三、当前阶段：MVP4 — SCENE→SOURCE→INFRA 下探 + 配置写回

**优先级**：中高 · MVP4-A 只读下探已完成；MVP4-B 配置写回主链路已实现，进入验收收口

**目标**：缺完整 Scene 时先只读下探 HTTP/SQL Source 和基础配置线索，结构化记录父子缺口并在前端展示缺口树；确定性前置校验通过后免人工确认自动创建并发布组合 Scene，回弹父缺口并继续执行。

### 范围

| 包括 | 不包括 |
|---|---|
| 扩展 `RequirementLayer`：SCENE / SOURCE / INFRA | 人工审批策略（ASK_ALWAYS/DELEGATED/FULL） |
| Requirement 父子关系（子缺口→父缺口回弹） | 从零自由设计 Scene 业务逻辑 |
| SourceCandidate / InfraCandidate | 自由 LLM 规划 |
| 只读搜索 + WAITING_USER 展示 | 写入 Source / Infra 配置（仅写入组合 Scene） |
| MVP4-B 配置写入：基于现有 Source **确定性组合**生成并发布 Scene，免人工确认，但必须有确定性校验和审计 | |

### 建议拆分

1. **Step 1：扩展 RequirementLayer + 父子关系（已实现，待持续回归）**
   - 已有 `RequirementLayer.SOURCE`、`RequirementLayer.INFRA`
   - Requirement 已有 `parent_requirement_id` 和 `layer`
   - MVP4-A 只记录父子关系；子缺口回弹父缺口继续 resolve 留到 MVP4-B

2. **Step 2：Source/Infra 搜索只读 + 展示（后端和卡片已实现，缺口树收敛中）**
   - 已能搜索已有 HTTP Source / SQL Source / 系统 / 环境 / 数据源
   - 已产出 SourceCandidate / InfraCandidate
   - 当前收敛点：前端按 `parent_requirement_id` 展示 SCENE -> SOURCE -> INFRA 缺口树
   - 不写任何配置

3. **Step 3：免人工确认的配置写入（主链路已实现，验收收口中）**
   - 已实现 `adapters/config_writeback.py:DatagenConfigWritebackAdapter`，经类型化 datagen service 合约创建并发布组合 Scene，不裸写表
   - 写入前完成确定性前置校验（见下方「确定性校验门」），不以人工确认作为门禁
   - 写入成功后回弹父 SCENE 缺口：`start_workflow.py` 取 `writeback_result.target_code` 作为新 scene_code，`resolve_explicit_scene` 重新执行
   - 无论成功/失败都通过 `build_config_writeback_decision` 落决策审计
   - 写回失败为降级（拼接失败原因回到「手动补 scene_code」路径），非硬阻断

### 确定性校验门（MVP4-B 免人工确认的前置）

写回只在以下条件**全部确定性满足**时发起（`source_infra_discovery.py:_can_writeback` + `config_writeback.py:_precheck`）：

- Source 候选非空
- Infra 候选数 ≥ Source 候选数（每个 Source 的基础配置依赖都已诊断）
- 所有 Infra 候选 `ready=True` 且无 `missing_fields`
- 发布前 `validate_scene_publish(scene)` 通过

任一条件不满足 → 返回 `SKIPPED`，不发起业务配置写入，保持只读下探挂起路径。

> **副作用边界**：写回成功会在 datagen 场景库创建并发布一个 `agent_scene_{hash}` 真实组合 Scene（`tags` 含 `agent-runtime`/`auto-writeback`），并自动续跑执行。此为预期副作用，验收时需确认其可在场景管理中追溯。

### 验收标准

**MVP4-A 只读下探（已完成）**

- 「没有完整的已支付订单 Scene，但有创建订单 HTTP Source + 支付 HTTP Source」→ 只读下探→记录 SOURCE/INFRA 子缺口→WAITING_USER 展示
- 缺口树在前端可展示，并能看到每层 proposal / Source / Infra 摘要
- Infra 未就绪时不发生 Source、Infra 或 Scene 配置写入
- 不引入 Capability Graph
- 不引入自由 LLM 规划

**MVP4-B 配置写回（主链路已实现，验收收口）**

- Source 候选齐备 + Infra 全部 ready 无缺字段 → 免人工确认创建并发布组合 Scene → COMPLETED（`test_source_and_ready_infra_writeback_publishes_scene_then_executes`）
- 任一确定性校验门不满足 → `SKIPPED`，不发起写入，保留只读挂起路径
- 写回成功后回弹父 SCENE 缺口并以新 scene_code 续跑执行
- 写回成功/失败均落 `CONFIG_WRITEBACK` 决策审计，可在 timeline 追溯
- 写回失败降级回「手动补 scene_code」，不硬阻断任务

### 前置条件

- [x] TimelineResponse 已扩展展示多 Layer 缺口
- [x] `RequirementLayer.SOURCE / INFRA` 和 `parent_requirement_id` 已进入代码
- [x] Source/Infra 只读发现后端测试已存在
- [x] frontend/agent-runtime-page.tsx 支持缺口树展示
- [x] MVP4-A 相关前后端回归集已通过（全量 frontend check 仍有既有 lint 债）

---

## 四、后续规划（MVP6–MVP7）

### MVP5：契约漂移 + UNKNOWN_STATE 对账（主链路已实现，验收收口中）

**状态**：2026-06-24 主链路实现完成，130 passed / 0 fail。Trellis 任务 `06-24-mvp5-contract-drift`。

**已实现**：
- **契约漂移检测**：`execute_scene` 顶部 `_guard_contract_drift`，仅在 select_scene / approve 恢复路径（候选快照来自更早请求、有时间间隔）触发执行前重验；hash 不一致 → WAITING_USER(CONTRACT_DRIFT) 阻断，落 `CONTRACT_DRIFT` 决策审计。用户回 `ACCEPT_CONTRACT_DRIFT` 接受新契约续跑。
- **UNKNOWN_STATE 对账双路径**：`CONFIRM_UNKNOWN_STATE` payload 新增 `actual_outcome`（SUCCEEDED/FAILED/UNCERTAIN，缺省 FAILED 向后兼容）。
  - FAILED → 失败收口（现有行为不回归）。
  - SUCCEEDED → 用户必须指定只读核查场景 `verify_scene_code`，系统执行该 QUERY 场景取证据 judge，**证据证明成功才推进 DONE**，绝不靠用户断言写状态（守住核心不变量）。
  - UNCERTAIN → 维持 WAITING_USER。

**关键设计决策**：
- contract_hash 抽取为 `support/contract_hash.py` 公共函数，catalog 委托复用，红线单测锁 `catalog hash == guard hash` 防全场景误报。
- 漂移在执行前 gate 拦截、不经 judge，因此**不新增 `VerdictType.CONTRACT_DRIFT`**，只新增 `SuspendReason.CONTRACT_DRIFT` + `DecisionKind.CONTRACT_DRIFT` + `ReplyType.ACCEPT_CONTRACT_DRIFT`。
- 漂移只在 select_scene/approve 触发（其余路径同请求内刚解析契约，漂移结构上不可能），消除每次执行多一次 Catalog 调用的成本。
- R1 核查证据来源 = **用户指定核查场景**（现有契约模型无"写场景→核查场景"链接，自动搜索接近一个新 MVP，留后续）。

**验收标准**：
- [x] select_scene/approve 恢复时契约 hash 漂移 → WAITING_USER(CONTRACT_DRIFT) 阻断，不发写请求
- [x] 用户 ACCEPT_CONTRACT_DRIFT → 以新契约续跑终态
- [x] hash 一致 → 正常执行（无行为变化）
- [x] CONFIRM_UNKNOWN_STATE actual_outcome=FAILED/缺省 → 失败收口不回归
- [x] actual_outcome=SUCCEEDED + 核查证据证明成功 → COMPLETED 带 final_verdict_id
- [x] SUCCEEDED 但无 verify_scene_code 或核查证据不达标 → 不推进（不靠用户断言写 DONE）
- [ ] timeline 投影确认 CONTRACT_DRIFT 决策与对账核查 Action 可审计、脱敏（收口项）

### MVP6：回退与变量污染

**优先级**：低 · 依赖 MVP3+5 稳定

**目标**：
- 下游失败通过 Variable provenance 回溯上游责任步骤
- taint 变量
- 回退受影响步骤 + 重搜/重执行

**关键设计点**：
- 已有地基：`Variable.tainted`、`Variable.provenance`、`PlanStep.consumes/produces`
- 不引入自动回退，先做用户驱动

### MVP7：跨任务 ContextItem 复用

**优先级**：低

**目标**：
- 完成任务后提取可复用 ContextItem
- 新任务引用历史可信变量（「前面的卡号帮我开通两个权限」）
- 复用前检查 env 匹配、TTL、tainted、reusable

---

## 五、当前短期建议步骤

### Step A：文档收敛（1–2 天）

- [x] 产出本 PRD / Architecture / MVP 路线三份核心文档
- [ ] 归档过时旧文档（见「文档审计报告」）
- [x] 修正 API.md 过时路径引用
- [x] clean up 前端 `WAITING_APPROVAL` 死分支

### Step B：稳固 MVP3 体验（3–5 天）

- [ ] 增加 1–2 个确定性 recipe（非订单支付的真实多步骤 case）
- [ ] 优化前端多步骤展示：突出 active step、前置步骤、变量传递
- [ ] 补充变量列表中 provenance 到步骤的可读映射
- [ ] 增加前端测试覆盖 WAITING_USER 交互派生

### Step C：MVP4-A 收敛验收（已完成）

- [x] 写 PRD / design / implement
- [x] 明确 Requirement 父子关系和回弹规则边界
- [x] 明确 SourceCandidate / InfraCandidate 最小字段
- [x] 前端缺口树展示 SCENE -> SOURCE -> INFRA
- [x] 跑通前后端 MVP4-A 相关回归集
- [x] 明确 MVP4-B 配置写入不需要人工确认；后续设计只保留确定性校验、权限/环境边界和审计要求

### Step D：MVP4-B 配置写回验收收口（当前）

- [x] 实现 `DatagenConfigWritebackAdapter` 经类型化 service 合约创建并发布组合 Scene
- [x] 确定性校验门（`_can_writeback` + `_precheck`）+ 发布前 `validate_scene_publish`
- [x] 写回成功回弹父缺口并续跑（`start_workflow.py`）
- [x] 写回决策审计落账（`CONFIG_WRITEBACK`）
- [x] 跑通 `test_gdp_agent_runtime_config_writeback.py`（9 passed）
- [ ] 确认 timeline 能审计到写回决策的脱敏投影
- [ ] 在文档/前端明确 `agent_scene_{hash}` 自动 Scene 的副作用可追溯

---

## 六、测试基线

**现役测试**：agent_runtime 全量 `uv run pytest tests/ -k gdp_agent_runtime` → **130 passed / 0 fail**

> 2026-06-24：MVP5 新增 11 项测试（2 hash 红线 + 4 契约漂移 + 5 UNKNOWN_STATE 对账），基线从 119 升至 130。

最低回归集（改 runtime 必须跑）：

```powershell
cd backend
uv run pytest tests/test_gdp_agent_runtime_runner.py -q
uv run pytest tests/test_gdp_agent_runtime_api.py -q
uv run pytest tests/test_gdp_agent_runtime_multistep_runner.py -q
uv run pytest tests/test_gdp_agent_runtime_multistep_reply.py -q
uv run pytest tests/test_gdp_agent_runtime_repository.py -q
uv run pytest tests/test_gdp_agent_runtime_verdict.py -q
uv run pytest tests/test_gdp_agent_runtime_execution.py -q
uv run pytest tests/test_gdp_agent_runtime_source_infra_discovery.py -q
uv run pytest tests/test_gdp_agent_runtime_config_writeback.py -q
uv run pytest tests/test_gdp_agent_runtime_contract_drift.py -q
uv run pytest tests/test_gdp_agent_runtime_unknown_state_reconcile.py -q
uv run pytest tests/test_gdp_datagen_api_method_contract.py -q
uv run pytest tests/test_gdp_datagen_pydantic_docs.py -q
```

边界守护：
```powershell
uv run pytest tests/test_gdp_agent_runtime_boundaries.py -q
```
