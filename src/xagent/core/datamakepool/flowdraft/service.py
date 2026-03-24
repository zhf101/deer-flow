from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from xagent.web.models.dm_flow_draft import DMFlowDraft

from ..preflight import PreflightService


@dataclass
class FlowDraftService:
    """FlowDraft 生命周期服务骨架。

    当前阶段先提供最小方法面，后续逐步接入真实 DB 与版本快照逻辑。
    """

    db: Session
    preflight_service: Optional[PreflightService] = None

    def get_flowdraft(self, flowdraft_id: int) -> dict[str, Any]:
        """读取单个 FlowDraft。

        当前返回骨架结构，后续替换为真实 repository 查询。
        """
        flowdraft = self.db.query(DMFlowDraft).filter(DMFlowDraft.id == flowdraft_id).first()
        if flowdraft is None:
            raise ValueError(f"FlowDraft {flowdraft_id} not found")

        return self._serialize_flowdraft(flowdraft)

    def mark_needs_resolution(
        self, flowdraft_id: int, step_id: Optional[str] = None
    ) -> dict[str, Any]:
        """将整个草稿或某个步骤标记为 needs_resolution。

        这个状态用于前台提示：用户改动已经触发重新收敛，不能直接试跑。
        """
        return {
            "flowdraft_id": flowdraft_id,
            "step_id": step_id,
            "status": "needs_resolution",
        }

    def evaluate_preflight(self, technical_graph: dict[str, Any]) -> dict[str, Any]:
        """对 technical_graph 执行预检。

        这里先把预检能力挂进 FlowDraftService，后续再决定是否拆成更完整的 orchestration 流程。
        """
        service = self.preflight_service or PreflightService()
        return service.evaluate(technical_graph).model_dump()

    def get_preflight(self, flowdraft_id: int) -> dict[str, Any]:
        """读取指定 FlowDraft 的预检结果。

        当前如果数据库里还没有缓存的 preflight_summary，就现场执行一次最小预检。
        """
        flowdraft = self.db.query(DMFlowDraft).filter(DMFlowDraft.id == flowdraft_id).first()
        if flowdraft is None:
            raise ValueError(f"FlowDraft {flowdraft_id} not found")

        if flowdraft.preflight_summary_payload:
            return flowdraft.preflight_summary_payload
        return self.evaluate_preflight(flowdraft.technical_graph_payload or {})

    def _serialize_flowdraft(self, flowdraft: DMFlowDraft) -> dict[str, Any]:
        """把 ORM 对象压平成 API 可直接返回的结构。"""
        return {
            "id": flowdraft.id,
            "task_id": flowdraft.task_id,
            "status": flowdraft.status,
            "title": flowdraft.title,
            "objective": flowdraft.objective,
            "business_graph": flowdraft.business_graph_payload or {},
            "technical_graph": flowdraft.technical_graph_payload or {},
            "pending_issues": flowdraft.pending_issues_payload or [],
            "preflight_summary": flowdraft.preflight_summary_payload,
            "input_schema_draft": flowdraft.input_schema_draft,
            "output_mapping_draft": flowdraft.output_mapping_draft,
            "latest_snapshot_id": flowdraft.latest_snapshot_id,
        }
