from __future__ import annotations

from typing import Optional

from ...workspace import TaskWorkspace


class RunWorkspace(TaskWorkspace):
    """Workspace isolated per run for trial and formal execution artifacts."""

    def __init__(
        self,
        run_id: int,
        base_dir: str = "uploads",
        user_id: Optional[int] = None,
    ):
        workspace_id = f"dm_run_{run_id}"
        if user_id is not None:
            base_dir = f"{base_dir}/user_{user_id}"
        super().__init__(id=workspace_id, base_dir=base_dir)
        self.run_id = run_id
        self.user_id = user_id
