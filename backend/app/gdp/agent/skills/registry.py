"""GDP Agent 阶段技能静态注册表。"""

from __future__ import annotations

from app.gdp.agent.skills.models import GDPAgentSkillContext, GDPAgentSkillContextItem, GDPAgentSkillDefinition
from app.gdp.datagen.config.task.models import DatagenTaskPhase

SKILL_VERSION = "2026-06-10"

_GDP_SKILLS: tuple[GDPAgentSkillDefinition, ...] = (
    GDPAgentSkillDefinition(
        skillId="gdp-scene-selection",
        version=SKILL_VERSION,
        title="已有场景选择",
        description="在已有已发布场景中选择最能满足当前造数目标的候选能力。",
        phases=[DatagenTaskPhase.SCENE_FULFILLMENT],
        allowedActions=["search_scene_contracts", "get_scene_contract", "bind_scene_inputs"],
        guidance=[
            "优先复用已发布场景，候选排序必须结合当前用户输入、变量栈和副作用风险。",
            "候选分数接近、低置信或涉及写操作时进入用户确认，不擅自执行。",
        ],
    ),
    GDPAgentSkillDefinition(
        skillId="gdp-scene-design",
        version=SKILL_VERSION,
        title="场景设计",
        description="缺少可复用场景时，基于 Source 契约生成可发布的造数场景。",
        phases=[DatagenTaskPhase.SCENE_DESIGN],
        allowedActions=["search_source_contracts", "compose_scene_draft_from_source", "publish_scene_from_source"],
        guidance=[
            "场景入参、出参和副作用必须从 Source 契约推导，不能凭空创造业务字段。",
            "自动发布前必须经过场景校验，写操作场景继续保留审批边界。",
        ],
    ),
    GDPAgentSkillDefinition(
        skillId="gdp-sql-source-design",
        version=SKILL_VERSION,
        title="SQL Source 设计",
        description="设计或修正 SQL Source，使其可被场景编排安全复用。",
        phases=[DatagenTaskPhase.SCENE_DESIGN, DatagenTaskPhase.SOURCE_CONFIG],
        allowedActions=[
            "parse_sql_source_from_agent",
            "resolve_sql_source_basis",
            "upsert_sql_source_from_agent",
            "test_sql_source_from_agent",
        ],
        guidance=[
            "SQL Source 默认只表达受控数据读取或明确审批后的写入能力。",
            "数据源、环境和系统编码必须来自基础配置，缺失时转入基础配置阶段。",
        ],
    ),
    GDPAgentSkillDefinition(
        skillId="gdp-http-source-design",
        version=SKILL_VERSION,
        title="HTTP Source 设计",
        description="设计或修正 HTTP Source，使其可被场景编排安全复用。",
        phases=[DatagenTaskPhase.SCENE_DESIGN, DatagenTaskPhase.SOURCE_CONFIG],
        allowedActions=["resolve_http_source_basis", "upsert_http_source_from_agent", "test_http_source_from_agent"],
        guidance=[
            "HTTP Source 的系统、环境、路径、方法和映射必须来自用户输入或受控配置。",
            "请求体、响应体和敏感字段只保存结构化摘要，不把完整响应注入 Prompt。",
        ],
    ),
    GDPAgentSkillDefinition(
        skillId="gdp-infra-resolution",
        version=SKILL_VERSION,
        title="基础配置补齐",
        description="补齐系统、环境、服务端点和数据源等造数基础配置。",
        phases=[DatagenTaskPhase.INFRA_CONFIG],
        allowedActions=[
            "resolve_infra_basis",
            "upsert_system_from_agent",
            "upsert_environment_from_agent",
            "upsert_service_endpoint_from_agent",
            "upsert_datasource_from_agent",
        ],
        guidance=[
            "基础配置只补齐当前任务必须的最小集合，避免引入无关系统或环境。",
            "Source 保存失败中返回的 missing 字段是补齐范围的主要依据。",
        ],
    ),
    GDPAgentSkillDefinition(
        skillId="gdp-approval-policy",
        version=SKILL_VERSION,
        title="审批策略",
        description="在执行写操作、保存配置或触发高风险动作前生成审批边界。",
        phases=[
            DatagenTaskPhase.SCENE_DESIGN,
            DatagenTaskPhase.SOURCE_CONFIG,
            DatagenTaskPhase.INFRA_CONFIG,
            DatagenTaskPhase.SCENE_EXECUTING,
        ],
        allowedActions=[
            "publish_scene_from_source",
            "upsert_http_source_from_agent",
            "upsert_sql_source_from_agent",
            "test_http_source_from_agent",
            "test_sql_source_from_agent",
            "upsert_system_from_agent",
            "upsert_environment_from_agent",
            "upsert_service_endpoint_from_agent",
            "upsert_datasource_from_agent",
            "run_datagen_scene_for_task",
        ],
        guidance=[
            "写操作、配置写入和业务副作用不能绕过审批策略。",
            "审批文案必须说明环境、资源、动作和可见副作用。",
        ],
    ),
    GDPAgentSkillDefinition(
        skillId="gdp-task-recovery",
        version=SKILL_VERSION,
        title="任务恢复",
        description="在执行或恢复造数任务时避免重复副作用并保持 checkpoint 轻量。",
        phases=[DatagenTaskPhase.SCENE_EXECUTING],
        allowedActions=["get_datagen_task_state", "run_datagen_scene_for_task"],
        guidance=[
            "遇到相同场景、环境和入参的成功步骤时优先幂等复用。",
            "完整执行结果落 TaskStep 或业务表，state 只保存 resultRef 和摘要。",
        ],
    ),
    GDPAgentSkillDefinition(
        skillId="gdp-progress-reflection",
        version=SKILL_VERSION,
        title="进度反思",
        description="判断当前结果是否满足总体造数目标，并决定是否继续搜索下一场景。",
        phases=[DatagenTaskPhase.PROGRESS_REFLECTION],
        allowedActions=["get_datagen_task_state", "reflect_scene_result", "search_scene_contracts"],
        guidance=[
            "反思只基于 TaskRun、TaskStep、visibleVariables 和当前结果摘要，不依赖长消息历史。",
            "总体目标未满足时保留父目标，回到可继续推进的业务阶段。",
        ],
    ),
    GDPAgentSkillDefinition(
        skillId="gdp-variable-stack",
        version=SKILL_VERSION,
        title="变量栈治理",
        description="管理场景输出变量的语义、预览、敏感性和后续绑定方式。",
        phases=[DatagenTaskPhase.SCENE_FULFILLMENT, DatagenTaskPhase.PROGRESS_REFLECTION],
        allowedActions=["get_datagen_task_state", "bind_scene_inputs", "reflect_scene_result"],
        guidance=[
            "变量全量值保存在业务表，Prompt 和 checkpoint 只使用预览、schema、size 和敏感标记。",
            "后续场景绑定优先使用当前任务变量栈，其次才参考 memory 或默认配置。",
        ],
    ),
)


