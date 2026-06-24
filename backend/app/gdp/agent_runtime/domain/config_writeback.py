"""配置写回领域模型。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ConfigWritebackStatus(StrEnum):
    """配置写回结果状态。

    SUCCESS：配置已成功写入并可继续回弹父缺口。
    SKIPPED：确定性前置条件不满足，未发起业务配置写入。
    FAILED：尝试写入但校验、依赖或持久化失败。
    """

    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ConfigWritebackResult(BaseModel):
    """一次 Runtime 自动写入 datagen 配置的结构化结果。

    业务目标：记录配置写入是否成功、目标资源、关联缺口和失败原因，
    供后续回弹父缺口、timeline 审计和问题诊断使用。
    """

    status: ConfigWritebackStatus = Field(description="写回状态：SUCCESS 成功、SKIPPED 跳过、FAILED 失败。")
    target_kind: str = Field(default="SCENE", description="目标资源类型。当前第一刀固定为 SCENE。")
    target_code: str | None = Field(default=None, description="目标资源编码。写入成功时为新发布的 scene_code。")
    message: str = Field(description="面向用户和审计展示的中文摘要。")
    reason: str | None = Field(default=None, description="失败或跳过原因。成功时为空。")
    validation_issues: list[str] = Field(default_factory=list, description="确定性校验问题摘要，不包含敏感载荷。")
    parent_requirement_id: str | None = Field(default=None, description="关联的父 SCENE 缺口 ID。")
    source_requirement_id: str | None = Field(default=None, description="关联的 SOURCE 子缺口 ID。")
    proposal_id: str | None = Field(default=None, description="关联的 Source 候选集 Proposal ID。")
