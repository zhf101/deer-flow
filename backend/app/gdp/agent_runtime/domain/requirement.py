"""资源缺口与候选场景领域模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .identifiers import HashValue, StepId, TaskRunId


class RequirementLayer(StrEnum):
    """资源缺口层级，定义系统为用户寻找的资源类型。

    当前仅支持 SCENE（已发布造数场景），未来扩展 SOURCE（数据源）和 INFRA（基础设施配置）。
    """

    SCENE = "SCENE"  # 寻找已发布的造数场景来满足用户需求


class RequirementStatus(StrEnum):
    """资源缺口状态，反映系统为用户找到合适场景的进展。

    PENDING：缺口刚创建，尚未开始搜索候选场景。
    RESOLVING：已搜索到候选场景，等待系统自动选定或用户手动选择。
    SATISFIED：已选定场景编码，缺口已满足，可以进入执行阶段。
    FAILED：无法满足缺口（零候选或用户放弃），可能导致任务失败。
    """

    PENDING = "PENDING"
    RESOLVING = "RESOLVING"
    SATISFIED = "SATISFIED"
    FAILED = "FAILED"


class Requirement(BaseModel):
    """用户造数步骤的资源缺口——"为了完成这一步，系统需要找到一个合适的造数场景"。

    业务目标：结构化表达当前步骤需要什么资源，追踪搜索进度和选定结果。
    当前动作：在 workflows/start_workflow.py 中创建，驱动 catalog 搜索和候选选择流程。
    预期结果：缺口被满足（SATISFIED）后进入场景执行阶段；无法满足（FAILED）则任务收口。
    """

    requirement_id: str = Field(description="缺口唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    step_id: StepId = Field(description="所属业务步骤 ID，标识这个缺口是为了完成哪个步骤。")
    layer: RequirementLayer = Field(description="缺口层级，当前固定 SCENE（寻找已发布场景）。")
    goal: str = Field(min_length=1, description="缺口要满足的目标描述，通常继承步骤的业务目标。")
    status: RequirementStatus = Field(description="缺口当前状态，决定流程走向。")
    proposal_id: str | None = Field(default=None, description="当前候选集 Proposal ID，关联到本次搜索结果。")
    selected_scene_code: str | None = Field(default=None, description="已选定的场景编码，SATISFIED 时必有值。")
    blacklist: list[str] = Field(default_factory=list, description="已失败或被拒的场景编码黑名单，重搜时自动排除。")
    created_at: datetime = Field(description="缺口创建时间。")
    updated_at: datetime = Field(description="缺口最近更新时间。")


class SceneCandidate(BaseModel):
    """搜索结果中的一个候选造数场景，来自 Catalog 的确定性检索。

    业务目标：为用户展示"系统找到了哪些可用的造数方案"，每个候选包含评分、
    命中理由、缺失入参和是否需要审批等信息，帮助用户或系统做出选择。
    注意：这是事实数据（Catalog 检索结果），不是 LLM 建议。
    """

    scene_code: str = Field(description="候选场景编码，唯一标识一个已发布的造数场景。")
    scene_name: str = Field(description="候选场景名称，直接展示给用户。")
    score: float = Field(ge=0.0, le=1.0, description="Catalog 综合评分，仅用于排序候选，不作为事实依据。")
    reasons: list[str] = Field(default_factory=list, description="命中理由列表，如'目标语义匹配''环境可用'，可直接展示给用户。")
    missing_inputs: list[str] = Field(default_factory=list, description="当前入参和变量栈尚不能绑定的必填字段，非空时需等用户补充后才能执行。")
    requires_confirmation: bool = Field(description="执行前是否需要用户审批，有写副作用的场景为 true。")
    contract_hash: HashValue = Field(description="候选契约快照哈希，执行前记录，未来用于检测场景契约是否发生漂移。")


class ProposalStatus(StrEnum):
    """候选集状态，反映一次搜索产出的候选方案的选定进展。

    PENDING：候选已生成，等待选定（系统自动或用户手动）。
    SELECTED：某个候选已被选定，即将进入执行准备阶段。
    REJECTED：全部候选被拒或用户放弃，可能导致重新搜索或任务失败。
    """

    PENDING = "PENDING"
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"


class SelectionSource(StrEnum):
    """选定场景的来源，用于审计"是谁/什么选了这个场景"。

    AUTO：系统规则自动选定（单候选高置信、入参齐全、无需审批）。
    USER：用户在多候选中手动选定。
    LLM：采纳了 AI 模型的排序建议，但仍经规则校验后采纳。
    EXPLICIT：用户启动时直接指定了场景编码。
    """

    AUTO = "AUTO"
    USER = "USER"
    LLM = "LLM"
    EXPLICIT = "EXPLICIT"


class RequirementProposal(BaseModel):
    """一次搜索产出的候选场景集合和选择结果。

    业务目标：记录"系统搜到了哪些场景、最终选了哪个、谁选的"，
    是连接搜索（catalog.search）和选定（apply_selection）的中间账本。
    """

    proposal_id: str = Field(description="候选集唯一标识。")
    task_run_id: TaskRunId = Field(description="所属造数任务 ID。")
    step_id: StepId = Field(description="所属业务步骤 ID。")
    requirement_id: str = Field(description="所属资源缺口 ID，标识这次搜索是为了满足哪个缺口。")
    candidates: list[SceneCandidate] = Field(default_factory=list, description="按评分倒序排列的候选场景列表。")
    query_terms: list[str] = Field(default_factory=list, description="参与检索的关键词和别名，供用户理解搜索条件。")
    status: ProposalStatus = Field(description="候选集当前状态。")
    selected_scene_code: str | None = Field(default=None, description="被选定的场景编码，SELECTED 时必有值。")
    selection_source: SelectionSource | None = Field(default=None, description="选定来源：AUTO/USER/LLM/EXPLICIT。")
    created_at: datetime = Field(description="候选集创建时间。")


class SceneSelectionSuggestion(BaseModel):
    """AI 模型在已检索候选中给出的排序建议，只能用于排序参考，不能直接定案。

    这是安全边界的一部分：即使模型给出了排序建议，也必须经过规则校验后才能被采纳。
    """

    ranked_scene_codes: list[str] = Field(default_factory=list, description="AI 建议的候选优先级排序。")
    explanation: str = Field(default="", description="AI 给出的选择解释，供规则校验后参考。")
