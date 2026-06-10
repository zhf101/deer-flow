"""GDP Agent 记忆 Pydantic 数据模型。

本模块描述跨造数任务复用的长期偏好和知识。Memory 只能作为推荐、
排序和提示上下文，不替代 TaskRun、TaskStep、TaskEvent 或 visibleVariables。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class GDPAgentMemoryScopeType(StrEnum):
    """GDP Agent 记忆作用域类型。"""

    USER = "USER"
    AGENT = "AGENT"
    ENV = "ENV"
    SYS = "SYS"
    RESOURCE = "RESOURCE"


class GDPAgentMemoryCategory(StrEnum):
    """GDP Agent 记忆分类。"""

    ENVIRONMENT_PREFERENCE = "environment_preference"
    SYSTEM_ALIAS = "system_alias"
    FIELD_MAPPING = "field_mapping"
    GOAL_PATTERN = "goal_pattern"
    SCENE_PREFERENCE = "scene_preference"
    SOURCE_PREFERENCE = "source_preference"
    SQL_PREFERENCE = "sql_preference"
    APPROVAL_PREFERENCE = "approval_preference"
    CORRECTION = "correction"


class GDPAgentMemoryStatus(StrEnum):
    """GDP Agent 记忆事实状态。"""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    SUPERSEDED = "SUPERSEDED"


class GDPAgentMemoryFactCreateRequest(BaseModel):
    """创建 GDP Agent 记忆事实请求。"""

    userId: str | None = Field(default=None, max_length=128, description="记忆所属用户 ID。为空表示 Agent 级或资源级共享记忆。")
    agentName: str = Field(default="gdp_agent", min_length=1, max_length=128, description="记忆所属 Agent 名称，默认 gdp_agent。")
    scopeType: GDPAgentMemoryScopeType = Field(..., description="记忆作用域类型，用于控制检索边界。")
    scopeKey: str = Field(..., min_length=1, max_length=256, description="作用域键，例如用户 ID、环境编码、系统编码、资源编码。")
    category: GDPAgentMemoryCategory = Field(..., description="记忆分类，决定参与推荐或上下文注入的方式。")
    memoryKey: str = Field(..., min_length=1, max_length=256, description="记忆事实键，同一作用域和分类下稳定标识一条偏好或知识。")
    value: dict[str, Any] = Field(default_factory=dict, description="记忆结构化值。不得保存 token、连接串、完整响应或一次性敏感数据。")
    confidence: float = Field(default=0.7, ge=0, le=1, description="记忆置信度。检索上下文优先使用高置信事实。")
    sourceTaskRunId: str | None = Field(default=None, max_length=64, description="产生该记忆的来源任务 ID，用于审计追溯。")
    sourceEventIds: list[str] = Field(default_factory=list, description="产生该记忆的来源 TaskEvent ID 列表。")
    evidenceSummary: str | None = Field(default=None, description="人类可读证据摘要，说明为什么形成该记忆。")
    expiresAt: datetime | None = Field(default=None, description="记忆过期时间。为空表示不过期。")


class GDPAgentMemoryFactUpdateRequest(BaseModel):
    """更新 GDP Agent 记忆事实请求。"""

    factId: str = Field(..., min_length=1, max_length=64, description="记忆事实业务 ID。")
    value: dict[str, Any] | None = Field(default=None, description="新的结构化记忆值。为空表示不更新。")
    confidence: float | None = Field(default=None, ge=0, le=1, description="新的置信度。为空表示不更新。")
    status: GDPAgentMemoryStatus | None = Field(default=None, description="新的记忆状态。为空表示不更新。")
    evidenceSummary: str | None = Field(default=None, description="新的证据摘要。为空表示不更新。")
    expiresAt: datetime | None = Field(default=None, description="新的过期时间。为空表示不更新。")


class GDPAgentMemoryFactIdRequest(BaseModel):
    """按 ID 操作 GDP Agent 记忆事实请求。"""

    factId: str = Field(..., min_length=1, max_length=64, description="记忆事实业务 ID。")


class GDPAgentMemoryReloadResponse(BaseModel):
    """GDP Agent 记忆重载响应。"""

    reloaded: bool = Field(..., description="是否完成重载动作。当前实现为轻量无状态刷新。")
    message: str = Field(..., description="重载结果说明。")


class GDPAgentMemoryFactResponse(BaseModel):
    """GDP Agent 记忆事实响应。"""

    id: str = Field(..., description="数据库主键 ID。")
    factId: str = Field(..., description="记忆事实业务 ID。")
    userId: str | None = Field(default=None, description="记忆所属用户 ID。")
    agentName: str = Field(..., description="记忆所属 Agent 名称。")
    scopeType: GDPAgentMemoryScopeType = Field(..., description="记忆作用域类型。")
    scopeKey: str = Field(..., description="记忆作用域键。")
    category: GDPAgentMemoryCategory = Field(..., description="记忆分类。")
    memoryKey: str = Field(..., description="记忆事实键。")
    value: dict[str, Any] = Field(default_factory=dict, description="结构化记忆值。")
    confidence: float = Field(..., description="记忆置信度。")
    status: GDPAgentMemoryStatus = Field(..., description="记忆事实状态。")
    sourceTaskRunId: str | None = Field(default=None, description="来源任务 ID。")
    sourceEventIds: list[str] = Field(default_factory=list, description="来源 TaskEvent ID 列表。")
    evidenceSummary: str | None = Field(default=None, description="证据摘要。")
    createdAt: datetime = Field(..., description="创建时间。")
    updatedAt: datetime = Field(..., description="最近更新时间。")
    lastUsedAt: datetime | None = Field(default=None, description="最近被注入上下文的时间。")
    useCount: int = Field(default=0, ge=0, description="被注入上下文的次数。")
    successCount: int = Field(default=0, ge=0, description="参与成功任务的次数。")
    failureCount: int = Field(default=0, ge=0, description="参与失败任务的次数。")
    expiresAt: datetime | None = Field(default=None, description="过期时间。")


class GDPAgentMemoryContextFact(BaseModel):
    """注入 GDPState 的轻量记忆事实。"""

    factId: str = Field(..., description="记忆事实业务 ID。")
    category: GDPAgentMemoryCategory = Field(..., description="记忆分类。")
    memoryKey: str = Field(..., description="记忆事实键。")
    scopeType: GDPAgentMemoryScopeType = Field(..., description="记忆作用域类型。")
    scopeKey: str = Field(..., description="记忆作用域键。")
    value: dict[str, Any] = Field(default_factory=dict, description="可注入 Prompt 的脱敏结构化值。")
    confidence: float = Field(..., description="记忆置信度。")
    evidenceSummary: str | None = Field(default=None, description="证据摘要。")


class GDPAgentMemoryContext(BaseModel):
    """GDP Agent 只读记忆上下文。"""

    enabled: bool = Field(..., description="本次运行是否启用记忆上下文。")
    userId: str | None = Field(default=None, description="检索记忆使用的用户 ID。")
    envCode: str | None = Field(default=None, description="检索记忆使用的环境编码。")
    phase: str | None = Field(default=None, description="注入记忆时的 Agent 阶段。")
    facts: list[GDPAgentMemoryContextFact] = Field(default_factory=list, description="本次注入的轻量记忆事实。")
    categories: dict[str, list[GDPAgentMemoryContextFact]] = Field(default_factory=dict, description="按分类分组的记忆事实，方便节点按需读取。")


class GDPAgentMemoryTraceItem(BaseModel):
    """GDP Agent 记忆注入轨迹。"""

    factId: str = Field(..., description="被注入的记忆事实业务 ID。")
    category: GDPAgentMemoryCategory = Field(..., description="记忆分类。")
    memoryKey: str = Field(..., description="记忆事实键。")
    reason: str = Field(..., description="本次注入该记忆的原因。")
