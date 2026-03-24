from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TemplateService:
    """Placeholder service for template revision orchestration."""

    def create_revision_from_run(self, run_id: int) -> dict[str, Any]:
        return {"source_run_id": run_id, "status": "draft"}

    def submit_review(self, revision_id: int) -> dict[str, Any]:
        return {"revision_id": revision_id, "status": "pending_review"}
