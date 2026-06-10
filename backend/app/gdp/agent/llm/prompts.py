"""GDP Agent 模型提示词。"""

GDP_LLM_SYSTEM_PROMPT = """你是 GDP Datagen Agent 的业务决策模型。
你只能输出一个 JSON 对象，不能输出 Markdown、代码块或额外解释。
你只负责给出结构化决策建议，不能直接执行 HTTP、SQL、写库或发布场景。
所有判断必须围绕用户造数目标、已有上下文和运行安全边界展开。"""


GDP_GOAL_NORMALIZATION_PROMPT = """请归一化用户造数目标，并抽取可用于后续造数流程的结构化信息。

输出 JSON Schema 语义：
- normalizedIntent: 清晰、完整、中文优先的目标描述，不改变用户原意
- envCode: 仅可填写 DEV、TEST、PRE、PROD 或 null
- taskType: 简短任务类型，例如 CREATE_ORDER、PAY_ORDER、QUERY_ORDER、CUSTOM
- businessDomain: 业务域，例如 交易、支付、会员、营销，无法判断填 null
- userInputs: 只抽取用户明确给出的结构化输入，不要编造
- subGoals: 可执行子目标列表，每项包含 goal、phaseHint、requiredInputs、expectedOutputs
- missingInformation: 缺失但后续可能需要追问的信息
- confidence: 0 到 1
- reason: 中文说明

用户目标：
{user_intent}

已有结构化输入：
{user_inputs}

外部已解析环境：
{env_code}
"""


GDP_REFLECTION_PROMPT = """请判断最近一次造数场景执行结果是否已经满足用户总体目标。

输出 JSON Schema 语义：
- completed: 是否已经满足总体目标
- nextAction: 只能是 FINISH_OR_VERIFY、SEARCH_NEXT_SCENE、FAIL_TASK
- reason: 中文说明
- confidence: 0 到 1
- missingInformation: 未完成时仍缺失的信息
- evidence: 支撑判断的关键字段、状态或错误

用户总体目标：
{goal}

场景执行结果：
{scene_result}

任务上下文摘要：
{context_summary}
"""


GDP_SCENE_CANDIDATE_PROMPT = """请在已有场景候选中判断哪个最适合复用。

输出 JSON Schema 语义：
- decision: 只能是 USE_SCENE、ASK_USER、NO_MATCH
- sceneCode: decision 为 USE_SCENE 或 ASK_USER 时填写候选中的 sceneCode；NO_MATCH 时为 null
- reason: 中文说明
- confidence: 0 到 1
- missingInputs: 该场景仍缺失的必填入参
- requiresUserConfirmation: 候选语义不够明确时为 true；业务写入审批由系统另行处理
- candidateRank: 只包含候选中的 sceneCode，按推荐顺序排序
- evidence: 支撑判断的候选契约字段、规则分数或变量证据

判断规则：
- 只能选择候选列表中存在的 sceneCode，不能编造。
- 如果候选不能覆盖用户总体目标，输出 NO_MATCH。
- 如果多个候选差异不足或置信度低，输出 ASK_USER。
- 不要因为场景有副作用就输出 ASK_USER，副作用会由系统审批链处理。

用户总体目标：
{goal}

用户结构化输入：
{user_inputs}

变量栈摘要：
{visible_variables}

候选场景：
{candidates}

任务上下文摘要：
{context_summary}
"""


GDP_SOURCE_CANDIDATE_PROMPT = """请在 HTTP/SQL Source 候选中判断哪个最适合生成造数场景。

输出 JSON Schema 语义：
- decision: 只能是 USE_SOURCE、ASK_USER、NO_MATCH
- sourceCode: decision 为 USE_SOURCE 或 ASK_USER 时填写候选中的 sourceCode；NO_MATCH 时为 null
- sourceType: HTTP 或 SQL；无法确定时为 null
- reason: 中文说明
- confidence: 0 到 1
- missingInputs: 该 Source 生成场景仍缺失的必填入参
- requiresUserConfirmation: 候选语义不够明确时为 true；配置发布审批由系统另行处理
- generationStrategy: 使用该 Source 生成场景的简短策略
- candidateRank: 只包含候选中的 sourceCode，按推荐顺序排序
- evidence: 支撑判断的候选契约字段、规则分数或变量证据

判断规则：
- 只能选择候选列表中存在的 sourceCode，不能编造。
- 如果候选不能支撑用户总体目标，输出 NO_MATCH。
- 如果多个候选差异不足或置信度低，输出 ASK_USER。
- 不要因为 Source 会生成配置或场景就输出 ASK_USER，配置写入会由系统审批链处理。

用户总体目标：
{goal}

用户结构化输入：
{user_inputs}

变量栈摘要：
{visible_variables}

候选 Source：
{candidates}

任务上下文摘要：
{context_summary}
"""


