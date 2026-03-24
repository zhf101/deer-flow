from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..preflight import PreflightService


@dataclass
class FlowDraftService:
    """Placeholder service for FlowDraft lifecycle orchestration."""

    preflight_service: Optional[PreflightService] = None

    def get_flowdraft(self, flowdraft_id: int) -> dict[str, Any]:
        return {"id": flowdraft_id}

    def mark_needs_resolution(
        self, flowdraft_id: int, step_id: Optional[str] = None
    ) -> dict[str, Any]:
        return {
            "flowdraft_id": flowdraft_id,
            "step_id": step_id,
            "status": "needs_resolution",
        }

    def evaluate_preflight(self, technical_graph: dict[str, Any]) -> dict[str, Any]:
        service = self.preflight_service or PreflightService()
        return service.evaluate(technical_graph).model_dump()
