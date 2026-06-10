"""GDP MCP capability 调用计划服务。"""

from __future__ import annotations

from app.gdp.agent.mcp.models import (
    GDPMCPCapabilityCallSpec,
    GDPMCPCapabilityPlanRequest,
    GDPMCPCapabilityPlanResponse,
)
from app.gdp.agent.mcp.registry import evaluate_gdp_mcp_capability, get_gdp_mcp_capability
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.service import DatagenTaskService


async def plan_gdp_mcp_capability_call(
    task_service: DatagenTaskService,
    request: GDPMCPCapabilityPlanRequest,
) -> GDPMCPCapabilityPlanResponse:
    """评估并记录一次 GDP MCP capability 计划调用。"""

    task_run = await task_service.get_task_run(request.taskRunId)
    phase = request.phase or task_run.phase
    env_code = request.envCode or task_run.envCode
    decision = evaluate_gdp_mcp_capability(
        capability_name=request.capabilityName,
        phase=phase,
        env_code=env_code,
        arguments=request.arguments,
        approved_approval_keys=request.approvedApprovalKeys,
        allow_config_write=request.allowConfigWrite,
        allow_business_write=request.allowBusinessWrite,
    )
    if not decision.allowed:
        await task_service.record_event(
            request.taskRunId,
            event_type="MCP_CAPABILITY_REJECTED",
            phase=_event_phase(phase),
            message=f"MCP capability {request.capabilityName} 未通过 GDP 策略评估。",
            payload={"decision": decision.model_dump(mode="json"), "argumentsKeys": sorted(request.arguments.keys())},
        )
        return GDPMCPCapabilityPlanResponse(decision=decision)

    capability = get_gdp_mcp_capability(request.capabilityName)
    call_spec = GDPMCPCapabilityCallSpec(
        taskRunId=request.taskRunId,
        capabilityName=capability.capabilityName,
        phase=_event_phase(phase).value,
        envCode=env_code,
        mcpServerName=capability.mcpServerName,
        mcpToolName=capability.mcpToolName,
        arguments=request.arguments,
        approvalKey=decision.approvalKey,
        outputSensitivity=decision.outputSensitivity,
        outputVariablePolicy=decision.outputVariablePolicy,
        auditEventType=capability.auditEventType,
    )
    result_ref = _result_ref(call_spec, decision.allowed)
    await task_service.record_event(
        request.taskRunId,
        event_type=capability.auditEventType,
        phase=_event_phase(phase),
        message=f"MCP capability {request.capabilityName} 已生成受控调用计划。",
        payload={
            "decision": decision.model_dump(mode="json"),
            "callSpec": call_spec.model_dump(mode="json"),
            "resultRef": result_ref,
        },
    )
    return GDPMCPCapabilityPlanResponse(
        decision=decision,
        callSpec=call_spec,
        resultRef=result_ref,
    )


def _result_ref(call_spec: GDPMCPCapabilityCallSpec, allowed: bool) -> dict:
    return {
        "ref_type": "MCP_CAPABILITY",
        "capability_name": call_spec.capabilityName,
        "approval_key": call_spec.approvalKey,
        "summary": {
            "allowed": allowed,
            "phase": call_spec.phase,
            "outputVariablePolicy": call_spec.outputVariablePolicy,
        },
    }


def _event_phase(value: DatagenTaskPhase | str | None) -> DatagenTaskPhase:
    if isinstance(value, DatagenTaskPhase):
        return value
    try:
        return DatagenTaskPhase(str(value))
    except ValueError:
        return DatagenTaskPhase.INTAKE
