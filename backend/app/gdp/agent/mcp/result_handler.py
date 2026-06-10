"""GDP MCP capability 结果归并服务。"""

from __future__ import annotations

from typing import Any

from app.gdp.agent.mcp.models import (
    GDPMCPCapabilityPolicy,
    GDPMCPCapabilityResultApplyRequest,
    GDPMCPCapabilityResultApplyResponse,
    GDPMCPOutputSensitivity,
    GDPMCPOutputVariablePolicy,
)
from app.gdp.agent.mcp.registry import get_gdp_mcp_capability
from app.gdp.agent.middlewares.output_budget import output_keys, summarize_gdp_output
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.service import DatagenTaskService


async def apply_gdp_mcp_capability_result(
    task_service: DatagenTaskService,
    request: GDPMCPCapabilityResultApplyRequest,
) -> GDPMCPCapabilityResultApplyResponse:
    """把 MCP capability 执行结果归并回 GDP 任务生命周期。

    安全约定：``outputSensitivity`` / ``outputVariablePolicy`` 永远以服务端
    registry 按 ``capabilityName`` 注册的策略为准，**不信任调用方请求体中的
    策略字段**，避免调用方自报策略绕过脱敏或向变量栈写入任意输出。
    capability 未注册时抛出 ``KeyError``，由 API 层转为 404。
    """

    capability = get_gdp_mcp_capability(request.capabilityName)
    task_run = await task_service.get_task_run(request.taskRunId)
    phase = request.phase or task_run.phase
    visible_variable_names: list[str] = []
    if request.success and capability.outputVariablePolicy == GDPMCPOutputVariablePolicy.VISIBLE_VARIABLE:
        variables = await task_service.append_visible_variables_from_mcp_result(
            request.taskRunId,
            capability_name=request.capabilityName,
            output=request.output,
            sensitive=capability.outputSensitivity == GDPMCPOutputSensitivity.SENSITIVE,
            storage_ref=request.storageRef,
        )
        output_names = set(request.output)
        visible_variable_names = [variable.name for variable in variables if variable.name in output_names]

    result_ref = _result_ref(request, capability, visible_variable_names)
    event_type = "MCP_CAPABILITY_RESULT_RECORDED" if request.success else "MCP_CAPABILITY_RESULT_FAILED"
    await task_service.record_event(
        request.taskRunId,
        event_type=event_type,
        phase=_event_phase(phase),
        message=f"MCP capability {request.capabilityName} 结果已归并到任务生命周期。",
        payload={
            "capabilityName": request.capabilityName,
            "success": request.success,
            "outputVariablePolicy": capability.outputVariablePolicy.value,
            "outputSensitivity": capability.outputSensitivity.value,
            "outputKeys": output_keys(request.output),
            "outputPreview": _output_preview(request, capability),
            "storageRef": request.storageRef,
            "visibleVariables": visible_variable_names,
            "errorType": request.errorType,
            "errorMessage": request.errorMessage,
            "resultRef": result_ref,
        },
    )
    return GDPMCPCapabilityResultApplyResponse(
        resultRef=result_ref,
        visibleVariables=visible_variable_names,
        eventType=event_type,
    )


def _result_ref(
    request: GDPMCPCapabilityResultApplyRequest,
    capability: GDPMCPCapabilityPolicy,
    visible_variable_names: list[str],
) -> dict[str, Any]:
    return {
        "ref_type": "MCP_CAPABILITY_RESULT",
        "capability_name": request.capabilityName,
        "storage_ref": request.storageRef,
        "summary": {
            "success": request.success,
            "outputKeys": output_keys(request.output),
            "outputVariablePolicy": capability.outputVariablePolicy.value,
            "outputSensitivity": capability.outputSensitivity.value,
            "visibleVariables": visible_variable_names,
            "errorType": request.errorType,
        },
    }


def _output_preview(request: GDPMCPCapabilityResultApplyRequest, capability: GDPMCPCapabilityPolicy) -> Any:
    if capability.outputSensitivity == GDPMCPOutputSensitivity.SENSITIVE:
        return None
    return summarize_gdp_output(request.output)["valuePreview"]


def _event_phase(value: DatagenTaskPhase | str | None) -> DatagenTaskPhase:
    if isinstance(value, DatagenTaskPhase):
        return value
    try:
        return DatagenTaskPhase(str(value))
    except ValueError:
        return DatagenTaskPhase.INTAKE
