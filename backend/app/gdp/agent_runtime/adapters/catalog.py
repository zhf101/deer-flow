"""场景目录适配器——为用户的造数目标搜索合适的已发布场景。

业务目标：连接运行时引擎和 datagen 的场景能力目录（AgentCatalogService），
根据用户的造数目标、环境和当前输入，从已发布场景中检索最匹配的候选方案。
当前动作：search() 调用 Catalog 搜索候选，get_contract() 解析显式场景的契约，
两者都将 Catalog 返回的原始数据转换为运行时内部的 SceneCandidate 格式。
预期结果：运行时引擎拿到候选列表后，通过 selection 模块做出选择决策。

设计红线：不在 runtime 内复刻分词/同义词/打分逻辑，全部复用 Catalog 服务；
只做必要的归一化（评分 clamp 到 [0,1]）和契约快照哈希。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from app.gdp.datagen.agent_catalog.models import AgentSceneCandidate, AgentSceneContract

from ..models import SceneCandidate
from ..support.errors import RuntimeDependencyError


class SceneCatalogPort(Protocol):
    """场景目录检索端口——为用户的造数目标匹配合适的已发布场景。

    业务目标：定义运行时引擎与场景目录之间的交互契约，
    运行时只依赖此协议，便于测试时注入模拟实现。
    """

    async def search(
        self,
        *,
        goal: str,
        env_code: str | None,
        user_inputs: dict[str, Any],
        visible_variables: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[SceneCandidate], list[str]]:
        """根据用户造数目标搜索可用的场景候选。

        业务目标：从已发布的场景目录中检索与用户需求最匹配的场景列表，
        供后续的 selection 模块做出选择决策。
        当前动作：将用户目标、环境、已有输入和变量传递给 Catalog 服务进行检索。
        预期结果：返回按匹配度排序的候选列表和本次检索使用的关键词。
        """
        ...

    async def get_contract(
        self,
        *,
        scene_code: str,
        user_inputs: dict[str, Any],
    ) -> SceneCandidate:
        """获取用户显式指定的场景的契约快照。

        业务目标：当用户或系统直接给出场景编码（而非通过搜索）时，
        获取该场景的入参契约，检查当前输入是否完整，合成单候选供选择决策使用。
        当前动作：按 scene_code 查询场景的输入参数定义和副作用标记。
        预期结果：返回包含缺失入参信息和契约哈希的 SceneCandidate。
        """
        ...


def _contract_hash(contract: AgentSceneContract) -> str:
    """对场景契约快照做稳定哈希，用于后续检测场景接口是否发生变更（契约漂移）。

    业务目标：记录选择时刻的场景接口状态，若场景在执行前被修改（如新增必填参数），
    系统可通过对比哈希发现漂移，避免用旧契约执行新接口导致造数失败。
    """
    raw = json.dumps(contract.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _clamp_score(score: float) -> float:
    """将 Catalog 返回的匹配度评分归一到 [0, 1] 区间。

    业务目标：确保候选场景的评分始终在模型定义的合法范围内，
    避免因 Catalog 内部评分算法返回超范围值而导致运行时校验报错。
    """
    return max(0.0, min(1.0, float(score)))


def _to_candidate(candidate: AgentSceneCandidate) -> SceneCandidate:
    """将 Catalog 返回的原始候选转换为运行时内部的 SceneCandidate 格式。

    业务目标：隔离外部 Catalog 服务的数据格式变化，确保运行时引擎只使用统一的内部模型。
    当前动作：提取场景编码、名称、评分、命中理由、缺失入参和契约哈希。
    """
    contract = candidate.contract
    return SceneCandidate(
        scene_code=contract.sceneCode,
        scene_name=contract.sceneName,
        score=_clamp_score(candidate.score),
        reasons=list(candidate.reasons),
        missing_inputs=list(candidate.missingInputs),
        requires_confirmation=candidate.requiresConfirmation,
        contract_hash=_contract_hash(contract),
    )


def _provided_keys(user_inputs: dict[str, Any]) -> set[str]:
    """从用户入参推导已提供键集，用于显式契约缺参判定。

    与 Catalog _provided_keys 同源（小写归一），但显式路径只有 user_inputs，没有变量栈。
    """
    return {str(key).lower() for key in user_inputs}


def _missing_required_inputs(contract: AgentSceneContract, provided_keys: set[str]) -> list[str]:
    """按契约字段判断显式 scene_code 路径缺少哪些必填入参。

    Runtime 自己维护这份轻量契约判定，不依赖 Catalog service 的内部 helper。
    """
    missing: list[str] = []
    for field in contract.inputSchema:
        if field.name == "env":
            continue
        if not field.required:
            continue
        candidates = {field.name.lower()}
        if field.semanticType:
            candidates.add(field.semanticType.lower())
        if field.label:
            candidates.add(field.label.lower())
        candidates.update(alias.lower() for alias in field.aliases)
        if candidates.isdisjoint(provided_keys):
            missing.append(field.name)
    return missing


def _explicit_candidate(contract: AgentSceneContract, user_inputs: dict[str, Any]) -> SceneCandidate:
    """为用户显式指定的场景构造单候选，跳过搜索直接按契约解析。

    业务目标：当用户直接给出场景编码（如已知场景名称），无需走搜索流程，
    直接解析该场景的入参契约，检查当前输入是否完整，构造一个"满分"候选。
    当前动作：评分固定 1.0（非检索来源），缺失入参通过契约字段逐一比对判定。
    """
    missing_inputs = _missing_required_inputs(contract, _provided_keys(user_inputs))
    return SceneCandidate(
        scene_code=contract.sceneCode,
        scene_name=contract.sceneName,
        score=1.0,
        reasons=["显式指定 scene_code，按契约解析"],
        missing_inputs=missing_inputs,
        requires_confirmation=contract.hasSideEffects,
        contract_hash=_contract_hash(contract),
    )


def _to_runtime_dependency_error(exc: Exception) -> RuntimeDependencyError | None:
    """将下游 Catalog 服务的 HTTP 风格异常转换为运行时领域错误。

    业务目标：隔离外部服务的异常格式，让运行时引擎统一处理依赖不可用的情况，
    向用户展示友好的"服务暂不可用"提示而非原始技术错误。
    """

    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        return None
    detail = getattr(exc, "detail", None)
    return RuntimeDependencyError(status_code, str(detail or exc))


class AgentCatalogAdapter:
    """场景目录服务的默认适配实现，连接 datagen 的场景能力目录。

    业务目标：将运行时引擎的场景搜索请求委托给 datagen AgentCatalogService，
    完成从"用户造数目标"到"可用场景候选列表"的转换。
    支持延迟初始化，首次使用时自动组装 Catalog 服务依赖链。
    """

    def __init__(self, service: Any | None = None) -> None:
        self._service = service

    def _get_service(self) -> Any:
        if self._service is not None:
            return self._service
        from app.gdp.datagen.agent_catalog.service import AgentCatalogService
        from app.gdp.datagen.config.scene.repository import SceneRepository
        from deerflow.persistence.engine import get_session_factory

        session_factory = get_session_factory()
        if session_factory is None:
            raise RuntimeDependencyError(503, "Catalog persistence not available")
        self._service = AgentCatalogService(scene_repository=SceneRepository(session_factory))
        return self._service

    async def search(
        self,
        *,
        goal: str,
        env_code: str | None,
        user_inputs: dict[str, Any],
        visible_variables: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[SceneCandidate], list[str]]:
        from app.gdp.datagen.agent_catalog.models import AgentSceneSearchRequest

        try:
            response = await self._get_service().search_scene_contracts(
                AgentSceneSearchRequest(
                    goal=goal,
                    envCode=env_code,
                    userInputs=user_inputs,
                    visibleVariables=visible_variables,
                    limit=limit,
                )
            )
        except Exception as exc:
            mapped = _to_runtime_dependency_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise
        candidates = [_to_candidate(item) for item in response.candidates]
        return candidates, list(response.queryTerms)

    async def get_contract(
        self,
        *,
        scene_code: str,
        user_inputs: dict[str, Any],
    ) -> SceneCandidate:
        # scene_code 不存在 / 未发布保持 404 语义；依赖不可用仍收敛成运行时错误。
        try:
            contract = await self._get_service().get_scene_contract(scene_code)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                raise
            mapped = _to_runtime_dependency_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise
        return _explicit_candidate(contract, user_inputs)
