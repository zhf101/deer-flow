from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RunRuntimeContext:
    """运行时桥接上下文。

    它把 task-centric 的探索态运行信息包装成 run-centric 的执行态上下文，
    供后续消息、产物和聚合视图统一消费。
    """

    task_id: Optional[int]
    run_id: int
    link_type: str = "trial"
    workspace_id: Optional[str] = None
    runtime_metadata: Optional[dict[str, Any]] = None


class RunRuntimeBridge:
    """连接探索态 runtime 与执行态 Run 的桥接层。"""

    def build_context(
        self,
        run_id: int,
        task_id: Optional[int] = None,
        link_type: str = "trial",
        workspace_id: Optional[str] = None,
        runtime_metadata: Optional[dict[str, Any]] = None,
    ) -> RunRuntimeContext:
        """构建一份可跨层传递的运行上下文。

        这里先保持极简，只做映射封装，不做数据库写入。
        后续真实实现时再把 task/run link、workspace、trace 聚合都接进来。
        """
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
        """把桥接上下文展开为统一事件载荷。

        这样 V1 就能在继续沿用 task 通道的同时，把 run_id 一并带给上层消费。
        """
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
