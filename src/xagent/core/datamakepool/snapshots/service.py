from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SnapshotService:
    """快照与 diff 服务骨架。

    后续会承接：
    - FlowDraft 关键版本快照生成
    - business_graph / technical_graph 的结构化 diff
    """

    def create_snapshot(self, flowdraft_id: int, snapshot_type: str) -> dict[str, Any]:
        """创建快照的占位实现。"""
        return {"flowdraft_id": flowdraft_id, "snapshot_type": snapshot_type}

    def diff(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        """diff 计算的占位实现。"""
        return {"before": before, "after": after}
