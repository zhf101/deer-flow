"""GDP Agent Runtime 持久化接口。MVP 使用内存实现。"""

from __future__ import annotations

from typing import Any

from .models import (
    Action,
    ActionAttempt,
    Evidence,
    Observation,
    PlanStep,
    TaskRun,
    Variable,
    Verdict,
)


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
        self._payloads: dict[str, Any] = {}

    def save_task_run(self, task_run: TaskRun) -> None:
        self._task_runs[task_run.task_run_id] = task_run

    def get_task_run(self, task_run_id: str) -> TaskRun:
        if task_run_id not in self._task_runs:
            raise EntityNotFoundError("TaskRun", task_run_id)
        return self._task_runs[task_run_id]

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

    def save_payload(self, ref: str, payload: Any) -> None:
        """按引用保存完整载荷。MVP 内存实现只在进程内可用。"""
        self._payloads[ref] = payload

    def get_payload(self, ref: str) -> Any:
        """读取完整载荷。"""
        if ref not in self._payloads:
            raise EntityNotFoundError("Payload", ref)
        return self._payloads[ref]

    def get_timeline(self, task_run_id: str) -> dict[str, Any]:
        """获取 TaskRun 的完整时间线：Steps + Actions + Attempts + Evidence + Verdicts。"""
        steps = [s for s in self._steps.values() if s.task_run_id == task_run_id]
        actions = [a for a in self._actions.values() if a.task_run_id == task_run_id]
        attempts = [a for a in self._attempts.values() if a.action_id in {act.action_id for act in actions}]
        observations = [o for o in self._observations.values() if o.task_run_id == task_run_id]
        evidences = [e for e in self._evidences.values() if e.task_run_id == task_run_id]
        verdicts = [v for v in self._verdicts.values() if v.task_run_id == task_run_id]
        variables = [v for v in self._variables.values() if v.task_run_id == task_run_id]
        return {
            "task_run_id": task_run_id,
            "steps": [s.model_dump(mode="json") for s in steps],
            "actions": [a.model_dump(mode="json") for a in actions],
            "attempts": [a.model_dump(mode="json") for a in attempts],
            "observations": [o.model_dump(mode="json") for o in observations],
            "evidences": [e.model_dump(mode="json") for e in evidences],
            "verdicts": [v.model_dump(mode="json") for v in verdicts],
            "variables": [v.model_dump(mode="json") for v in variables],
        }

    def has_started_idempotency_key(self, idempotency_key: str, *, exclude_action_id: str | None = None) -> bool:
        """检查同幂等键是否已经发起过写请求。"""
        return any(
            action.idempotency_key == idempotency_key
            and action.action_id != exclude_action_id
            and bool(action.attempt_ids)
            for action in self._actions.values()
        )
