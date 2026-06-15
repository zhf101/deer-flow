"""执行层通用 ID 和时间工具。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def now() -> datetime:
    """返回当前 UTC 时间。"""

    return datetime.now(UTC)


def gen_id(prefix: str) -> str:
    """生成运行时账本 ID。"""

    return f"{prefix}-{uuid.uuid4().hex[:12]}"
