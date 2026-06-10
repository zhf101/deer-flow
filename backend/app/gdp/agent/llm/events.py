"""GDP Agent 模型决策审计事件辅助。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def llm_decision_payload(decision: BaseModel, *, source: str = "llm") -> dict[str, Any]:
    """生成可落 DatagenTaskEvent 的轻量模型决策摘要。"""

    payload = decision.model_dump(mode="json")
    payload["decisionSource"] = source
    return payload


def llm_failure_payload(error: Exception) -> dict[str, Any]:
    """生成模型决策失败的审计摘要。"""

    return {
        "decisionSource": "fallback_rule",
        "errorType": type(error).__name__,
        "errorMessage": str(error)[:512],
    }
