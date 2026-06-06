"""造数场景仓储。"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gdp.datagen.scene.models import (
    SceneDefinition,
    SceneSummary,
    SceneVersion,
    ValidationResult,
)
from app.gdp.models import SceneStatus, VersionStatus
from app.gdp.persistence.model import (
    DataFactoryConfigAuditRow,
    DataFactorySceneRow,
    DataFactorySceneVersionRow,
)


class SceneNotFoundError(LookupError):
    """请求的场景不存在。"""


class SceneConflictError(RuntimeError):
    """场景违反唯一约束。"""


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


class SceneRepository:
    """造数场景仓储。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def list_scenes(
        self, *, scene_type: str | None = None, status: SceneStatus | None = None,
        keyword: str | None = None, limit: int = 100, offset: int = 0,
    ) -> list[SceneSummary]:
        stmt = select(DataFactorySceneRow)
        if scene_type:
            stmt = stmt.where(DataFactorySceneRow.scene_type == scene_type)
        if status:
            stmt = stmt.where(DataFactorySceneRow.status == status.value)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                DataFactorySceneRow.scene_code.like(pattern) | DataFactorySceneRow.scene_name.like(pattern)
            )
        stmt = stmt.order_by(DataFactorySceneRow.updated_at.desc(), DataFactorySceneRow.scene_code.asc()).offset(offset).limit(limit)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._summary(row) for row in rows]

    async def create_scene(self, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        async with self._sf() as session:
            existing = await self._get_scene_row(session, definition.sceneCode)
            if existing is not None:
                raise SceneConflictError(f"sceneCode already exists: {definition.sceneCode}")
            now = _now()
            scene = DataFactorySceneRow(
                id=_new_id(), scene_code=definition.sceneCode, scene_name=definition.sceneName,
                scene_remark=definition.sceneRemark, scene_type=definition.sceneType,
                status=SceneStatus.DRAFT.value, current_version_no=None,
                created_by=operator, updated_by=operator, created_at=now, updated_at=now,
            )
            session.add(scene)
            version = self._make_version_row(scene, definition, version_no=1, operator=operator)
            session.add(version)
            self._add_audit(session, "SCENE", scene.id, "CREATE", operator, None, definition.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(scene)
            await session.refresh(version)
            return self._version(scene, version)

    async def update_scene(self, scene_code: str, definition: SceneDefinition, *, operator: str | None = None) -> SceneVersion:
        if scene_code != definition.sceneCode:
            raise SceneConflictError("path sceneCode must match request sceneCode")
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            before = self._scene_payload(scene)
            scene.scene_name = definition.sceneName
            scene.scene_remark = definition.sceneRemark
            scene.scene_type = definition.sceneType
            scene.status = SceneStatus.DRAFT.value
            scene.updated_by = operator
            scene.updated_at = _now()
            version_no = await self._next_version_no(session, scene.id)
            version = self._make_version_row(scene, definition, version_no=version_no, operator=operator)
            session.add(version)
            self._add_audit(session, "SCENE", scene.id, "UPDATE_DRAFT", operator, before, definition.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(scene)
            await session.refresh(version)
            return self._version(scene, version)

    async def get_scene_definition(self, scene_code: str) -> SceneDefinition:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            version = await self._require_latest_version(session, scene.id)
            return self._definition_from_rows(scene, version)

    async def publish_scene(self, scene_code: str, validation_result: ValidationResult, *, operator: str | None = None) -> SceneVersion:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            version = await self._require_latest_version(session, scene.id)
            if version.version_status == VersionStatus.PUBLISHED.value:
                return self._version(scene, version)
            before = self._scene_payload(scene)
            now = _now()
            version.version_status = VersionStatus.PUBLISHED.value
            version.validation_result_json = _dumps(validation_result.model_dump(mode="json"))
            version.published_by = operator
            version.published_at = now
            scene.status = SceneStatus.PUBLISHED.value
            scene.current_version_no = version.version_no
            scene.updated_by = operator
            scene.updated_at = now
            self._add_audit(session, "SCENE", scene.id, "PUBLISH", operator, before, {"sceneCode": scene_code, "versionNo": version.version_no})
            await self._commit(session)
            await session.refresh(scene)
            await session.refresh(version)
            return self._version(scene, version)

    async def disable_scene(self, scene_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            before = self._scene_payload(scene)
            scene.status = SceneStatus.DISABLED.value
            scene.updated_by = operator
            scene.updated_at = _now()
            self._add_audit(session, "SCENE", scene.id, "DISABLE", operator, before, self._scene_payload(scene))
            await self._commit(session)
            return True

    async def delete_scene(self, scene_code: str, *, operator: str | None = None) -> bool:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            before = self._scene_payload(scene)
            stmt_versions = select(DataFactorySceneVersionRow).where(DataFactorySceneVersionRow.scene_id == scene.id)
            versions = (await session.execute(stmt_versions)).scalars().all()
            for v in versions:
                await session.delete(v)
            await session.delete(scene)
            self._add_audit(session, "SCENE", scene.id, "DELETE", operator, before, None)
            await self._commit(session)
            return True

    async def copy_scene(self, scene_code: str, target_scene_code: str, *, operator: str | None = None) -> SceneVersion:
        async with self._sf() as session:
            source_scene = await self._require_scene_row(session, scene_code)
            source_version = await self._require_latest_version(session, source_scene.id)
            existing = await self._get_scene_row(session, target_scene_code)
            if existing is not None:
                raise SceneConflictError(f"target sceneCode already exists: {target_scene_code}")
            definition = self._definition_from_rows(source_scene, source_version)
            definition.sceneCode = target_scene_code
            definition.sceneName = f"Copy of {definition.sceneName}"
            now = _now()
            new_scene = DataFactorySceneRow(
                id=_new_id(), scene_code=target_scene_code, scene_name=definition.sceneName,
                scene_remark=definition.sceneRemark, scene_type=definition.sceneType,
                status=SceneStatus.DRAFT.value, current_version_no=None,
                created_by=operator, updated_by=operator, created_at=now, updated_at=now,
            )
            session.add(new_scene)
            new_version = self._make_version_row(new_scene, definition, version_no=1, operator=operator)
            session.add(new_version)
            self._add_audit(session, "SCENE", new_scene.id, "COPY_FROM", operator, {"source": scene_code}, definition.model_dump(mode="json"))
            await self._commit(session)
            await session.refresh(new_scene)
            await session.refresh(new_version)
            return self._version(new_scene, new_version)

    async def list_scene_versions(self, scene_code: str) -> list[SceneVersion]:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            stmt = (
                select(DataFactorySceneVersionRow)
                .where(DataFactorySceneVersionRow.scene_id == scene.id)
                .order_by(DataFactorySceneVersionRow.version_no.desc())
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [self._version(scene, row) for row in rows]

    async def get_scene_version(self, scene_code: str, version_no: int) -> SceneVersion:
        async with self._sf() as session:
            scene = await self._require_scene_row(session, scene_code)
            stmt = select(DataFactorySceneVersionRow).where(
                DataFactorySceneVersionRow.scene_id == scene.id,
                DataFactorySceneVersionRow.version_no == version_no,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise SceneNotFoundError(f"scene version not found: {scene_code}@{version_no}")
            return self._version(scene, row)

    # ========================= 内部辅助 =========================

    async def _commit(self, session: AsyncSession) -> None:
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise SceneConflictError("unique constraint violation") from exc

    async def _get_scene_row(self, session: AsyncSession, scene_code: str) -> DataFactorySceneRow | None:
        stmt = select(DataFactorySceneRow).where(DataFactorySceneRow.scene_code == scene_code)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _require_scene_row(self, session: AsyncSession, scene_code: str) -> DataFactorySceneRow:
        row = await self._get_scene_row(session, scene_code)
        if row is None:
            raise SceneNotFoundError(f"scene not found: {scene_code}")
        return row

    async def _next_version_no(self, session: AsyncSession, scene_id: str) -> int:
        stmt = select(func.coalesce(func.max(DataFactorySceneVersionRow.version_no), 0)).where(
            DataFactorySceneVersionRow.scene_id == scene_id
        )
        return int((await session.execute(stmt)).scalar_one()) + 1

    async def _require_latest_version(self, session: AsyncSession, scene_id: str) -> DataFactorySceneVersionRow:
        stmt = (
            select(DataFactorySceneVersionRow)
            .where(DataFactorySceneVersionRow.scene_id == scene_id)
            .order_by(DataFactorySceneVersionRow.version_no.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise SceneNotFoundError("scene version not found")
        return row

    @staticmethod
    def _make_version_row(scene: DataFactorySceneRow, definition: SceneDefinition, *, version_no: int, operator: str | None) -> DataFactorySceneVersionRow:
        return DataFactorySceneVersionRow(
            id=_new_id(), scene_id=scene.id, scene_code=scene.scene_code,
            version_no=version_no, version_status=VersionStatus.DRAFT.value,
            environment_field=definition.environmentField,
            input_schema_json=_dumps([f.model_dump(mode="json") for f in definition.inputSchema]),
            steps_json=_dumps([s.model_dump(mode="json") for s in definition.steps]),
            result_mapping_json=_dumps(definition.resultMapping),
            batch_config_json=_dumps(definition.batchConfig.model_dump(mode="json")),
            validation_result_json=None,
            created_by=operator, created_at=_now(),
        )

    @staticmethod
    def _definition_from_rows(scene: DataFactorySceneRow, version: DataFactorySceneVersionRow) -> SceneDefinition:
        return SceneDefinition(
            sceneCode=scene.scene_code, sceneName=scene.scene_name,
            sceneRemark=scene.scene_remark, sceneType=scene.scene_type,
            environmentField=version.environment_field,
            inputSchema=_loads(version.input_schema_json, []),
            steps=_loads(version.steps_json, []),
            resultMapping=_loads(version.result_mapping_json, {}),
            batchConfig=_loads(version.batch_config_json, {}),
            status=scene.status,
        )

    @staticmethod
    def _summary(row: DataFactorySceneRow) -> SceneSummary:
        return SceneSummary(
            id=row.id, sceneCode=row.scene_code, sceneName=row.scene_name,
            sceneRemark=row.scene_remark, sceneType=row.scene_type,
            status=row.status, currentVersionNo=row.current_version_no,
            createdBy=row.created_by, updatedBy=row.updated_by,
            createdAt=row.created_at, updatedAt=row.updated_at,
        )

    @staticmethod
    def _version(scene: DataFactorySceneRow, version: DataFactorySceneVersionRow) -> SceneVersion:
        return SceneVersion(
            id=version.id, sceneCode=version.scene_code,
            versionNo=version.version_no, versionStatus=version.version_status,
            definition=SceneRepository._definition_from_rows(scene, version),
            validationResult=_loads(version.validation_result_json, None),
            createdBy=version.created_by, createdAt=version.created_at,
            publishedBy=version.published_by, publishedAt=version.published_at,
        )

    @staticmethod
    def _scene_payload(row: DataFactorySceneRow) -> dict[str, Any]:
        return {
            "sceneCode": row.scene_code, "sceneName": row.scene_name,
            "sceneRemark": row.scene_remark, "sceneType": row.scene_type,
            "status": row.status, "currentVersionNo": row.current_version_no,
        }

    @staticmethod
    def _add_audit(session: AsyncSession, target_type: str, target_id: str, action: str, operator: str | None, before: Any, after: Any) -> None:
        session.add(DataFactoryConfigAuditRow(
            id=_new_id(), target_type=target_type, target_id=target_id,
            action=action, operator=operator,
            before_json=_dumps(before) if before is not None else None,
            after_json=_dumps(after) if after is not None else None,
            created_at=_now(),
        ))
