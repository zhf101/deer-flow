from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RunRuntimeContext:
    task_id: Optional[int]
    run_id: int
    link_type: str = "trial"
    workspace_id: Optional[str] = None
    runtime_metadata: Optional[dict[str, Any]] = None


class RunRuntimeBridge:
    """Bridges task-centric runtime facilities to run-centric business execution."""

    def build_context(
        self,
        run_id: int,
        task_id: Optional[int] = None,
        link_type: str = "trial",
        workspace_id: Optional[str] = None,
        runtime_metadata: Optional[dict[str, Any]] = None,
    ) -> RunRuntimeContext:
        return RunRuntimeContext(
            task_id=task_id,
            run_id=run_id,
            link_type=link_type,
            workspace_id=workspace_id,
            runtime_metadata=runtime_metadata or {},
        )

    def event_payload(
        self, context: RunRuntimeContext, payload: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        base = {
            "task_id": context.task_id,
            "run_id": context.run_id,
            "link_type": context.link_type,
            "workspace_id": context.workspace_id,
        }
        if context.runtime_metadata:
            base["runtime_metadata"] = context.runtime_metadata
        if payload:
            base.update(payload)
        return base
