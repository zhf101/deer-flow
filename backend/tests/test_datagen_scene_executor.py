"""场景执行器边界行为测试。"""

from __future__ import annotations

import pytest

from app.gdp.datagen.config.scene.executor import SceneExecutionError, SceneExecutor
from app.gdp.datagen.config.scene.models import HttpStepDefinition


@pytest.mark.anyio
async def test_http_step_path_type_error_message_distinguishes_resolved_non_string() -> None:
    """HTTP path 表达式解析成非字符串时，应明确提示类型不对。"""

    executor = SceneExecutor(sql_execution_service=object(), base_repository=object())  # type: ignore[arg-type]
    step = HttpStepDefinition(
        stepId="getToken",
        sysCode="account",
        path="${inputs.port}",
    )

    with pytest.raises(SceneExecutionError, match="HTTP step path must resolve to a non-empty string"):
        await executor._execute_http_step(step, "DEV", {"inputs": {"port": 8080}})
