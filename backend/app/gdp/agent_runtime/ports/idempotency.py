"""幂等检查端口。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

IdempotencyGate = Callable[[str, str, str], Awaitable[bool]]
"""幂等冲突检查函数。

参数依次为 task_run_id、action_id、idempotency_key。
返回 True 表示同一幂等键已经由其他动作发起过写请求。
"""

