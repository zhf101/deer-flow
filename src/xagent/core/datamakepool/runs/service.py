from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..orchestration import RunRuntimeBridge


@dataclass
class RunService:
    """Placeholder service for creating and orchestrating runs."""

    runtime_bridge: RunRuntimeBridge

    def create_run(
        self,
        entry_type: str,
        initiator_user_id: int,
        task_id: Optional[int] = None,
        system_short: Optional[str] = None,
    ) -> dict[str, Any]:
        return {
            "entry_type": entry_type,
            "initiator_user_id": initiator_user_id,
            "task_id": task_id,
            "system_short": system_short,
            "runtime": self.runtime_bridge.build_context(
                run_id=0, task_id=task_id, link_type=entry_type
            ),
        }
