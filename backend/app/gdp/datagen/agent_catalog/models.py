"""Agent 能力目录数据模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.gdp.datagen.config.common.models import CapabilityCondition, CapabilitySideEffect, CapabilityType, InputFieldDefinition


class AgentSceneSearchRequest(BaseModel):
    """Agent 场景能力搜索请求。"""

    goal: str = Field(..., min_length=1, description="当前造数任务或子任务目标。")
    envCode: str | None = Field(default=None, max_length=64, description="目标环境编码，用于候选解释和后续执行。")
    userInputs: dict[str, Any] = Field(default_factory=dict, description="用户已提供的结构化入参。")
    visibleVariables: list[dict[str, Any]] = Field(default_factory=list, description="任务变量栈摘要。")
    limit: int = Field(default=5, ge=1, le=20, description="返回候选数量上限。")


class AgentSceneContract(BaseModel):
    """已发布场景对 Agent 暴露的能力契约。"""

    sceneCode: str = Field(..., description="场景编码。")
    sceneName: str = Field(..., description="场景名称。")
    sceneRemark: str | None = Field(default=None, description="场景备注。")
    tags: list[str] = Field(default_factory=list, description="场景业务标签。")
    capabilityType: CapabilityType = Field(..., description="场景能力类型。")
    businessDomain: str | None = Field(default=None, description="场景所属业务域。")
    preconditions: list[CapabilityCondition] = Field(default_factory=list, description="业务前置条件。")
    sideEffects: list[CapabilitySideEffect] = Field(default_factory=list, description="业务副作用。")
    agentDescription: str | None = Field(default=None, description="面向 Agent 的能力说明。")
    inputSchema: list[InputFieldDefinition] = Field(default_factory=list, description="场景入参定义。")
    resultSchema: list[InputFieldDefinition] | None = Field(default=None, description="场景结果结构。")
    resultMapping: dict[str, str] = Field(default_factory=dict, description="场景结果映射。")
    versionNo: int = Field(..., description="已发布场景版本号。")
    executable: bool = Field(default=True, description="该场景当前是否可被 Task 执行。")
    hasSideEffects: bool = Field(default=False, description="该场景是否存在写入或业务副作用。")


class AgentSceneCandidate(BaseModel):
    """Agent 场景搜索候选。"""

    contract: AgentSceneContract = Field(..., description="场景能力契约。")
    score: float = Field(..., ge=0, le=1, description="候选综合评分。")
    reasons: list[str] = Field(default_factory=list, description="候选命中理由。")
    missingInputs: list[str] = Field(default_factory=list, description="当前用户输入和变量栈尚不能绑定的必填入参。")
    requiresConfirmation: bool = Field(default=False, description="执行该场景前是否需要用户确认。")


class AgentSceneSearchResponse(BaseModel):
    """Agent 场景能力搜索响应。"""

    candidates: list[AgentSceneCandidate] = Field(default_factory=list, description="按评分倒序排列的候选场景。")
    queryTerms: list[str] = Field(default_factory=list, description="参与检索的关键词和别名。")


class AgentSourceSearchRequest(BaseModel):
    """Agent Source 能力搜索请求。"""

    goal: str = Field(..., min_length=1, description="当前缺失场景或原子能力目标。")
    sourceTypes: list[str] = Field(default_factory=lambda: ["HTTP", "SQL"], description="允许搜索的 Source 类型，取值为 HTTP、SQL。")
    envCode: str | None = Field(default=None, max_length=64, description="目标环境编码，用于候选解释和后续基础配置校验。")
    userInputs: dict[str, Any] = Field(default_factory=dict, description="用户已提供的结构化入参。")
    visibleVariables: list[dict[str, Any]] = Field(default_factory=list, description="任务变量栈摘要。")
    limit: int = Field(default=5, ge=1, le=20, description="返回候选数量上限。")


class AgentSourceContract(BaseModel):
    """HTTP/SQL Source 对 Agent 暴露的原子能力契约。"""

    sourceType: str = Field(..., description="Source 类型，HTTP 或 SQL。")
    sourceCode: str = Field(..., description="Source 编码。")
    sourceName: str = Field(..., description="Source 名称。")
    tags: list[str] = Field(default_factory=list, description="Source 业务标签。")
    capabilityType: CapabilityType = Field(..., description="Source 能力类型。")
    businessDomain: str | None = Field(default=None, description="Source 所属业务域。")
    sideEffects: list[CapabilitySideEffect] = Field(default_factory=list, description="Source 执行副作用。")
    agentDescription: str | None = Field(default=None, description="面向 Agent 的能力说明。")
    sysCode: str = Field(..., description="Source 所属系统编码。")
    method: str | None = Field(default=None, description="HTTP Source 请求方法。")
    path: str | None = Field(default=None, description="HTTP Source 相对路径。")
    datasourceCode: str | None = Field(default=None, description="SQL Source 数据源编码。")
    operation: str | None = Field(default=None, description="SQL 操作类型。")
    inputSchema: list[InputFieldDefinition] = Field(default_factory=list, description="Source 运行所需入参定义。")
    resultSchema: list[InputFieldDefinition] = Field(default_factory=list, description="Source 可产出的结果字段定义。")
    outputMapping: dict[str, str] = Field(default_factory=dict, description="Source 输出变量映射。")
    executable: bool = Field(default=True, description="该 Source 当前是否可用于生成场景。")
    hasSideEffects: bool = Field(default=False, description="该 Source 是否存在写入或业务副作用。")


class AgentSourceCandidate(BaseModel):
    """Agent Source 搜索候选。"""

    contract: AgentSourceContract = Field(..., description="Source 原子能力契约。")
    score: float = Field(..., ge=0, le=1, description="候选综合评分。")
    reasons: list[str] = Field(default_factory=list, description="候选命中理由。")
    missingInputs: list[str] = Field(default_factory=list, description="当前用户输入和变量栈尚不能绑定的必填入参。")
    requiresConfirmation: bool = Field(default=False, description="由该 Source 生成的写操作场景执行前是否需要用户确认。")


class AgentSourceSearchResponse(BaseModel):
    """Agent Source 能力搜索响应。"""

    candidates: list[AgentSourceCandidate] = Field(default_factory=list, description="按评分倒序排列的候选 Source。")
    queryTerms: list[str] = Field(default_factory=list, description="参与检索的关键词和别名。")


class AgentInfraResolveRequest(BaseModel):
    """Agent 基础配置解析请求。"""

    query: str = Field(..., min_length=1, description="用户目标、系统线索或 Source 描述，用于检索系统候选。")
    envCode: str = Field(default="DEV", min_length=1, max_length=64, description="目标环境编码。用户未指定时默认 DEV。")
    sysCode: str | None = Field(default=None, max_length=64, description="已知系统编码。提供后优先精确匹配系统。")
    datasourceCode: str | None = Field(default=None, max_length=128, description="SQL Source 已知数据源编码。")
    resourceType: str = Field(default="HTTP", description="待解析资源类型，HTTP 需要服务端点，SQL 需要数据源。")


class AgentInfraResolveResponse(BaseModel):
    """Agent 基础配置解析响应。"""

    matchedSystems: list[dict[str, Any]] = Field(default_factory=list, description="命中的系统候选，包含评分和命中理由。")
    matchedEnvironments: list[dict[str, Any]] = Field(default_factory=list, description="命中的环境配置。")
    matchedServiceEndpoints: list[dict[str, Any]] = Field(default_factory=list, description="命中的 HTTP 服务端点。")
    matchedDatasources: list[dict[str, Any]] = Field(default_factory=list, description="命中的数据库数据源。")
    confidence: float = Field(default=0, ge=0, le=1, description="本次基础配置解析置信度。")
    missingFields: list[str] = Field(default_factory=list, description="仍缺失的基础配置字段。")
    ready: bool = Field(default=False, description="基础配置是否已经满足目标资源配置需要。")
