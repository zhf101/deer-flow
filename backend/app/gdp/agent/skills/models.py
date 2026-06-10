"""GDP Agent 阶段技能 Pydantic 数据模型。

本模块只描述 GDP 专用方法论引用。技能上下文用于告诉 Agent 当前阶段
应采用哪些方法论，不保存任务事实，也不替代 TaskRun/TaskStep/TaskEvent。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.gdp.datagen.config.task.models import DatagenTaskPhase


class GDPAgentSkillDefinition(BaseModel):
    """GDP Agent 阶段技能定义。"""

    skillId: str = Field(..., min_length=1, description="GDP 技能稳定标识，用于 state、TaskEvent 和前端展示。")
    version: str = Field(..., min_length=1, description="技能方法论版本。版本变化只影响新运行，不改写历史任务。")
    title: str = Field(..., min_length=1, description="技能中文标题。")
    description: str = Field(..., min_length=1, description="技能用途说明，描述它解决的造数阶段问题。")
    phases: list[DatagenTaskPhase] = Field(default_factory=list, description="允许注入该技能的 GDP Agent 阶段。")
    allowedActions: list[str] = Field(default_factory=list, description="该技能允许指导的动作类型，不等价于工具执行权限。")
    guidance: list[str] = Field(default_factory=list, description="可注入 Prompt 的轻量方法论要点。")
    auditEventType: str = Field(default="AGENT_SKILLS_SELECTED", description="技能被注入时记录的 TaskEvent 类型。")


class GDPAgentSkillContextItem(BaseModel):
    """注入 GDPState 的单个技能轻量引用。"""

    skillId: str = Field(..., description="GDP 技能稳定标识。")
    version: str = Field(..., description="技能方法论版本。")
    title: str = Field(..., description="技能中文标题。")
    description: str = Field(..., description="技能用途说明。")
    allowedActions: list[str] = Field(default_factory=list, description="当前技能允许指导的动作类型。")
    guidance: list[str] = Field(default_factory=list, description="可注入 Prompt 的轻量方法论要点。")


class GDPAgentSkillContext(BaseModel):
    """GDP Agent 当前阶段技能上下文。"""

    enabled: bool = Field(..., description="本次运行是否启用 GDP 阶段技能注入。")
    phase: str | None = Field(default=None, description="本次技能上下文对应的 GDP Agent 阶段。")
    skillIds: list[str] = Field(default_factory=list, description="当前阶段注入的技能 ID 列表。")
    skills: list[GDPAgentSkillContextItem] = Field(default_factory=list, description="当前阶段注入的轻量技能引用。")
