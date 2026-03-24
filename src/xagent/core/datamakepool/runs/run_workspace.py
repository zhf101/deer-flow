from __future__ import annotations

from typing import Optional

from ...workspace import TaskWorkspace


class RunWorkspace(TaskWorkspace):
    """按 Run 隔离的工作区。

    试跑和正式执行产生的临时文件、输出产物不能继续混在 TaskWorkspace 中，
    否则会污染探索态上下文，也不利于按 run 做审计和归档。
    """

    def __init__(
        self,
        run_id: int,
        base_dir: str = "uploads",
        user_id: Optional[int] = None,
    ):
        # workspace_id 采用 dm_run_{run_id} 形式，避免与探索态 web_task_* 混淆。
        workspace_id = f"dm_run_{run_id}"
        if user_id is not None:
            base_dir = f"{base_dir}/user_{user_id}"
        super().__init__(id=workspace_id, base_dir=base_dir)
        self.run_id = run_id
        self.user_id = user_id
