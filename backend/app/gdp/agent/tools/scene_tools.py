"""GDP Task Agent 场景能力工具。"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool

from app.gdp.datagen.agent_catalog.models import AgentSceneSearchRequest
from app.gdp.datagen.agent_catalog.service import AgentCatalogService
from app.gdp.datagen.config.scene.models import SceneRunRequest
from app.gdp.datagen.config.scene.service import SceneService
from app.gdp.datagen.config.task.models import DatagenTaskPhase, DatagenTaskStepStatus
from app.gdp.datagen.config.task.service import DatagenTaskService


async def search_scene_contracts(
    catalog_service: AgentCatalogService,
    *,
    goal: str,
    env_code: str | None = None,
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """搜索已发布场景能力契约。"""

    result = await catalog_service.search_scene_contracts(
        AgentSceneSearchRequest(
            goal=goal,
            envCode=env_code,
            userInputs=user_inputs or {},
            visibleVariables=visible_variables or [],
            limit=limit,
        )
    )
    return result.model_dump(mode="json")


async def get_scene_contract(catalog_service: AgentCatalogService, scene_code: str) -> dict[str, Any]:
    """读取单个已发布场景能力契约。"""

    contract = await catalog_service.get_scene_contract(scene_code)
    return contract.model_dump(mode="json")


async def bind_scene_inputs(
    catalog_service: AgentCatalogService,
    *,
    scene_code: str,
    user_inputs: dict[str, Any] | None = None,
    visible_variables: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """按场景入参语义绑定用户输入和变量栈。"""

    contract = await catalog_service.get_scene_contract(scene_code)
    user_inputs = user_inputs or {}
    visible_variables = visible_variables or []
    bindings: dict[str, Any] = {}
    missing: list[str] = []
    sources: dict[str, str] = {}
    for field in contract.inputSchema:
        if field.name == "env":
            continue
        value, source = _resolve_input_value(field.name, field.semanticType, field.aliases, user_inputs, visible_variables)
        if value is None and field.required:
            missing.append(field.name)
            continue
        if value is not None:
            bindings[field.name] = value
            sources[field.name] = source
    return {
        "sceneCode": scene_code,
        "bindings": bindings,
        "sources": sources,
        "missingInputs": missing,
        "confidence": 1.0 if not missing else 0.5,
    }


async def run_datagen_scene_for_task(
    task_service: DatagenTaskService,
    scene_service: SceneService,
    *,
    task_run_id: str,
    scene_code: str,
    env_code: str,
    input_params: dict[str, Any],
    goal: str | None = None,
) -> dict[str, Any]:
    """执行已发布场景并记录任务历史。"""

    steps = await task_service.list_steps(task_run_id)
    await task_service.record_event(
        task_run_id,
        event_type="SCENE_RUN_STARTED",
        phase=DatagenTaskPhase.SCENE_EXECUTING,
        message=f"开始执行场景 {scene_code}。",
        payload={"sceneCode": scene_code, "envCode": env_code, "inputs": input_params},
    )
    result = await scene_service.run_scene(
        SceneRunRequest(sceneCode=scene_code, envCode=env_code, inputs=input_params)
    )
    success = result.status == "SUCCESS"
    step = await task_service.record_scene_step(
        task_run_id,
        step_no=len(steps) + 1,
        goal=goal or f"执行场景 {scene_code}",
        selected_resource={"sceneCode": scene_code, "versionNo": result.versionNo},
        input_binding=input_params,
        output=result.finalOutput,
        scene_run_id=result.runId,
        status=DatagenTaskStepStatus.SUCCESS if success else DatagenTaskStepStatus.FAILED,
    )
    await task_service.record_event(
        task_run_id,
        event_type="SCENE_RUN_FINISHED",
        phase=DatagenTaskPhase.SCENE_EXECUTING,
        message=f"场景 {scene_code} 执行完成，状态 {result.status}。",
        payload={
            "sceneCode": scene_code,
            "sceneRunId": result.runId,
            "status": result.status,
            "errors": result.errors,
            "finalOutput": result.finalOutput,
        },
    )
    if success:
        await task_service.append_visible_variables_from_scene_result(
            task_run_id,
            scene_code=scene_code,
            scene_run_id=result.runId,
            final_output=result.finalOutput,
        )
    else:
        await task_service.fail_task(
            task_run_id,
            failure_type="SCENE_BUSINESS_ERROR",
            failure_message="场景执行失败或部分成功，造数任务已终止。",
        )
    return {
        "success": success,
        "taskStepId": step.taskStepId,
        "sceneRunId": result.runId,
        "sceneStatus": result.status,
        "finalOutput": result.finalOutput,
        "errors": result.errors,
    }


async def reflect_scene_result(
    *,
    goal: str,
    scene_result: dict[str, Any],
) -> dict[str, Any]:
    """根据场景结果给出下一步建议。"""

    if scene_result.get("success") and _goal_requires_paid_state(goal) and not _output_has_paid_state(scene_result.get("finalOutput")):
        return {
            "completed": False,
            "nextAction": "SEARCH_NEXT_SCENE",
            "reason": "当前输出还没有支付完成状态，需要继续寻找可消费现有变量的后续场景。",
            "goal": goal,
        }
    if scene_result.get("success"):
        return {
            "completed": True,
            "nextAction": "FINISH_OR_VERIFY",
            "reason": "场景执行成功，已获得最终输出。",
            "goal": goal,
        }
    return {
        "completed": False,
        "nextAction": "FAIL_TASK",
        "reason": "场景执行失败，按照任务规则终止整个造数任务。",
        "goal": goal,
    }


def _goal_requires_paid_state(goal: str) -> bool:
    normalized = goal.lower()
    return any(word in normalized for word in ("已支付", "支付", "付款", "paid", "payment", "pay"))


def _output_has_paid_state(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_output_has_paid_state(item) for item in value.values())
    if isinstance(value, list):
        return any(_output_has_paid_state(item) for item in value)
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"paid", "payed", "payment_success", "pay_success", "success", "已支付", "支付成功"}


def build_scene_tools(
    *,
    catalog_service: AgentCatalogService,
    task_service: DatagenTaskService,
    scene_service: SceneService,
) -> list[StructuredTool]:
    """构造场景阶段 LangChain 工具。"""

    async def _search_scene_contracts(
        goal: str,
        env_code: str | None = None,
        user_inputs: dict[str, Any] | None = None,
        visible_variables: list[dict[str, Any]] | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """搜索已发布场景能力契约。"""

        return await search_scene_contracts(
            catalog_service,
            goal=goal,
            env_code=env_code,
            user_inputs=user_inputs,
            visible_variables=visible_variables,
            limit=limit,
        )

    async def _get_scene_contract(scene_code: str) -> dict[str, Any]:
        """读取单个已发布场景能力契约。"""

        return await get_scene_contract(catalog_service, scene_code)

    async def _bind_scene_inputs(
        scene_code: str,
        user_inputs: dict[str, Any] | None = None,
        visible_variables: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """按场景入参语义绑定用户输入和变量栈。"""

        return await bind_scene_inputs(
            catalog_service,
            scene_code=scene_code,
            user_inputs=user_inputs,
            visible_variables=visible_variables,
        )

    async def _run_datagen_scene_for_task(
        task_run_id: str,
        scene_code: str,
        env_code: str,
        input_params: dict[str, Any],
        goal: str | None = None,
    ) -> dict[str, Any]:
        """执行已发布场景并记录任务历史。"""

        return await run_datagen_scene_for_task(
            task_service,
            scene_service,
            task_run_id=task_run_id,
            scene_code=scene_code,
            env_code=env_code,
            input_params=input_params,
            goal=goal,
        )

    async def _reflect_scene_result(goal: str, scene_result: dict[str, Any]) -> dict[str, Any]:
        """根据场景执行结果判断下一步。"""

        return await reflect_scene_result(goal=goal, scene_result=scene_result)

    return [
        StructuredTool.from_function(
            coroutine=_search_scene_contracts,
            name="search_scene_contracts",
            description="搜索已发布造数场景能力契约，返回候选、评分、理由、缺失入参和是否需要确认。",
        ),
        StructuredTool.from_function(
            coroutine=_get_scene_contract,
            name="get_scene_contract",
            description="读取单个已发布造数场景的能力契约。",
        ),
        StructuredTool.from_function(
            coroutine=_bind_scene_inputs,
            name="bind_scene_inputs",
            description="根据场景入参定义、用户输入和变量栈生成入参绑定。",
        ),
        StructuredTool.from_function(
            coroutine=_run_datagen_scene_for_task,
            name="run_datagen_scene_for_task",
            description="执行已发布场景，并把场景运行详情记录到造数任务历史。",
        ),
        StructuredTool.from_function(
            coroutine=_reflect_scene_result,
            name="reflect_scene_result",
            description="根据场景执行结果判断任务是否可完成或应终止。",
        ),
    ]


def _resolve_input_value(
    name: str,
    semantic_type: str | None,
    aliases: list[str],
    user_inputs: dict[str, Any],
    visible_variables: list[dict[str, Any]],
) -> tuple[Any | None, str]:
    keys = [name, semantic_type or "", *aliases]
    lowered_inputs = {str(key).lower(): value for key, value in user_inputs.items()}
    for key in keys:
        if key and key.lower() in lowered_inputs:
            return lowered_inputs[key.lower()], f"input.{key}"
    for variable in visible_variables:
        for key in keys:
            if not key:
                continue
            matched = key.lower() in {
                str(variable.get("name") or "").lower(),
                str(variable.get("semanticType") or "").lower(),
                str(variable.get("label") or "").lower(),
            }
            if matched:
                return variable.get("valuePreview"), f"variable.{variable.get('name')}"
    return None, ""
