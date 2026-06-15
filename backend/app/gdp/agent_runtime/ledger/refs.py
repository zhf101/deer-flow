"""运行时账本引用生成工具。"""

from __future__ import annotations

_PENDING_START_REF_PREFIX = "ref:agent-runtime/pending-start"


def pending_start_ref(task_run_id: str) -> str:
    """返回待补充启动请求的固定存储引用。"""

    return f"{_PENDING_START_REF_PREFIX}/{task_run_id}"
