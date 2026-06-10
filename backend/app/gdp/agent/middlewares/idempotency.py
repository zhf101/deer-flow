"""GDP Agent 副作用幂等判定工具。"""

from __future__ import annotations

import json
from typing import Any

from app.gdp.datagen.config.task.models import (
    DatagenTaskStepResponse,
    DatagenTaskStepStatus,
    DatagenTaskStepType,
)


def find_successful_scene_run_step(
    steps: list[DatagenTaskStepResponse],
    *,
    scene_code: str,
    env_code: str,
    input_params: dict[str, Any],
) -> DatagenTaskStepResponse | None:
    """查找同一任务内已成功执行过的同参场景步骤。"""

    for step in steps:
        if step.stepType != DatagenTaskStepType.RUN_SCENE or step.status != DatagenTaskStepStatus.SUCCESS:
            continue
        selected_resource = step.selectedResource or {}
        if selected_resource.get("sceneCode") != scene_code:
            continue
        if selected_resource.get("envCode") != env_code:
            continue
        if _stable_json(step.inputBinding or {}) != _stable_json(input_params):
            continue
        return step
    return None


def find_successful_scene_publish_step(
    steps: list[DatagenTaskStepResponse],
    *,
    source_code: str,
) -> DatagenTaskStepResponse | None:
    """查找同一任务内已成功基于同一 Source 发布过的场景步骤。"""

    for step in steps:
        if step.stepType != DatagenTaskStepType.DESIGN_SCENE or step.status != DatagenTaskStepStatus.SUCCESS:
            continue
        selected_resource = step.selectedResource or {}
        source = selected_resource.get("source") if isinstance(selected_resource, dict) else None
        if not isinstance(source, dict):
            continue
        if source.get("sourceCode") == source_code:
            return step
    return None


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
