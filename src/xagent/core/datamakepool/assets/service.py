from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AssetService:
    """资产服务骨架。

    当前阶段先保留最小读接口形状，后续再分别接 HTTP 资产与 SQL 资产的真实查询和写入逻辑。
    """

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        """读取单个资产的占位实现。"""
        return {"asset_id": asset_id}

    def list_assets(self, system_short: str | None = None) -> dict[str, Any]:
        """按 systemShort 过滤资产列表的占位实现。"""
        return {"system_short": system_short, "items": []}
