# GDP Agent Runtime — MVP 实施路线

> 版本：2026-06-23 · 基于现役代码状态
> 当前阶段：🚩 **MVP0–MVP3 已完成，MVP4-A 只读 Source/Infra 下探已进入收敛验收**

---

## 一、路线总图

```
MVP0 ████████████████████████████████████ 已完成
MVP1 ████████████████████████████████████ 已完成
MVP2 ████████████████████████████████████ 已完成
MVP3 ████████████████████████████████████ 已完成
MVP4 ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░ MVP4-A 收敛验收中，配置写入未启动
MVP5 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 规划中
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

## 三、下一阶段：MVP4 — SCENE→SOURCE→INFRA 下探

**优先级**：中高 · 当前先收敛 MVP4-A 只读发现，不进入配置写入

**目标**：缺完整 Scene 时先只读下探 HTTP/SQL Source 和基础配置线索，结构化记录父子缺口并在前端展示缺口树；子缺口完成后回弹父缺口和无需人工确认的配置写入留到后续 MVP4-B。

### 范围

| 包括 | 不包括 |
|---|---|
| 扩展 `RequirementLayer`：SCENE / SOURCE / INFRA | 人工审批策略（ASK_ALWAYS/DELEGATED/FULL） |
| Requirement 父子关系（子缺口→父缺口回弹） | 自动生成 Scene（只搜索现有 Source） |
| SourceCandidate / InfraCandidate | 自由 LLM 规划 |
| 只读搜索 + WAITING_USER 展示 | |
| MVP4-B 配置写入决策：写入不需要人工确认，但必须有确定性校验、权限/环境边界和审计 | |

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

3. **Step 3：无需人工确认的配置写入（未启动，后续 MVP4-B）**
   - 系统校验通过后写入 Source/Infra/Scene 配置，不再把“人工确认”作为默认门禁
   - 写入前必须完成确定性契约校验、权限/环境边界检查和审计记录
   - 写入后回弹父 Requirement
   - 重新 resolve 父缺口

### 验收标准

- 「没有完整的已支付订单 Scene，但有创建订单 HTTP Source + 支付 HTTP Source」→ 只读下探→记录 SOURCE/INFRA 子缺口→WAITING_USER 展示
- 缺口树在前端可展示，并能看到每层 proposal / Source / Infra 摘要
- 不发生 Source、Infra 或 Scene 配置写入
- 不引入 Capability Graph
- 不引入自由 LLM 规划

### 前置条件

- [x] TimelineResponse 已扩展展示多 Layer 缺口
- [x] `RequirementLayer.SOURCE / INFRA` 和 `parent_requirement_id` 已进入代码
- [x] Source/Infra 只读发现后端测试已存在
- [x] frontend/agent-runtime-page.tsx 支持缺口树展示
- [x] MVP4-A 相关前后端回归集已通过（全量 frontend check 仍有既有 lint 债）

---

## 四、后续规划（MVP5–MVP7）

### MVP5：契约漂移 + UNKNOWN_STATE 对账

**优先级**：中 · 在 MVP4 后启动

**目标**：
- 执行前/恢复前校验 Scene 合约 hash
- UNKNOWN_STATE 人工确认成功后可继续推进（非只失败收口）
- 契约漂移告警

**关键设计点**：
- 已有地基：`SceneCandidate.contract_hash`、plan step spec payload
- 新增 `CONTRACT_DRIFT` verdict / suspend_reason
- UNKNOWN_STATE 双路径：成功→继续、失败→收口

**验收标准**：
- 超时后用户确认「实际成功」→ 可继续后续只读验证或终态
- 恢复前合约漂移 → WAITING_USER 告警
- 超时后不会普通补参重放

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

### Step C：MVP4-A 收敛验收（当前）

- [x] 写 PRD / design / implement
- [x] 明确 Requirement 父子关系和回弹规则边界
- [x] 明确 SourceCandidate / InfraCandidate 最小字段
- [x] 前端缺口树展示 SCENE -> SOURCE -> INFRA
- [x] 跑通前后端 MVP4-A 相关回归集
- [x] 明确 MVP4-B 配置写入不需要人工确认；后续设计只保留确定性校验、权限/环境边界和审计要求

---

## 六、测试基线

**现役测试**：**107 passed + 1 known-fail**

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
uv run pytest tests/test_gdp_datagen_api_method_contract.py -q
uv run pytest tests/test_gdp_datagen_pydantic_docs.py -q
```

边界守护：
```powershell
uv run pytest tests/test_gdp_agent_runtime_boundaries.py -q
```
