from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from xagent.web.models.dm_run import DMRun, DMRunStep

from ..contracts import ExecutorInput, ExecutorOutput, ResolverInput
from ..executors import ControlExecutor, HTTPExecutor, SQLExecutor
from ..governance import GovernanceService
from ..resolvers import HTTPResolver, SQLResolver


@dataclass
class TrialOrchestrator:
    """最小试跑编排器。

    这层只解决一件事：把已经通过预检的 technical_graph 真的跑起来，并把
    结果稳定回写到 Run / RunStep。
    """

    db: Session
    http_resolver: HTTPResolver = field(default_factory=HTTPResolver)
    sql_resolver: SQLResolver = field(default_factory=SQLResolver)
    control_executor: ControlExecutor = field(default_factory=ControlExecutor)

    def execute_run(
        self,
        run_id: int,
        technical_graph: dict[str, Any],
        input_payload: dict[str, Any] | None = None,
        resolved_input: dict[str, Any] | None = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        run = self.db.query(DMRun).filter(DMRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        nodes = technical_graph.get("nodes", []) if isinstance(technical_graph, dict) else []
        node_map = {
            str(node.get("step_id") or node.get("id") or ""): node
            for node in nodes
            if isinstance(node, dict)
        }
        step_map = {step.step_id: step for step in run.steps}
        user_inputs = self._merge_inputs(input_payload, resolved_input)

        try:
            execution_order = self._topological_sort(nodes)
        except ValueError as exc:
            run.status = "failed"
            run.error_summary = str(exc)
            self.db.commit()
            return self._serialize_result(run, {})

        run.status = "running"
        if resume:
            run.final_output = None
            run.error_summary = None
        self.db.flush()
        governance_service = GovernanceService(db=self.db)

        step_outputs: dict[str, Any] = self._restore_step_outputs(run.steps) if resume else {}
        step_errors: dict[str, Any] = self._restore_step_errors(run.steps) if resume else {}
        first_failure: str | None = None
        first_failure_status: str | None = None

        for step_id in execution_order:
            node = node_map.get(step_id)
            step = step_map.get(step_id)
            if node is None or step is None:
                continue
            if resume and step.status == "succeeded" and step_id in step_outputs:
                continue

            missing_dep = self._find_missing_dependency(step.depends_on or [], step_outputs, step_errors)
            if missing_dep is not None:
                self._mark_step_blocked(
                    step,
                    f"Dependency step {missing_dep} did not produce a successful output",
                )
                step_errors[step_id] = {"type": "dependency_blocked", "dependency": missing_dep}
                first_failure = first_failure or step.error_message
                first_failure_status = first_failure_status or "blocked"
                break

            resolver_output, executor_output = self._execute_single_step(
                step=step,
                node=node,
                user_inputs=user_inputs,
                step_outputs=step_outputs,
            )

            if resolver_output is not None:
                step.resolved_execution_plan_snapshot = resolver_output.resolved_execution_plan
            self.db.flush()
            self._record_step_audit(
                governance_service=governance_service,
                run=run,
                step=step,
                resolver_output=resolver_output,
                executor_output=executor_output,
            )

            if executor_output.execution_status == "succeeded":
                outputs = executor_output.extracted_outputs or {}
                step_outputs[step_id] = outputs
                self._mark_step_succeeded(
                    step=step,
                    input_snapshot={
                        "user_inputs": user_inputs,
                        "upstream_outputs": {
                            dep: step_outputs.get(dep) for dep in (step.depends_on or [])
                        },
                    },
                    output_snapshot={
                        **(executor_output.raw_payload or {}),
                        "extracted_outputs": outputs,
                    },
                )
                continue

            if executor_output.execution_status == "blocked":
                self._mark_step_blocked(
                    step,
                    executor_output.error_info.get("message")
                    if executor_output.error_info
                    else "Step execution blocked",
                )
            else:
                self._mark_step_failed(
                    step,
                    executor_output.error_info.get("message")
                    if executor_output.error_info
                    else "Step execution failed",
                    input_snapshot={
                        "user_inputs": user_inputs,
                        "upstream_outputs": {
                            dep: step_outputs.get(dep) for dep in (step.depends_on or [])
                        },
                    },
                    output_snapshot=executor_output.raw_payload or {},
                )
            step_errors[step_id] = executor_output.error_info or {
                "type": executor_output.execution_status
            }
            first_failure = first_failure or step.error_message
            first_failure_status = first_failure_status or executor_output.execution_status
            break

        if first_failure is None:
            run.status = "succeeded"
            run.final_output = self._choose_final_output(execution_order, node_map, step_outputs)
            run.error_summary = None
        else:
            run.status = "blocked" if first_failure_status == "blocked" else "failed"
            run.error_summary = first_failure

        self.db.commit()
        return self._serialize_result(run, step_outputs)

    def _execute_single_step(
        self,
        step: DMRunStep,
        node: dict[str, Any],
        user_inputs: dict[str, Any],
        step_outputs: dict[str, Any],
    ):
        """执行单个步骤，严格保持 resolver -> executor 顺序。"""

        step.status = "running"
        step.started_at = self._now()
        self.db.flush()

        upstream_outputs = {
            dep: step_outputs.get(dep, {}) for dep in (step.depends_on or []) if dep in step_outputs
        }
        resolver_input = ResolverInput(
            design_intent=node.get("design_intent") or {},
            upstream_outputs=upstream_outputs,
            user_inputs=user_inputs,
            asset_definition=node.get("asset_definition") or {},
            template_context={"step_id": step.step_id, "step_type": step.step_type},
            governance_rules=node.get("governance_rules") or {},
        )

        if step.step_type == "http_step":
            resolver_output = self.http_resolver.resolve(node, resolver_input)
        elif step.step_type == "sql_step":
            resolver_output = self.sql_resolver.resolve(node, resolver_input)
        else:
            resolver_output = None

        if resolver_output is not None and resolver_output.resolution_status != "resolved":
            return resolver_output, ExecutorOutput(
                execution_status="blocked",
                error_info={
                    "message": "; ".join(
                        issue.get("message", "resolver blocked") for issue in resolver_output.blocking_issues
                    ),
                    "type": "resolver_blocked",
                },
            )

        resolved_plan = (
            resolver_output.resolved_execution_plan
            if resolver_output is not None
            else (
                node.get("resolved_execution_plan")
                or {
                    "output_mapping": node.get("output_mapping"),
                    "mapping": node.get("mapping"),
                    "confirmation_required": node.get("confirmation_required"),
                    "auto_confirm": node.get("auto_confirm"),
                }
            )
        )

        execution_input = ExecutorInput(
            resolved_execution_plan=resolved_plan,
            runtime_values={
                "user_inputs": user_inputs,
                "upstream_outputs": upstream_outputs,
                "step_outputs": step_outputs,
            },
        )

        if step.step_type == "http_step":
            executor_output = HTTPExecutor().execute(execution_input)
        elif step.step_type == "sql_step":
            executor_output = SQLExecutor(self.db).execute(execution_input)
        else:
            executor_output = self.control_executor.execute(
                step_type=step.step_type,
                execution_input=execution_input,
                depends_on=step.depends_on or [],
            )

        return resolver_output, executor_output

    def _record_step_audit(
        self,
        governance_service: GovernanceService,
        run: DMRun,
        step: DMRunStep,
        resolver_output,
        executor_output: ExecutorOutput,
    ) -> None:
        """为需要治理追踪的步骤补审计记录。

        当前仅对 SQL 节点落审计，避免在 V1 第一阶段把非治理节点也卷入复杂审计结构。
        """

        if step.step_type != "sql_step":
            return

        resolved_plan = {}
        if resolver_output is not None:
            resolved_plan = resolver_output.resolved_execution_plan or {}
        elif isinstance(step.resolved_execution_plan_snapshot, dict):
            resolved_plan = step.resolved_execution_plan_snapshot

        audit_payload = governance_service.build_sql_audit_payload(
            run=run,
            step=step,
            resolved_plan=resolved_plan,
            execution_status=executor_output.execution_status,
            raw_payload=executor_output.raw_payload,
            extracted_outputs=executor_output.extracted_outputs,
            error_info=executor_output.error_info,
        )
        if executor_output.audit_payload:
            audit_payload.update(executor_output.audit_payload)

        governance_service.record_sql_audit(
            run=run,
            step=step,
            actor_user_id=run.initiator_user_id,
            execution_status=executor_output.execution_status,
            audit_payload=audit_payload,
            error_info=executor_output.error_info,
        )

    def _topological_sort(self, nodes: list[Any]) -> list[str]:
        """按 depends_on 对 technical_graph 做最小拓扑排序。"""

        node_ids = [
            str(node.get("step_id") or node.get("id") or "")
            for node in nodes
            if isinstance(node, dict)
        ]
        incoming = {node_id: 0 for node_id in node_ids}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}

        for node in nodes:
            if not isinstance(node, dict):
                continue
            step_id = str(node.get("step_id") or node.get("id") or "")
            for dep in node.get("depends_on") or []:
                dep_id = str(dep)
                if dep_id not in incoming:
                    continue
                incoming[step_id] += 1
                outgoing.setdefault(dep_id, []).append(step_id)

        queue = [node_id for node_id, count in incoming.items() if count == 0]
        ordered: list[str] = []

        while queue:
            current = queue.pop(0)
            ordered.append(current)
            for target in outgoing.get(current, []):
                incoming[target] -= 1
                if incoming[target] == 0:
                    queue.append(target)

        if len(ordered) != len(node_ids):
            raise ValueError("technical_graph has cyclic dependencies and cannot execute")

        return ordered

    def _find_missing_dependency(
        self,
        depends_on: list[Any],
        step_outputs: dict[str, Any],
        step_errors: dict[str, Any],
    ) -> str | None:
        for dep in depends_on:
            dep_id = str(dep)
            if dep_id in step_errors or dep_id not in step_outputs:
                return dep_id
        return None

    def _mark_step_succeeded(
        self,
        step: DMRunStep,
        input_snapshot: dict[str, Any],
        output_snapshot: dict[str, Any],
    ) -> None:
        step.status = "succeeded"
        step.input_snapshot = input_snapshot
        step.output_snapshot = output_snapshot
        step.error_message = None
        step.finished_at = self._now()

    def _mark_step_failed(
        self,
        step: DMRunStep,
        message: str,
        input_snapshot: dict[str, Any],
        output_snapshot: dict[str, Any],
    ) -> None:
        step.status = "failed"
        step.input_snapshot = input_snapshot
        step.output_snapshot = output_snapshot
        step.error_message = message
        step.finished_at = self._now()

    def _mark_step_blocked(self, step: DMRunStep, message: str) -> None:
        step.status = "blocked"
        step.error_message = message
        step.finished_at = self._now()

    def _merge_inputs(
        self,
        input_payload: dict[str, Any] | None,
        resolved_input: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        if isinstance(input_payload, dict):
            merged.update(input_payload)
        if isinstance(resolved_input, dict):
            merged.update(resolved_input)
        return merged

    def _restore_step_outputs(self, steps: list[DMRunStep]) -> dict[str, Any]:
        """从已成功步骤的输出快照恢复上游结果，供恢复执行使用。"""

        restored: dict[str, Any] = {}
        for step in steps:
            if step.status != "succeeded" or not isinstance(step.output_snapshot, dict):
                continue

            output_snapshot = step.output_snapshot
            extracted = output_snapshot.get("extracted_outputs")
            if isinstance(extracted, dict):
                restored[step.step_id] = extracted
                continue

            legacy_outputs = output_snapshot.get("outputs")
            if isinstance(legacy_outputs, dict):
                restored[step.step_id] = legacy_outputs
                continue

            final_output = output_snapshot.get("final_output")
            if isinstance(final_output, dict):
                restored[step.step_id] = final_output
                continue

            mapped_output = output_snapshot.get("mapped_output")
            if isinstance(mapped_output, dict):
                restored[step.step_id] = mapped_output
                continue

            if output_snapshot:
                restored[step.step_id] = output_snapshot
        return restored

    def _restore_step_errors(self, steps: list[DMRunStep]) -> dict[str, Any]:
        """恢复已失败或仍阻塞步骤的错误状态。"""

        restored: dict[str, Any] = {}
        for step in steps:
            if step.status not in {"failed", "blocked"}:
                continue
            restored[step.step_id] = {
                "type": step.status,
                "message": step.error_message,
            }
        return restored

    def _choose_final_output(
        self,
        execution_order: list[str],
        node_map: dict[str, dict[str, Any]],
        step_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        """优先取 end 节点输出，否则取最后一个成功步骤输出。"""

        for step_id in reversed(execution_order):
            node = node_map.get(step_id) or {}
            if node.get("step_type") == "end" and step_id in step_outputs:
                output = step_outputs[step_id]
                return output if isinstance(output, dict) else {"result": output}

        for step_id in reversed(execution_order):
            if step_id in step_outputs:
                output = step_outputs[step_id]
                return output if isinstance(output, dict) else {"result": output}
        return {}

    def _serialize_result(self, run: DMRun, step_outputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "run_id": run.id,
            "status": run.status,
            "final_output": run.final_output,
            "error_summary": run.error_summary,
            "steps_summary": [
                {
                    "step_id": step.step_id,
                    "status": step.status,
                    "error_message": step.error_message,
                    "has_output": step.step_id in step_outputs,
                }
                for step in run.steps
            ],
        }

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
