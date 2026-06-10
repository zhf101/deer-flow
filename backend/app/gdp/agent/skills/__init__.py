"""GDP Agent 阶段技能注册模块。"""

from app.gdp.agent.skills.models import GDPAgentSkillContext, GDPAgentSkillContextItem, GDPAgentSkillDefinition
from app.gdp.agent.skills.registry import (
    get_gdp_skill_context,
    list_gdp_skills,
    list_gdp_skills_for_phase,
)

__all__ = [
    "GDPAgentSkillContext",
    "GDPAgentSkillContextItem",
    "GDPAgentSkillDefinition",
    "get_gdp_skill_context",
    "list_gdp_skills",
    "list_gdp_skills_for_phase",
]
