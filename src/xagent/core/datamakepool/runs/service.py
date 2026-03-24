from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from xagent.web.models.dm_run import DMRun, DMRunStep
from xagent.web.models.dm_runtime_link import DMTaskRunLink
from xagent.web.models.dm_template import DMTemplateRevision

from ..orchestration import RunRuntimeBridge, TrialOrchestrator


@dataclass
class RunService:
    """Run 服务骨架。

    这个服务负责把设计态真正落成执行态。

    当前第一版先完成：
    - Run 落库
    - Task / Run 桥接关系落库
    - 基于 technical_graph 生成初始 RunStep
    """

    db: Session
    runtime_bridge: RunRuntimeBridge

    def create_run(
        self,
        entry_type: str,
        initiator_user_id: int,
        task_id: Optional[int] = None,
        template_id: Optional[str] = None,
        template_revision_id: Optional[str] = None,
        system_short: Optional[str] = None,
        objective: Optional[str] = None,
        input_payload: Optional[dict[str, Any]] = None,
        resolved_input: Optional[dict[str, Any]] = None,
        technical_graph: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """创建并初始化一条执行态 Run。

        这里默认在服务内部完成一次事务提交，目的是先把执行态最小闭环跑通：
        - 建立 Run
        - 建立 Task / Run 桥接关系
        - 建立初始 RunStep
        """
        try:
            run = DMRun(
                entry_type=entry_type,
                source_task_id=task_id,
                template_id=template_id,
                template_revision_id=template_revision_id,
                initiator_user_id=initiator_user_id,
                system_short=system_short,
                objective=objective,
                input_payload=input_payload,
                resolved_input=resolved_input,
                status="pending",
            )
            self.db.add(run)
            self.db.flush()

            if task_id is not None:
                link = DMTaskRunLink(task_id=task_id, run_id=run.id, link_type=entry_type)
                self.db.add(link)

            created_steps = self._create_run_steps(run.id, technical_graph or {})
            runtime_context = self.runtime_bridge.build_context(
                run_id=run.id,
                task_id=task_id,
                link_type=entry_type,
                workspace_id=f"dm_run_{run.id}",
            )

            self.db.commit()

            return {
                "run_id": run.id,
                "entry_type": run.entry_type,
                "status": run.status,
                "created_steps": created_steps,
                "runtime": self.runtime_bridge.event_payload(runtime_context),
            }
        except Exception:
            self.db.rollback()
            raise

    def get_run(self, run_id: int) -> dict[str, Any]:
        """读取单个 Run 详情。"""
        run = self.db.query(DMRun).filter(DMRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        return self._serialize_run(run)

    def get_run_steps(self, run_id: int) -> list[dict[str, Any]]:
        """读取某个 Run 的步骤列表。"""
        run = self.db.query(DMRun).filter(DMRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Run {run_id} not found")
        return [self._serialize_step(step) for step in run.steps]

    def create_run_from_template(
        self,
        template_revision_id: int,
        initiator_user_id: int,
        system_short: Optional[str] = None,
        input_payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """基于模板版本创建正式执行 Run。"""
        revision = (
            self.db.query(DMTemplateRevision)
            .filter(DMTemplateRevision.id == template_revision_id)
            .first()
        )
        if revision is None:
            raise ValueError(f"Template revision {template_revision_id} not found")

        if revision.status != "published":
            raise ValueError(
                f"Template revision {template_revision_id} is not published and cannot execute"
            )

        return self.create_run(
            entry_type="template",
            initiator_user_id=initiator_user_id,
            task_id=None,
            template_id=str(revision.template_id),
            template_revision_id=str(revision.id),
            system_short=system_short or revision.template.system_short,
            objective=revision.template.description or revision.template.name,
            input_payload=input_payload,
            resolved_input=input_payload,
            technical_graph=revision.technical_graph or {},
        )

    def execute_trial(
        self,
        run_id: int,
        technical_graph: dict[str, Any],
        input_payload: Optional[dict[str, Any]] = None,
        resolved_input: Optional[dict[str, Any]] = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        """执行一条已创建的 trial Run。"""

        orchestrator = TrialOrchestrator(db=self.db)
        return orchestrator.execute_run(
            run_id=run_id,
            technical_graph=technical_graph,
            input_payload=input_payload,
            resolved_input=resolved_input,
            resume=resume,
        )

    def resume_run(self, run_id: int) -> dict[str, Any]:
        """恢复一条被治理确认后可继续执行的 Run。

        当前恢复策略遵循最小闭环原则：
        - 不重新走 FlowDraft
        - 直接基于 RunStep 快照重建最小 technical_graph
        - 保留已成功步骤输出，只继续执行 pending 步骤
        """

        run = self.db.query(DMRun).filter(DMRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        technical_graph = self._rebuild_technical_graph_from_run(run)
        return self.execute_trial(
            run_id=run.id,
            technical_graph=technical_graph,
            input_payload=run.input_payload if isinstance(run.input_payload, dict) else None,
            resolved_input=run.resolved_input if isinstance(run.resolved_input, dict) else None,
            resume=True,
        )

    def _create_run_steps(
        self, run_id: int, technical_graph: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """根据 technical_graph 生成初始 RunStep 记录。

        这里的目标不是执行步骤，而是把“准备怎么执行”投影成执行态骨架，
        让运行详情页和后续 trial / execute 流程有稳定落点。
        """
        created: list[dict[str, Any]] = []
        nodes = technical_graph.get("nodes", []) if isinstance(technical_graph, dict) else []

        for node in nodes:
            if not isinstance(node, dict):
                continue

            step = DMRunStep(
                run_id=run_id,
                step_id=str(node.get("step_id") or node.get("id") or ""),
                step_type=str(node.get("step_type") or ""),
                step_name=str(node.get("name") or node.get("step_name") or "Unnamed Step"),
                status="pending",
                depends_on=node.get("depends_on") or [],
                resolved_execution_plan_snapshot=node.get("resolved_execution_plan"),
                asset_version_snapshot_ref=node.get("asset_version_snapshot_ref"),
            )
            self.db.add(step)
            created.append(
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "step_name": step.step_name,
                }
            )

        return created

    def _rebuild_technical_graph_from_run(self, run: DMRun) -> dict[str, Any]:
        """从 RunStep 快照重建最小 technical_graph。

        恢复执行时不再依赖 FlowDraft 或 Template 的原始设计稿，
        只依赖本次 Run 已经固化下来的执行快照，保证恢复链路可追溯、可重复。
        """

        nodes: list[dict[str, Any]] = []
        for step in run.steps:
            nodes.append(
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "name": step.step_name,
                    "depends_on": step.depends_on or [],
                    "resolved_execution_plan": step.resolved_execution_plan_snapshot or {},
                }
            )
        return {"nodes": nodes}

    def _serialize_run(self, run: DMRun) -> dict[str, Any]:
        """将 Run ORM 对象压平成 API 结构。"""
        return {
            "run_id": run.id,
            "entry_type": run.entry_type,
            "source_task_id": run.source_task_id,
            "template_id": run.template_id,
            "template_revision_id": run.template_revision_id,
            "initiator_user_id": run.initiator_user_id,
            "system_short": run.system_short,
            "objective": run.objective,
            "input_payload": run.input_payload,
            "resolved_input": run.resolved_input,
            "status": run.status,
            "final_output": run.final_output,
            "error_summary": run.error_summary,
            "steps_count": len(run.steps),
        }

    def _serialize_step(self, step: DMRunStep) -> dict[str, Any]:
        """将 RunStep ORM 对象压平成 API 结构。"""
        return {
            "id": step.id,
            "run_id": step.run_id,
            "step_id": step.step_id,
            "step_type": step.step_type,
            "step_name": step.step_name,
            "status": step.status,
            "depends_on": step.depends_on or [],
            "resolved_execution_plan_snapshot": step.resolved_execution_plan_snapshot,
            "asset_version_snapshot_ref": step.asset_version_snapshot_ref,
            "input_snapshot": step.input_snapshot,
            "output_snapshot": step.output_snapshot,
            "error_message": step.error_message,
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "finished_at": step.finished_at.isoformat() if step.finished_at else None,
        }
