"""契约快照哈希——契约漂移检测的公共复算函数。

业务目标：在"选择时刻"记录场景/Source 契约的稳定哈希，执行前重算并比对，
若契约在执行前被修改（如新增必填参数）即可发现漂移，避免用旧契约执行新接口。

设计红线：catalog 适配器与 contract_guard 必须复用本模块的同一函数，
否则两份实现一旦不一致会导致全场景误报漂移。本模块零 runtime 内部依赖（只用 stdlib + pydantic），
不可能与 catalog/guard 形成循环引用。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel


def contract_hash(contract: BaseModel) -> str:
    """对契约快照做稳定哈希：sha256(model_dump JSON, 键序稳定) 取前 16 位。

    `sort_keys=True` 保证同一契约多次解析产生相同哈希（可复算）。
    适用于 AgentSceneContract 与 AgentSourceContract，两者哈希逻辑一致。
    """
    raw = json.dumps(contract.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class DriftCheck:
    """契约漂移检测结果。

    drifted=True 表示执行前重算的 hash 与选定时刻的快照不一致，
    调用方应阻断执行并等用户确认是否按新契约执行。
    """

    drifted: bool
    stored_hash: str | None
    fresh_hash: str


def compare_contract_hash(stored_hash: str | None, fresh_hash: str | None) -> DriftCheck:
    """直接比对两个已算好的契约 hash（runtime 层 candidate.contract_hash 已由 catalog 算好）。

    任一 hash 为空（历史无快照或 catalog 未产出）视为不漂移，避免误报。
    """
    drifted = bool(stored_hash) and bool(fresh_hash) and stored_hash != fresh_hash
    return DriftCheck(drifted=drifted, stored_hash=stored_hash, fresh_hash=fresh_hash or "")