def list_gdp_skills() -> list[GDPAgentSkillDefinition]:
    """列出所有 GDP 专用阶段技能。"""

    return list(_GDP_SKILLS)


def list_gdp_skills_for_phase(phase: DatagenTaskPhase | str | None) -> list[GDPAgentSkillDefinition]:
    """按当前 GDP Agent 阶段列出应注入的技能。"""

    normalized = _normalize_phase(phase)
    if normalized is None:
        return []
    return [skill for skill in _GDP_SKILLS if normalized in skill.phases]


def get_gdp_skill_context(phase: DatagenTaskPhase | str | None, *, enabled: bool = True) -> dict:
    """构造可写入 GDPState 的轻量技能上下文。"""

    normalized = _normalize_phase(phase)
    if not enabled:
        return GDPAgentSkillContext(enabled=False, phase=normalized.value if normalized else None).model_dump(mode="json")
    skills = list_gdp_skills_for_phase(normalized)
    items = [
        GDPAgentSkillContextItem(
            skillId=skill.skillId,
            version=skill.version,
            title=skill.title,
            description=skill.description,
            allowedActions=skill.allowedActions,
            guidance=skill.guidance,
        )
        for skill in skills
    ]
    return GDPAgentSkillContext(
        enabled=True,
        phase=normalized.value if normalized else None,
        skillIds=[item.skillId for item in items],
        skills=items,
    ).model_dump(mode="json")


def _normalize_phase(phase: DatagenTaskPhase | str | None) -> DatagenTaskPhase | None:
    if phase is None:
        return None
    if isinstance(phase, DatagenTaskPhase):
        return phase
    try:
        return DatagenTaskPhase(str(phase))
    except ValueError:
        return None
