"""GDP 造数运行时的领域模型兼容导出层。

本文件继续提供历史导入路径 `agent_runtime.models`，避免一次性迁移所有调用方。
新的领域模型已经按语义迁移到 `agent_runtime.domain` 下，再由本文件 re-export。

当前导出的模型涵盖：
- 任务账本（TaskRun）：用户造数目标的完整生命周期记录
- 步骤与动作（PlanStep / Action / ActionAttempt）：目标拆解、场景执行、重试记录
- 证据与判定（Observation / Evidence / Verdict）：从原始响应到结构化结论的判定链
- 变量（Variable）：造数过程中产出和消费的业务数据
- 资源缺口与候选（Requirement / RequirementProposal / SceneCandidate）：为用户目标匹配合适场景的搜索过程
- 审计记录（DecisionRecord）：让用户和运维人员理解"系统为什么这样选择"
- 安全边界（LMProposal）：隔离 AI 模型输出与事实数据，防止模型直接操控任务状态

所有状态机枚举均附带中文语义说明，确保业务含义不被内部编码淹没。
"""

from __future__ import annotations

from .domain.action import Action, ActionAttempt, ActionStatus, ActionType, AttemptStatus
from .domain.config_writeback import ConfigWritebackResult, ConfigWritebackStatus
from .domain.decision import (
    DecisionKind,
    DecisionOption,
    DecisionRecord,
    DecisionRejection,
    DecisionSource,
    DecisionStatus,
)
from .domain.evidence import Evidence, EvidenceFact, FactPredicate, Observation
from .domain.identifiers import (
    ActionId,
    AttemptId,
    EvidenceId,
    HashValue,
    StepId,
    StorageRef,
    TaskRunId,
    VariableId,
    VerdictId,
)
from .domain.requirement import (
    InfraCandidate,
    ProposalStatus,
    Requirement,
    RequirementLayer,
    RequirementProposal,
    RequirementStatus,
    SceneCandidate,
    SceneSelectionSuggestion,
    SelectionSource,
    SourceCandidate,
)
from .domain.safety import LMProposal, reject_lm_proposal
from .domain.step import PlanStep, StepStatus
from .domain.task import ReplyType, StepEdge, SuspendReason, TaskRun, TaskRunStatus
from .domain.variable import Variable, VariableProvenance, VariableSource
from .domain.verdict import Verdict, VerdictType

__all__ = [
    "Action",
    "ActionAttempt",
    "ActionId",
    "ActionStatus",
    "ActionType",
    "AttemptId",
    "AttemptStatus",
    "ConfigWritebackResult",
    "ConfigWritebackStatus",
    "DecisionKind",
    "DecisionOption",
    "DecisionRecord",
    "DecisionRejection",
    "DecisionSource",
    "DecisionStatus",
    "Evidence",
    "EvidenceFact",
    "EvidenceId",
    "FactPredicate",
    "HashValue",
    "InfraCandidate",
    "LMProposal",
    "Observation",
    "PlanStep",
    "ProposalStatus",
    "ReplyType",
    "Requirement",
    "RequirementLayer",
    "RequirementProposal",
    "RequirementStatus",
    "SceneCandidate",
    "SceneSelectionSuggestion",
    "SelectionSource",
    "SourceCandidate",
    "StepEdge",
    "StepId",
    "StepStatus",
    "StorageRef",
    "SuspendReason",
    "TaskRun",
    "TaskRunId",
    "TaskRunStatus",
    "Variable",
    "VariableId",
    "VariableProvenance",
    "VariableSource",
    "Verdict",
    "VerdictId",
    "VerdictType",
    "reject_lm_proposal",
]
