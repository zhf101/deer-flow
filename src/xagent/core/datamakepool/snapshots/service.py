from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from xagent.web.models.dm_flow_draft import DMFlowDraft, DMFlowDraftSnapshot


ALLOWED_SNAPSHOT_TYPES = {
    "initial_draft",
    "manual_edit",
    "re_resolved",
    "pre_trial",
    "trial_success",
    "trial_failed",
}


@dataclass
class SnapshotService:
    """FlowDraft 快照与 diff 服务。

    当前只实现 V1 进入编辑闭环所需的最小能力：

    - 基于当前 FlowDraft 生成快照
    - 查询某个 FlowDraft 的快照列表
    - 计算 snapshot 与 snapshot / current 之间的结构差异
    """

    db: Session

    def create_snapshot(
        self,
        flowdraft: DMFlowDraft,
        snapshot_type: str,
        created_by: int,
    ) -> dict[str, Any]:
        """为当前 FlowDraft 状态创建一条关键快照。"""

        if snapshot_type not in ALLOWED_SNAPSHOT_TYPES:
            raise ValueError(f"Unsupported flowdraft snapshot type {snapshot_type!r}")

        snapshot = DMFlowDraftSnapshot(
            flow_draft_id=flowdraft.id,
            snapshot_type=snapshot_type,
            business_graph_snapshot=flowdraft.business_graph_payload or {},
            technical_graph_snapshot=flowdraft.technical_graph_payload or {},
            preflight_summary_snapshot=flowdraft.preflight_summary_payload,
            created_by=created_by,
        )
        self.db.add(snapshot)
        self.db.flush()

        flowdraft.latest_snapshot_id = snapshot.id
        self.db.flush()
        return self._serialize_snapshot(snapshot)

    def list_snapshots(self, flowdraft: DMFlowDraft) -> list[dict[str, Any]]:
        """列出指定 FlowDraft 的全部快照。"""

        snapshots = (
            self.db.query(DMFlowDraftSnapshot)
            .filter(DMFlowDraftSnapshot.flow_draft_id == flowdraft.id)
            .order_by(DMFlowDraftSnapshot.created_at.desc(), DMFlowDraftSnapshot.id.desc())
            .all()
        )
        return [self._serialize_snapshot(snapshot) for snapshot in snapshots]

    def get_snapshot(
        self,
        flowdraft_id: int,
        snapshot_id: int,
    ) -> DMFlowDraftSnapshot:
        """读取指定快照，并校验归属。"""

        snapshot = (
            self.db.query(DMFlowDraftSnapshot)
            .filter(
                DMFlowDraftSnapshot.id == snapshot_id,
                DMFlowDraftSnapshot.flow_draft_id == flowdraft_id,
            )
            .first()
        )
        if snapshot is None:
            raise ValueError(
                f"Snapshot {snapshot_id} not found for flowdraft {flowdraft_id}"
            )
        return snapshot

    def diff(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        """计算两个结构之间的最小 diff。"""

        changed_paths: list[str] = []
        self._collect_diff(before, after, path="$", changed_paths=changed_paths)
        changed_step_ids = self._collect_changed_step_ids(before, after)
        return {
            "changed": bool(changed_paths),
            "changed_count": len(changed_paths),
            "changed_paths": changed_paths,
            "changed_step_ids": changed_step_ids,
        }

    def _collect_diff(
        self,
        before: Any,
        after: Any,
        path: str,
        changed_paths: list[str],
    ) -> None:
        """递归收集差异路径。

        这里不尝试做复杂的结构编辑脚本，只输出“哪里发生变化”，
        先满足前台和排障对最小 diff 的需要。
        """

        if type(before) is not type(after):
            changed_paths.append(path)
            return

        if isinstance(before, dict):
            before_keys = set(before.keys())
            after_keys = set(after.keys())
            for key in sorted(before_keys | after_keys):
                next_path = f"{path}.{key}"
                if key not in before or key not in after:
                    changed_paths.append(next_path)
                    continue
                self._collect_diff(before[key], after[key], next_path, changed_paths)
            return

        if isinstance(before, list):
            if len(before) != len(after):
                changed_paths.append(path)
            for index, (before_item, after_item) in enumerate(zip(before, after)):
                self._collect_diff(
                    before_item,
                    after_item,
                    path=f"{path}[{index}]",
                    changed_paths=changed_paths,
                )
            return

        if before != after:
            changed_paths.append(path)

    def _serialize_snapshot(self, snapshot: DMFlowDraftSnapshot) -> dict[str, Any]:
        """将快照对象压平成 API 结构。"""

        return {
            "snapshot_id": snapshot.id,
            "flowdraft_id": snapshot.flow_draft_id,
            "snapshot_type": snapshot.snapshot_type,
            "created_by": snapshot.created_by,
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        }

    def _collect_changed_step_ids(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> list[str]:
        """针对技术图输出受影响步骤列表。"""

        if not isinstance(before, dict) or not isinstance(after, dict):
            return []
        if "nodes" not in before and "nodes" not in after:
            return []

        before_nodes = before.get("nodes", []) if isinstance(before.get("nodes", []), list) else []
        after_nodes = after.get("nodes", []) if isinstance(after.get("nodes", []), list) else []

        before_map = {
            str(node.get("step_id") or node.get("id") or ""): node
            for node in before_nodes
            if isinstance(node, dict)
        }
        after_map = {
            str(node.get("step_id") or node.get("id") or ""): node
            for node in after_nodes
            if isinstance(node, dict)
        }

        changed: list[str] = []
        for step_id in sorted(set(before_map.keys()) | set(after_map.keys())):
            if before_map.get(step_id) != after_map.get(step_id):
                changed.append(step_id)
        return changed
