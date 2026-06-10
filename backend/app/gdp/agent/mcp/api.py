"""GDP Agent MCP capability FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.gdp.agent.mcp.models import (
    GDPMCPCapabilityDecision,
    GDPMCPCapabilityEvaluateRequest,
    GDPMCPCapabilityPlanRequest,
    GDPMCPCapabilityPlanResponse,
    GDPMCPCapabilityPolicy,
    GDPMCPCapabilityResultApplyRequest,
    GDPMCPCapabilityResultApplyResponse,
)
from app.gdp.agent.mcp.planner import plan_gdp_mcp_capability_call
from app.gdp.agent.mcp.registry import (
    evaluate_gdp_mcp_capability,
    list_gdp_mcp_capabilities,
    list_gdp_mcp_capabilities_for_phase,
)
from app.gdp.agent.mcp.result_handler import apply_gdp_mcp_capability_result
from app.gdp.datagen.config.task.models import DatagenTaskPhase
from app.gdp.datagen.config.task.repository import DatagenTaskRepository
from app.gdp.datagen.config.task.service import DatagenTaskService
from deerflow.persistence.engine import get_session_factory

router = APIRouter(tags=["data-factory-agent-mcp"])


def _get_task_service() -> DatagenTaskService:
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=503, detail="Persistence not available")
    return DatagenTaskService(DatagenTaskRepository(sf))


class GDPMCPCapabilityListResponse(BaseModel):
    """GDP MCP capability 阶段查询响应。"""

    phase: str = Field(..., description="查询的 GDP Agent 阶段。")
    capabilities: list[GDPMCPCapabilityPolicy] = Field(default_factory=list, description="当前阶段允许使用的 MCP capability。")


@router.get("/agent-mcp/capabilities", response_model=list[GDPMCPCapabilityPolicy])
async def list_agent_mcp_capabilities() -> list[GDPMCPCapabilityPolicy]:
    return list_gdp_mcp_capabilities()


@router.get("/agent-mcp/capabilities/phase/{phase}", response_model=GDPMCPCapabilityListResponse)
async def list_agent_mcp_capabilities_for_phase(phase: DatagenTaskPhase) -> GDPMCPCapabilityListResponse:
    return GDPMCPCapabilityListResponse(
        phase=phase.value,
        capabilities=list_gdp_mcp_capabilities_for_phase(phase),
    )


@router.post("/agent-mcp/capabilities/evaluate", response_model=GDPMCPCapabilityDecision)
async def evaluate_agent_mcp_capability(body: GDPMCPCapabilityEvaluateRequest) -> GDPMCPCapabilityDecision:
    return evaluate_gdp_mcp_capability(
        capability_name=body.capabilityName,
        phase=body.phase,
        env_code=body.envCode,
        arguments=body.arguments,
        approved_approval_keys=body.approvedApprovalKeys,
        allow_config_write=body.allowConfigWrite,
        allow_business_write=body.allowBusinessWrite,
    )


@router.post("/agent-mcp/capabilities/plan", response_model=GDPMCPCapabilityPlanResponse)
async def plan_agent_mcp_capability(
    body: GDPMCPCapabilityPlanRequest,
    task_service: DatagenTaskService = Depends(_get_task_service),
) -> GDPMCPCapabilityPlanResponse:
    return await plan_gdp_mcp_capability_call(task_service, body)


@router.post("/agent-mcp/capabilities/apply-result", response_model=GDPMCPCapabilityResultApplyResponse)
async def apply_agent_mcp_capability_result(
    body: GDPMCPCapabilityResultApplyRequest,
    task_service: DatagenTaskService = Depends(_get_task_service),
) -> GDPMCPCapabilityResultApplyResponse:
    try:
        return await apply_gdp_mcp_capability_result(task_service, body)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"MCP capability 未注册：{body.capabilityName}") from None
