from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..preflight import PreflightService


@dataclass
class FlowDraftService:
    """FlowDraft 生命周期服务骨架。

    当前阶段先提供最小方法面，后续逐步接入真实 DB 与版本快照逻辑。
    """

    preflight_service: Optional[PreflightService] = None

    def get_flowdraft(self, flowdraft_id: int) -> dict[str, Any]:
        """读取单个 FlowDraft。

        当前返回骨架结构，后续替换为真实 repository 查询。
        """
        return {"id": flowdraft_id}

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