GDP_SOURCE_CONFIG_DRAFT_PROMPT = """当前没有可复用的 HTTP/SQL Source。请根据用户目标生成一个 Source 配置草稿，或说明需要追问的信息。

输出 JSON Schema 语义：
- decision: 只能是 DRAFT_SOURCE、ASK_USER、NO_DRAFT
- sourceType: DRAFT_SOURCE 时只能是 HTTP 或 SQL；无法判断时为 null
- configDraft: HttpSourceConfig 或 SqlSourceConfig 草稿 JSON；ASK_USER/NO_DRAFT 时可为空对象
- infraReadiness: 基于“基础配置摘要”判断的配置可用性，建议包含 recommendedSysCode、recommendedDatasourceCode、missingInfraFields、canUseExistingInfra、reason
- missingInformation: 仍需要用户补充的信息，例如系统编码、接口路径、请求字段、SQL 文本、数据源编码
- confidence: 0 到 1
- reason: 中文说明
- assumptions: 草稿中做出的假设，必须显式列出
- evidence: 支撑草稿的用户目标、结构化输入或变量证据

草稿边界：
- 只生成配置草稿，不会自动保存、测试、执行 HTTP 或 SQL。
- 不要编造密码、token、Authorization、Cookie 等敏感字段。
- HTTP method 只能是 GET 或 POST。
- sysCode、datasourceCode 必须优先使用基础配置摘要中已存在且启用的配置；基础配置摘要里只有 usable=true 的系统、环境、服务端点、数据源才可视为可直接复用。
- 如果目标配置不存在、未启用或未配置，不要硬编成事实，应写入 missingInformation 和 infraReadiness.missingInfraFields。
- 生成 HTTP 草稿时，必须检查目标 envCode 下是否存在该 sysCode 的 serviceEndpoint；缺失时仍可草拟 Source，但必须提示先补 serviceEndpoint。
- 生成 SQL 草稿时，必须检查目标 envCode + sysCode 下是否存在 datasourceCode；缺失时仍可草拟 Source，但必须提示先补 datasource。
- 如果缺少路径、SQL 文本、系统编码等关键事实，优先输出 ASK_USER，并把可推断字段放入 configDraft。
- HTTP 草稿尽量贴近 HttpSourceConfig：sourceCode、sourceName、tags、capabilityType、businessDomain、sideEffects、agentDescription、sysCode、path、method、requestMapping、bodySchema、responseSchema、outputMapping。
- SQL 草稿尽量贴近 SqlSourceConfig：sourceCode、sourceName、tags、capabilityType、businessDomain、sideEffects、agentDescription、sysCode、datasourceCode、operation、sqlText、parameters、resultFields。

用户总体目标：
{goal}

目标环境：
{env_code}

用户结构化输入：
{user_inputs}

变量栈摘要：
{visible_variables}

任务上下文摘要：
{context_summary}

基础配置摘要：
{infra_summary}

已归一化目标：
{normalized_goal}
"""


GDP_SCENE_DRAFT_ENHANCEMENT_PROMPT = """请基于后端已经生成的 SceneDefinition 草稿，补全面向用户审批、Agent 检索和运行校验更友好的语义信息。

输出 JSON Schema 语义：
- decision: 只能是 ENHANCE_SCENE、KEEP_ORIGINAL、ASK_USER
- sceneDraft: decision 为 ENHANCE_SCENE 时填写完整 SceneDefinition JSON；其他情况可为空对象
- missingInformation: 仍需要用户补充的信息
- confidence: 0 到 1
- reason: 中文说明
- assumptions: 草稿补全中做出的假设，必须显式列出
- evidence: 支撑补全的用户目标、Source 契约、字段或上下文证据

草稿边界：
- 你只生成 SceneDefinition 草稿建议，不会自动保存、发布、执行 HTTP 或 SQL。
- sceneDraft.sceneCode 必须保持为基础草稿中的 sceneCode，不能改名、不能编造新场景编码。
- 不要删除或改写步骤 templateRef、sourceCode、sourceNameAtSnapshot、sourceUpdatedAtSnapshot 等来源快照字段。
- 不要改写 HTTP path、method、requestMapping、bodySchema、SQL 文本、datasourceCode、paramMapping 等运行行为字段。
- HTTP method 只能是 GET 或 POST。
- 不要编造密码、token、Authorization、Cookie、连接串等敏感信息。
- 优先补全 sceneName、sceneRemark、tags、businessDomain、agentDescription、inputSchema/resultSchema 字段中文名和备注、步骤 description、outputMeta。
- 如果基础草稿已经足够或无法可靠补全，输出 KEEP_ORIGINAL。
- 如果缺少关键业务事实，输出 ASK_USER，并把缺失项放入 missingInformation。

用户总体目标：
{goal}

用户结构化输入：
{user_inputs}

变量栈摘要：
{visible_variables}

候选 Source 契约：
{source_contract}

后端基础 SceneDefinition 草稿：
{base_scene_draft}

任务上下文摘要：
{context_summary}

已归一化目标：
{normalized_goal}
"""
