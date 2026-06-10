"""GDP Agent 阶段技能 FastAPI 路由。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.gdp.agent.skills.models import GDPAgentSkillDefinition
from app.gdp.agent.skills.registry import get_gdp_skill_context, list_gdp_skills, list_gdp_skills_for_phase
from app.gdp.datagen.config.task.models import DatagenTaskPhase

router = APIRouter(tags=["data-factory-agent-skills"])


class GDPAgentSkillContextResponse(BaseModel):
    """GDP Agent 当前阶段技能上下文响应。"""

    enabled: bool = Field(..., description="本次技能上下文是否启用。")
    phase: str = Field(..., description="查询的 GDP Agent 阶段。")
    skillIds: list[str] = Field(default_factory=list, description="当前阶段应注入的技能 ID 列表。")
    skills: list[GDPAgentSkillDefinition] = Field(default_factory=list, description="当前阶段应注入的技能定义。")


@router.get("/agent-skills", response_model=list[GDPAgentSkillDefinition])
async def list_agent_skills() -> list[GDPAgentSkillDefinition]:
    return list_gdp_skills()


@router.get("/agent-skills/phase/{phase}", response_model=GDPAgentSkillContextResponse)
async def list_agent_skills_for_phase(phase: DatagenTaskPhase) -> GDPAgentSkillContextResponse:
    skills = list_gdp_skills_for_phase(phase)
    context = get_gdp_skill_context(phase)
    return GDPAgentSkillContextResponse(
        enabled=context["enabled"],
        phase=phase.value,
        skillIds=context["skillIds"],
        skills=skills,
    )
