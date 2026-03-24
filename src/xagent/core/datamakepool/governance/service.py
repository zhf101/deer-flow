from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..preflight import PreflightService


@dataclass
class GovernanceService:
    """治理服务骨架。

    V1 先把预检和审计载荷输出统一放在这里，后续再逐步接入 SQL 风险规则、确认流和审计落库。
    """

    def preflight_check(self, technical_graph: dict[str, Any]) -> dict[str, Any]:
        """执行面向治理视角的预检。

        当前直接复用 PreflightService，后续会扩展为包含 SQL lane / risk / confirmation 的规则集。
        """
        return PreflightService().evaluate(technical_graph).model_dump()

    def create_audit_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """为审计中心预留统一载荷出口。"""
        return payload
