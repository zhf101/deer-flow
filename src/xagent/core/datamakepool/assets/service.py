from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AssetService:
    """Placeholder service for asset lookup and mutation."""

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        return {"asset_id": asset_id}

    def list_assets(self, system_short: str | None = None) -> dict[str, Any]:
        return {"system_short": system_short, "items": []}
