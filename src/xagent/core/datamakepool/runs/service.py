from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from xagent.web.models.dm_run import DMRun, DMRunStep
from xagent.web.models.dm_runtime_link import DMTaskRunLink

from ..orchestration import RunRuntimeBridge


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
