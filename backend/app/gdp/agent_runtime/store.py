"""GDP Agent Runtime 持久化接口。MVP 使用内存实现。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import (
    Action,
    ActionAttempt,
    DecisionRecord,
    Evidence,
    Observation,
    PlanStep,
    Requirement,
    RequirementProposal,
    TaskRun,
    Variable,
    Verdict,
)


def _proposal_view(proposal: RequirementProposal) -> dict[str, Any]:
    """Proposal 的 timeline 投影。候选只输出 scene_code / scene_name / score / reasons /
    missing_inputs / requires_confirmation，不输出敏感入参原值（验收标准 11）。
    """
    return {
        "proposal_id": proposal.proposal_id,
        "task_run_id": proposal.task_run_id,
        "step_id": proposal.step_id,
        "requirement_id": proposal.requirement_id,
        "status": proposal.status.value,
        "selected_scene_code": proposal.selected_scene_code,
        "selection_source": proposal.selection_source.value if proposal.selection_source else None,
        "query_terms": list(proposal.query_terms),
        "created_at": proposal.created_at.isoformat(),
        "candidates": [
            {
                "scene_code": c.scene_code,
                "scene_name": c.scene_name,
                "score": c.score,
                "reasons": list(c.reasons),
                "missing_inputs": list(c.missing_inputs),
                "requires_confirmation": c.requires_confirmation,
            }
            for c in proposal.candidates
        ],
    }


class EntityNotFoundError(Exception):
    """实体未找到。"""

    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} not found: {entity_id}")


class Store:
    """MVP 内存存储。线程不安全，仅用于单进程开发验证。"""

    def __init__(self) -> None:
        self._task_runs: dict[str, TaskRun] = {}
        self._steps: dict[str, PlanStep] = {}
        self._actions: dict[str, Action] = {}
        self._attempts: dict[str, ActionAttempt] = {}
        self._observations: dict[str, Observation] = {}
        self._evidences: dict[str, Evidence] = {}
        self._verdicts: dict[str, Verdict] = {}
        self._variables: dict[str, Variable] = {}
        self._requirements: dict[str, Requirement] = {}
        self._proposals: dict[str, RequirementProposal] = {}
        self._decisions: dict[str, DecisionRecord] = {}
        self._approval_records: list[dict[str, Any]] = []
        self._payloads: dict[str, Any] = {}

    def save_task_run(self, task_run: TaskRun) -> None:
        self._task_runs[task_run.task_run_id] = task_run

    def get_task_run(self, task_run_id: str) -> TaskRun:
        if task_run_id not in self._task_runs:
            raise EntityNotFoundError("TaskRun", task_run_id)
        return self._task_runs[task_run_id]

    def list_task_runs(self) -> list[TaskRun]:
        """返回内存中的 TaskRun 列表。"""
        return sorted(self._task_runs.values(), key=lambda item: item.updated_at, reverse=True)

    def snapshot(self) -> dict[str, Any]:
        """创建内存账本快照，用于外部持久化失败时回滚。"""
        return {
            "task_runs": deepcopy(self._task_runs),
            "steps": deepcopy(self._steps),
            "actions": deepcopy(self._actions),
            "attempts": deepcopy(self._attempts),
            "observations": deepcopy(self._observations),
            "evidences": deepcopy(self._evidences),
            "verdicts": deepcopy(self._verdicts),
            "variables": deepcopy(self._variables),
            "requirements": deepcopy(self._requirements),
            "proposals": deepcopy(self._proposals),
            "decisions": deepcopy(self._decisions),
            "approval_records": deepcopy(self._approval_records),
            "payloads": deepcopy(self._payloads),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """恢复内存账本快照。"""
        self._task_runs = deepcopy(snapshot["task_runs"])
        self._steps = deepcopy(snapshot["steps"])
        self._actions = deepcopy(snapshot["actions"])
        self._attempts = deepcopy(snapshot["attempts"])
        self._observations = deepcopy(snapshot["observations"])
        self._evidences = deepcopy(snapshot["evidences"])
        self._verdicts = deepcopy(snapshot["verdicts"])
        self._variables = deepcopy(snapshot["variables"])
        self._requirements = deepcopy(snapshot["requirements"])
        self._proposals = deepcopy(snapshot["proposals"])
        self._decisions = deepcopy(snapshot["decisions"])
        self._approval_records = deepcopy(snapshot["approval_records"])
        self._payloads = deepcopy(snapshot["payloads"])

    def save_step(self, step: PlanStep) -> None:
        self._steps[step.step_id] = step

    def get_step(self, step_id: str) -> PlanStep:
        if step_id not in self._steps:
            raise EntityNotFoundError("PlanStep", step_id)
        return self._steps[step_id]

    def save_action(self, action: Action) -> None:
        self._actions[action.action_id] = action

    def get_action(self, action_id: str) -> Action:
        if action_id not in self._actions:
            raise EntityNotFoundError("Action", action_id)
        return self._actions[action_id]

    def save_attempt(self, attempt: ActionAttempt) -> None:
        self._attempts[attempt.attempt_id] = attempt

    def get_attempt(self, attempt_id: str) -> ActionAttempt:
        if attempt_id not in self._attempts:
            raise EntityNotFoundError("ActionAttempt", attempt_id)
        return self._attempts[attempt_id]

    def save_observation(self, observation: Observation) -> None:
        self._observations[observation.observation_id] = observation

    def get_observation(self, observation_id: str) -> Observation:
        if observation_id not in self._observations:
            raise EntityNotFoundError("Observation", observation_id)
        return self._observations[observation_id]

    def save_evidence(self, evidence: Evidence) -> None:
        self._evidences[evidence.evidence_id] = evidence

    def get_evidence(self, evidence_id: str) -> Evidence:
        if evidence_id not in self._evidences:
            raise EntityNotFoundError("Evidence", evidence_id)
        return self._evidences[evidence_id]

    def save_verdict(self, verdict: Verdict) -> None:
        self._verdicts[verdict.verdict_id] = verdict

    def get_verdict(self, verdict_id: str) -> Verdict:
        if verdict_id not in self._verdicts:
            raise EntityNotFoundError("Verdict", verdict_id)
        return self._verdicts[verdict_id]

    def save_variable(self, variable: Variable) -> None:
        self._variables[variable.variable_id] = variable

    def get_variable(self, variable_id: str) -> Variable:
        if variable_id not in self._variables:
            raise EntityNotFoundError("Variable", variable_id)
        return self._variables[variable_id]

    def save_requirement(self, requirement: Requirement) -> None:
        self._requirements[requirement.requirement_id] = requirement

    def get_requirement(self, requirement_id: str) -> Requirement:
        if requirement_id not in self._requirements:
            raise EntityNotFoundError("Requirement", requirement_id)
        return self._requirements[requirement_id]

    def get_active_requirement(self, task_run_id: str) -> Requirement | None:
        """返回该 TaskRun 最近创建的 Requirement（第二阶段单 step 单缺口）。"""
        reqs = [r for r in self._requirements.values() if r.task_run_id == task_run_id]
        if not reqs:
            return None
        return max(reqs, key=lambda r: r.created_at)

    def save_proposal(self, proposal: RequirementProposal) -> None:
        self._proposals[proposal.proposal_id] = proposal

    def get_proposal(self, proposal_id: str) -> RequirementProposal:
        if proposal_id not in self._proposals:
            raise EntityNotFoundError("RequirementProposal", proposal_id)
        return self._proposals[proposal_id]

    def get_latest_proposal(self, task_run_id: str) -> RequirementProposal | None:
        """返回该 TaskRun 最近创建的 Proposal。"""
        proposals = [p for p in self._proposals.values() if p.task_run_id == task_run_id]
        if not proposals:
            return None
        return max(proposals, key=lambda p: p.created_at)

    def save_decision(self, decision: DecisionRecord) -> None:
        """保存一条决策审计记录。"""
        self._decisions[decision.decision_id] = decision

    def list_decisions(self, task_run_id: str) -> list[DecisionRecord]:
        """返回该 TaskRun 的决策审计记录。"""
        decisions = [item for item in self._decisions.values() if item.task_run_id == task_run_id]
        return sorted(decisions, key=lambda item: item.created_at)

    def save_approval_record(self, record: dict[str, Any]) -> None:
        """保存审批事实。"""
        self._approval_records.append(record)

    def list_approval_records(self, task_run_id: str) -> list[dict[str, Any]]:
        """返回该 TaskRun 的审批事实。"""
        return [item for item in self._approval_records if item.get("task_run_id") == task_run_id]

    def has_approval_record(self, task_run_id: str, scene_code: str) -> bool:
        """判断某个场景是否已审批。"""
        return any(
            item.get("task_run_id") == task_run_id and item.get("scene_code") == scene_code
            for item in self._approval_records
        )

    def save_payload(self, ref: str, payload: Any) -> None:
        """按引用保存完整载荷。MVP 内存实现只在进程内可用。"""
        self._payloads[ref] = payload

    def get_payload(self, ref: str) -> Any:
        """读取完整载荷。"""
        if ref not in self._payloads:
            raise EntityNotFoundError("Payload", ref)
        return self._payloads[ref]

    def export_task_run(self, task_run_id: str) -> dict[str, Any]:
        """导出单个 TaskRun 的完整账本快照，供数据库仓储持久化。"""
        task_run = self.get_task_run(task_run_id)
        steps = [s for s in self._steps.values() if s.task_run_id == task_run_id]
        actions = [a for a in self._actions.values() if a.task_run_id == task_run_id]
        action_ids = {action.action_id for action in actions}
        attempts = [a for a in self._attempts.values() if a.action_id in action_ids]
        observations = [o for o in self._observations.values() if o.task_run_id == task_run_id]
        evidences = [e for e in self._evidences.values() if e.task_run_id == task_run_id]
        verdicts = [v for v in self._verdicts.values() if v.task_run_id == task_run_id]
        variables = [v for v in self._variables.values() if v.task_run_id == task_run_id]
        requirements = [r for r in self._requirements.values() if r.task_run_id == task_run_id]
        proposals = [p for p in self._proposals.values() if p.task_run_id == task_run_id]
        decisions = self.list_decisions(task_run_id)
        return {
            "task_run": task_run.model_dump(mode="json"),
            "steps": [item.model_dump(mode="json") for item in steps],
            "actions": [item.model_dump(mode="json") for item in actions],
            "attempts": [item.model_dump(mode="json") for item in attempts],
            "observations": [item.model_dump(mode="json") for item in observations],
            "evidences": [item.model_dump(mode="json") for item in evidences],
            "verdicts": [item.model_dump(mode="json") for item in verdicts],
            "variables": [item.model_dump(mode="json") for item in variables],
            "requirements": [item.model_dump(mode="json") for item in requirements],
            "proposals": [item.model_dump(mode="json") for item in proposals],
            "decisions": [item.model_dump(mode="json") for item in decisions],
            "approval_records": self.list_approval_records(task_run_id),
            "payloads": [{"ref": ref, "payload": payload} for ref, payload in self._payloads.items()],
        }

    def get_timeline(self, task_run_id: str) -> dict[str, Any]:
        """获取 TaskRun 的完整时间线：Steps + Actions + Attempts + Evidence + Verdicts。"""
        steps = [s for s in self._steps.values() if s.task_run_id == task_run_id]
        actions = [a for a in self._actions.values() if a.task_run_id == task_run_id]
        attempts = [a for a in self._attempts.values() if a.action_id in {act.action_id for act in actions}]
        observations = [o for o in self._observations.values() if o.task_run_id == task_run_id]
        evidences = [e for e in self._evidences.values() if e.task_run_id == task_run_id]
        verdicts = [v for v in self._verdicts.values() if v.task_run_id == task_run_id]
        variables = [v for v in self._variables.values() if v.task_run_id == task_run_id]
        requirements = [r for r in self._requirements.values() if r.task_run_id == task_run_id]
        proposals = [p for p in self._proposals.values() if p.task_run_id == task_run_id]
        decisions = self.list_decisions(task_run_id)
        approval_records = self.list_approval_records(task_run_id)
        return {
            "task_run_id": task_run_id,
            "steps": [s.model_dump(mode="json") for s in steps],
            "actions": [a.model_dump(mode="json") for a in actions],
            "attempts": [a.model_dump(mode="json") for a in attempts],
            "observations": [o.model_dump(mode="json") for o in observations],
            "evidences": [e.model_dump(mode="json") for e in evidences],
            "verdicts": [v.model_dump(mode="json") for v in verdicts],
            "variables": [v.model_dump(mode="json") for v in variables],
            "requirements": [r.model_dump(mode="json") for r in requirements],
            "proposals": [_proposal_view(p) for p in proposals],
            "decisions": [d.model_dump(mode="json") for d in decisions],
            "approval_records": approval_records,
        }

    def has_started_idempotency_key(self, idempotency_key: str, *, exclude_action_id: str | None = None) -> bool:
        """检查同幂等键是否已经发起过写请求。"""
        return any(
            action.idempotency_key == idempotency_key
            and action.action_id != exclude_action_id
            and bool(action.attempt_ids)
            for action in self._actions.values()
        )
