"""配置写回端口。"""

from __future__ import annotations

from typing import Any, Protocol

from ..domain.config_writeback import ConfigWritebackResult
from ..models import InfraCandidate, Requirement, RequirementProposal, SourceCandidate, TaskRun


class ConfigWritebackPort(Protocol):
    """Runtime 自动写入 datagen 配置的端口。

    业务目标：隔离 Agent Runtime 编排和 datagen 配置持久化细节，确保 Runtime
    只能通过类型化 service 合约写入业务配置，不能直接写数据库表或裸 JSON。
    """

    async def create_and_publish_scene_from_sources(
        self,
        *,
        task_run: TaskRun,
        scene_requirement: Requirement,
        source_requirement: Requirement,
        proposal: RequirementProposal,
        source_candidates: list[SourceCandidate],
        infra_candidates: list[InfraCandidate],
        inputs: dict[str, Any],
    ) -> ConfigWritebackResult:
        """基于已有 Source 候选创建并发布组合 Scene。"""
        ...
