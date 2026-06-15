"""造数运行时的内存账本。

记录用户任务从创建到完成的全部事实，包括步骤、动作、证据、判定、变量和决策。
MVP 阶段使用内存实现，所有数据在进程存活期间保持可查；通过 snapshot/restore
机制保护用户任务数据不会因外部持久化失败而丢失；通过 export_task_run 导出
完整账本供数据库落库，保存用户的造数历史。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..models import (
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
from .snapshot import build_task_run_snapshot
from .timeline import build_timeline


class EntityNotFoundError(Exception):
    """账本中找不到指定实体。

    用户查看任务详情或时间线时，如果请求的步骤、动作、证据等记录不存在，
    系统抛出此异常，API 层会转为用户友好的 404 提示。
    """

    def __init__(self, entity_type: str, entity_id: str) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} not found: {entity_id}")


class MemoryLedger:
    """造数运行时内存账本。

    业务目标：在进程内存中维护用户造数任务的全部事实记录，供编排引擎实时读写、
    前端轮询展示、以及最终落库归档。
    当前动作：MVP 阶段使用纯内存字典存储，线程不安全，仅用于单进程开发验证。
    预期结果：用户的每个造数任务都有完整的执行账本，可随时查看历史。
    """

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
        self._payloads: dict[str, dict[str, Any]] = {}

    def save_task_run(self, task_run: TaskRun) -> None:
        self._task_runs[task_run.task_run_id] = task_run

    def get_task_run(self, task_run_id: str) -> TaskRun:
        if task_run_id not in self._task_runs:
            raise EntityNotFoundError("TaskRun", task_run_id)
        return self._task_runs[task_run_id]

    def list_task_runs(self) -> list[TaskRun]:
        """返回用户所有造数任务列表，按最近更新时间倒序，前端任务列表页直接展示。"""
        return sorted(self._task_runs.values(), key=lambda item: item.updated_at, reverse=True)

    def snapshot(self) -> dict[str, Any]:
        """创建内存账本快照。

        业务目标：在执行外部持久化（如写数据库）之前先拍照，万一持久化失败可以
        回滚到一致状态，保护用户任务数据不丢失、不脏写。
        """
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
        """恢复内存账本快照。

        业务目标：当外部持久化失败时，用之前的快照恢复账本到一致状态，
        确保用户任务不会因为落库失败而出现数据不一致。
        预期结果：用户重新查看任务时，所有数据仍然完整正确。
        """
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

    def get_active_requirement(self, task_run_id: str, *, step_id: str | None = None) -> Requirement | None:
        """返回该任务当前步骤最近创建的缺口记录，用于编排引擎判断下一步应填补哪个缺口。"""
        reqs = [r for r in self._requirements.values() if r.task_run_id == task_run_id]
        if step_id is not None:
            reqs = [r for r in reqs if r.step_id == step_id]
        if not reqs:
            return None
        return max(reqs, key=lambda r: r.created_at)

    def save_proposal(self, proposal: RequirementProposal) -> None:
        self._proposals[proposal.proposal_id] = proposal

    def get_proposal(self, proposal_id: str) -> RequirementProposal:
        if proposal_id not in self._proposals:
            raise EntityNotFoundError("RequirementProposal", proposal_id)
        return self._proposals[proposal_id]

    def get_latest_proposal(
        self,
        task_run_id: str,
        *,
        step_id: str | None = None,
        requirement_id: str | None = None,
    ) -> RequirementProposal | None:
        """返回该任务当前步骤或缺口最近的候选提案，用于判断是否已有候选等待用户确认。"""
        proposals = [p for p in self._proposals.values() if p.task_run_id == task_run_id]
        if step_id is not None:
            proposals = [p for p in proposals if p.step_id == step_id]
        if requirement_id is not None:
            proposals = [p for p in proposals if p.requirement_id == requirement_id]
        if not proposals:
            return None
        return max(proposals, key=lambda p: p.created_at)

    def save_decision(self, decision: DecisionRecord) -> None:
        """保存一条决策审计记录，记录系统在编排过程中做出的关键决策，供用户事后追溯。"""
        self._decisions[decision.decision_id] = decision

    def list_decisions(self, task_run_id: str) -> list[DecisionRecord]:
        """返回该任务的全部决策审计记录，按时间正序，用户可在详情页追溯每次决策。"""
        decisions = [item for item in self._decisions.values() if item.task_run_id == task_run_id]
        return sorted(decisions, key=lambda item: item.created_at)

    def save_approval_record(self, record: dict[str, Any]) -> None:
        """保存用户审批记录，记录用户对某个场景的批准事实，同一场景不再重复询问。"""
        self._approval_records.append(record)

    def list_approval_records(self, task_run_id: str) -> list[dict[str, Any]]:
        """返回该任务的全部审批记录，前端可展示用户已批准过的场景列表。"""
        return [item for item in self._approval_records if item.get("task_run_id") == task_run_id]

    def has_approval_record(self, task_run_id: str, scene_code: str) -> bool:
        """判断某个场景是否已被用户批准，已批准则跳过重复确认，减少用户交互次数。"""
        return any(
            item.get("task_run_id") == task_run_id and item.get("scene_code") == scene_code
            for item in self._approval_records
        )

    def save_payload(self, task_run_id: str, ref: str, payload: Any) -> None:
        """保存造数过程中的完整请求/响应载荷，供用户事后排查接口调用细节。"""
        self._payloads.setdefault(task_run_id, {})[ref] = payload

    def get_payload(self, task_run_id: str, ref: str) -> Any:
        """读取某个造数任务的完整载荷，用于调试或导出审计记录。"""
        payloads = self._payloads.get(task_run_id, {})
        if ref not in payloads:
            raise EntityNotFoundError("Payload", ref)
        return payloads[ref]

    def export_task_run(self, task_run_id: str) -> dict[str, Any]:
        """导出单个造数任务的完整账本快照。

        业务目标：将内存中的全部事实（步骤、动作、尝试、证据、判定、变量、缺口、
        候选、决策、审批、载荷）打包导出，供数据库仓储持久化，保存用户的造数历史。
        预期结果：用户的造数记录在进程重启后仍然可以从数据库恢复查看。
        """
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
        return build_task_run_snapshot(
            task_run=task_run,
            steps=steps,
            actions=actions,
            attempts=attempts,
            observations=observations,
            evidences=evidences,
            verdicts=verdicts,
            variables=variables,
            requirements=requirements,
            proposals=proposals,
            decisions=decisions,
            approval_records=self.list_approval_records(task_run_id),
            payloads=self._payloads.get(task_run_id, {}),
        )

    def get_timeline(self, task_run_id: str) -> dict[str, Any]:
        """获取造数任务的完整时间线。

        业务目标：汇总任务的所有步骤、动作、尝试、观测、证据、判定、变量、缺口、
        候选和决策，生成前端可渲染的时间线视图，让用户看到造数过程的每一步进展。
        预期结果：用户在前端详情页看到完整时间线，包括每个步骤的状态、每步的证据
        和最终判定结果。候选集使用安全投影，不暴露敏感入参。
        """
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
        return build_timeline(
            task_run_id=task_run_id,
            steps=steps,
            actions=actions,
            attempts=attempts,
            observations=observations,
            evidences=evidences,
            verdicts=verdicts,
            variables=variables,
            requirements=requirements,
            proposals=proposals,
            decisions=decisions,
            approval_records=approval_records,
        )

    def has_started_idempotency_key(self, idempotency_key: str, *, exclude_action_id: str | None = None) -> bool:
        """检查同一幂等键是否已经发起过写请求，防止用户任务重试时重复造数。"""
        return any(
            action.idempotency_key == idempotency_key
            and action.action_id != exclude_action_id
            and bool(action.attempt_ids)
            for action in self._actions.values()
        )


Store = MemoryLedger
