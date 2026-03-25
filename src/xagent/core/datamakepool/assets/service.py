from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from xagent.web.models.dm_asset import DMHTTPAsset, DMSQLAsset, DMSQLAssetVersion
from xagent.web.models.user import User

from ..governance import GovernanceService


@dataclass
class AssetService:
    """datamakepool 资产服务。

    本阶段实现资产域前两批最小闭环：

    - HTTP 资产列表 / 创建
    - HTTP 资产详情
    - SQL 资产列表 / 创建
    - SQL 资产版本列表 / 详情
    - SQL 资产版本送审 / 审批切换生效版本

    当前明确不扩展：
    - HTTP 资产编辑 / 删除
    - SQL 资产版本复制 / 编辑
    - 真实连通测试与测试 SQL
    """

    db: Session

    def list_http_assets(self, user: User) -> list[dict[str, Any]]:
        """列出当前用户可见的 HTTP 资产。"""

        assets = self.db.query(DMHTTPAsset).order_by(DMHTTPAsset.created_at.desc()).all()
        governance_service = GovernanceService(db=self.db)
        visible_assets: list[DMHTTPAsset] = []
        for asset in assets:
            try:
                governance_service.assert_http_asset_access(asset, user)
                visible_assets.append(asset)
            except PermissionError:
                continue
        return [self._serialize_http_asset(asset) for asset in visible_assets]

    def get_http_asset(self, asset_id: int, user: User) -> dict[str, Any]:
        """读取单个 HTTP 资产详情。"""

        asset = self._get_http_asset(asset_id)
        GovernanceService(db=self.db).assert_http_asset_access(asset, user)
        return self._serialize_http_asset_detail(asset)

    def create_http_asset(
        self,
        user: User,
        *,
        name: str,
        description: str | None,
        system_short: str,
        base_url: str,
        method: str,
        path_template: str,
        query_template: dict[str, Any] | None,
        headers_template: dict[str, Any] | None,
        body_template: dict[str, Any] | None,
        request_schema: dict[str, Any] | None,
        auth_type: str | None,
        auth_config_ciphertext: str | None,
        response_extraction_rules: dict[str, Any] | None,
        timeout_seconds: int,
        max_response_bytes: int,
        enabled: bool,
    ) -> dict[str, Any]:
        """创建一个 HTTP 资产。

        当前不走审核流，因为设计文档里 HTTP 资产是单层对象。
        但会在这里统一做最小字段标准化，保证后续 resolver 可稳定引用。
        """

        asset = DMHTTPAsset(
            name=self._require_text(name, "name"),
            description=self._normalize_text(description),
            system_short=self._require_text(system_short, "system_short"),
            base_url=self._require_text(base_url, "base_url"),
            method=self._normalize_http_method(method),
            path_template=self._require_text(path_template, "path_template"),
            query_template=query_template or {},
            headers_template=headers_template or {},
            body_template=body_template or {},
            request_schema=request_schema or {},
            auth_type=self._normalize_text(auth_type),
            auth_config_ciphertext=self._normalize_text(auth_config_ciphertext),
            response_extraction_rules=response_extraction_rules or {},
            timeout_seconds=self._normalize_positive_int(timeout_seconds, "timeout_seconds"),
            max_response_bytes=self._normalize_positive_int(
                max_response_bytes, "max_response_bytes"
            ),
            enabled=bool(enabled),
            owner_user_id=int(user.id),
        )
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return self._serialize_http_asset(asset)

    def list_sql_assets(self, user: User) -> list[dict[str, Any]]:
        """列出当前用户可见的 SQL 资产逻辑对象。"""

        assets = self.db.query(DMSQLAsset).order_by(DMSQLAsset.created_at.desc()).all()
        governance_service = GovernanceService(db=self.db)
        visible_assets: list[DMSQLAsset] = []
        for asset in assets:
            try:
                governance_service.assert_sql_asset_access(asset, user)
                visible_assets.append(asset)
            except PermissionError:
                continue
        return [self._serialize_sql_asset(asset) for asset in visible_assets]

    def list_sql_asset_versions(self, asset_id: int, user: User) -> list[dict[str, Any]]:
        """列出某个 SQL 资产的全部版本。"""

        asset = self._get_sql_asset(asset_id)
        GovernanceService(db=self.db).assert_sql_asset_access(asset, user)
        versions = sorted(
            asset.versions,
            key=lambda item: (int(item.version_no), int(item.id)),
            reverse=True,
        )
        return [self._serialize_sql_asset_version_summary(version) for version in versions]

    def get_sql_asset_version_detail(self, version_id: int, user: User) -> dict[str, Any]:
        """读取单个 SQL 资产版本详情。"""

        version = self._get_sql_asset_version(version_id)
        GovernanceService(db=self.db).assert_sql_asset_version_access(version, user)
        return self._serialize_sql_asset_version_detail(version)

    def create_sql_asset(
        self,
        user: User,
        *,
        name: str,
        description: str | None,
        system_short: str,
        connection_config: dict[str, Any] | None,
        whitelist: list[str] | None,
        blacklist: list[str] | None,
        mutation_enabled: bool,
    ) -> dict[str, Any]:
        """创建 SQL 资产逻辑对象及其初始草稿版本。"""

        try:
            asset = DMSQLAsset(
                name=self._require_text(name, "name"),
                description=self._normalize_text(description),
                system_short=self._require_text(system_short, "system_short"),
                owner_user_id=int(user.id),
            )
            self.db.add(asset)
            self.db.flush()

            version = DMSQLAssetVersion(
                sql_asset_id=int(asset.id),
                version_no=1,
                status="draft",
                connection_config=connection_config or {},
                whitelist=self._normalize_string_list(whitelist),
                blacklist=self._normalize_string_list(blacklist),
                mutation_enabled=bool(mutation_enabled),
                review_comment=None,
                created_by=int(user.id),
            )
            self.db.add(version)
            self.db.commit()
            self.db.refresh(asset)
            self.db.refresh(version)

            return {
                "asset_id": int(asset.id),
                "version_id": int(version.id),
                "version_no": int(version.version_no),
                "status": version.status,
            }
        except Exception:
            self.db.rollback()
            raise

    def submit_sql_asset_review(self, version_id: int, user: User) -> dict[str, Any]:
        """把 SQL 资产版本推进到待审核状态。"""

        version = self._get_sql_asset_version(version_id)
        GovernanceService(db=self.db).assert_can_submit_sql_asset_review(version, user)
        version.status = "pending_review"
        version.review_comment = None
        self.db.commit()
        return self._serialize_sql_asset_review(version)

    def approve_sql_asset_version(self, version_id: int, user: User) -> dict[str, Any]:
        """审批通过 SQL 资产版本，并切到当前生效版本。"""

        version = self._get_sql_asset_version(version_id)
        asset = version.asset
        if asset is None:
            raise ValueError(f"SQL asset {version.sql_asset_id} not found")

        GovernanceService(db=self.db).assert_can_approve_sql_asset_version(version, user)
        try:
            version.status = "approved"
            version.reviewed_by = int(user.id)
            version.reviewed_at = self._now()
            version.review_comment = "approved"
            asset.current_active_version_id = int(version.id)
            self.db.commit()
            return self._serialize_sql_asset_review(version)
        except Exception:
            self.db.rollback()
            raise

    def _get_sql_asset_version(self, version_id: int) -> DMSQLAssetVersion:
        """读取 SQL 资产版本对象。"""

        version = (
            self.db.query(DMSQLAssetVersion)
            .filter(DMSQLAssetVersion.id == version_id)
            .first()
        )
        if version is None:
            raise ValueError(f"SQL asset version {version_id} not found")
        return version

    def _get_http_asset(self, asset_id: int) -> DMHTTPAsset:
        """读取 HTTP 资产对象。"""

        asset = self.db.query(DMHTTPAsset).filter(DMHTTPAsset.id == asset_id).first()
        if asset is None:
            raise ValueError(f"HTTP asset {asset_id} not found")
        return asset

    def _get_sql_asset(self, asset_id: int) -> DMSQLAsset:
        """读取 SQL 资产逻辑对象。"""

        asset = self.db.query(DMSQLAsset).filter(DMSQLAsset.id == asset_id).first()
        if asset is None:
            raise ValueError(f"SQL asset {asset_id} not found")
        return asset

    def _serialize_http_asset(self, asset: DMHTTPAsset) -> dict[str, Any]:
        """把 HTTP 资产对象压平成 API 列表 / 创建响应结构。"""

        return {
            "asset_id": asset.id,
            "name": asset.name,
            "description": asset.description,
            "system_short": asset.system_short,
            "method": asset.method,
            "base_url": asset.base_url,
            "path_template": asset.path_template,
            "enabled": asset.enabled,
            "owner_user_id": asset.owner_user_id,
            "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
        }

    def _serialize_http_asset_detail(self, asset: DMHTTPAsset) -> dict[str, Any]:
        """把 HTTP 资产对象压平成详情响应。

        这里不直接回传 `auth_config_ciphertext`，避免前台详情接口泄露敏感密文。
        当前只返回“是否已配置”这一最小信息。
        """

        return {
            **self._serialize_http_asset(asset),
            "query_template": asset.query_template or {},
            "headers_template": asset.headers_template or {},
            "body_template": asset.body_template or {},
            "request_schema": asset.request_schema or {},
            "auth_type": asset.auth_type,
            "auth_config_configured": bool(asset.auth_config_ciphertext),
            "response_extraction_rules": asset.response_extraction_rules or {},
            "timeout_seconds": int(asset.timeout_seconds),
            "max_response_bytes": int(asset.max_response_bytes),
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
        }

    def _serialize_sql_asset(self, asset: DMSQLAsset) -> dict[str, Any]:
        """把 SQL 资产逻辑对象压平成 API 结构。"""

        latest_version = self._pick_latest_sql_asset_version(asset)
        return {
            "asset_id": asset.id,
            "name": asset.name,
            "description": asset.description,
            "system_short": asset.system_short,
            "owner_user_id": asset.owner_user_id,
            "current_active_version_id": asset.current_active_version_id,
            "versions_count": len(asset.versions),
            "latest_version_id": latest_version.id if latest_version is not None else None,
            "latest_version_no": (
                int(latest_version.version_no) if latest_version is not None else None
            ),
            "latest_version_status": latest_version.status if latest_version is not None else None,
            "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
        }

    def _serialize_sql_asset_review(self, version: DMSQLAssetVersion) -> dict[str, Any]:
        """把 SQL 资产版本审核动作压平成 API 响应。"""

        return {
            "asset_id": version.sql_asset_id,
            "version_id": version.id,
            "version_no": version.version_no,
            "status": version.status,
            "reviewed_by": version.reviewed_by,
            "reviewed_at": version.reviewed_at.isoformat() if version.reviewed_at else None,
        }

    def _serialize_sql_asset_version_summary(
        self,
        version: DMSQLAssetVersion,
    ) -> dict[str, Any]:
        """把 SQL 资产版本对象压平成列表项。"""

        return {
            "version_id": version.id,
            "asset_id": version.sql_asset_id,
            "version_no": version.version_no,
            "status": version.status,
            "mutation_enabled": bool(version.mutation_enabled),
            "created_by": version.created_by,
            "reviewed_by": version.reviewed_by,
            "review_comment": version.review_comment,
            "reviewed_at": version.reviewed_at.isoformat() if version.reviewed_at else None,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }

    def _serialize_sql_asset_version_detail(
        self,
        version: DMSQLAssetVersion,
    ) -> dict[str, Any]:
        """把 SQL 资产版本对象压平成详情响应。

        SQL 版本详情需要为管理台提供连接与治理配置，但要尽量避免把明显敏感字段
        原样返回，因此这里只做最小脱敏。
        """

        asset = version.asset
        if asset is None:
            raise ValueError(f"SQL asset {version.sql_asset_id} not found")

        return {
            **self._serialize_sql_asset_version_summary(version),
            "system_short": asset.system_short,
            "connection_config": self._mask_sensitive_dict(version.connection_config or {}),
            "whitelist": [str(item) for item in (version.whitelist or [])],
            "blacklist": [str(item) for item in (version.blacklist or [])],
            "is_active_version": asset.current_active_version_id == version.id,
        }

    def _pick_latest_sql_asset_version(
        self,
        asset: DMSQLAsset,
    ) -> DMSQLAssetVersion | None:
        """返回 SQL 资产的最新版本。"""

        if not asset.versions:
            return None
        return max(asset.versions, key=lambda item: (int(item.version_no), int(item.id)))

    def _normalize_http_method(self, method: str) -> str:
        """统一 HTTP method 格式并做最小校验。"""

        normalized = self._require_text(method, "method").upper()
        allowed_methods = {"GET", "POST", "PUT", "PATCH", "DELETE"}
        if normalized not in allowed_methods:
            raise ValueError(f"Unsupported HTTP method {normalized!r}")
        return normalized

    def _normalize_positive_int(self, value: int, field_name: str) -> int:
        """把数值字段约束为正整数。"""

        normalized = int(value)
        if normalized <= 0:
            raise ValueError(f"Field {field_name!r} requires positive integer")
        return normalized

    def _normalize_string_list(self, values: list[str] | None) -> list[str]:
        """统一清洗字符串列表。"""

        if not values:
            return []
        normalized: list[str] = []
        for value in values:
            item = self._normalize_text(value)
            if item:
                normalized.append(item)
        return normalized

    def _require_text(self, value: str | None, field_name: str) -> str:
        """要求输入字段必须是非空字符串。"""

        normalized = self._normalize_text(value)
        if not normalized:
            raise ValueError(f"Field {field_name!r} is required")
        return normalized

    def _normalize_text(self, value: str | None) -> str | None:
        """做最小文本归一化。"""

        if value is None:
            return None
        normalized = " ".join(str(value).strip().split())
        return normalized or None

    def _mask_sensitive_dict(self, payload: dict[str, Any]) -> dict[str, Any]:
        """对连接配置中的明显敏感字段做最小脱敏。"""

        masked: dict[str, Any] = {}
        sensitive_tokens = {"password", "secret", "token", "key", "credential"}
        for key, value in payload.items():
            lowered_key = str(key).lower()
            if any(token in lowered_key for token in sensitive_tokens):
                masked[str(key)] = "***"
                continue
            masked[str(key)] = value
        return masked

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
