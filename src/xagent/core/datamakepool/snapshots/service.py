from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SnapshotService:
    """Placeholder service for flowdraft snapshots and diffs."""

    def create_snapshot(self, flowdraft_id: int, snapshot_type: str) -> dict[str, Any]:
        return {"flowdraft_id": flowdraft_id, "snapshot_type": snapshot_type}

    def diff(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        return {"before": before, "after": after}
