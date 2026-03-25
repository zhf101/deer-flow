from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from xagent.web.models.dm_asset import DMHTTPAsset, DMSQLAsset, DMSQLAssetVersion
from xagent.web.models.user import User

from ..contracts import ExecutorInput
from ..executors.http import HTTPExecutor
from ..governance import GovernanceService


@dataclass
class AssetService:
    """datamakepool 资产服务。

    本阶段实现资产域前三批最小闭环，并开始承接探索态资产引用：

    - HTTP 资产列表 / 创建
    - HTTP 资产详情
    - HTTP 资产测试
    - SQL 资产列表 / 创建
    - SQL 资产版本列表 / 详情
    - SQL 资产版本测试
    - SQL 资产版本送审 / 审批切换生效版本
    - 结构化 `asset_ref` 解析与资产快照投影

    当前明确不扩展：
    - HTTP 资产编辑 / 删除
    - SQL 资产版本复制 / 编辑
    - mutation SQL 测试执行
    """

    db: Session

    def normalize_asset_reference(
        self,
        asset_ref: Any,
        *,
        default_asset_type: str | None = None,
    ) -> dict[str, Any] | None:
        """把前台或草稿里的资产引用统一转成结构化对象。

        当前兼容三种输入：
        - 字典：`{"asset_type": "http", "asset_id": 1}`
        - 简写字符串：`"http:1"` / `"sql:2:5"`
        - 纯数字字符串：结合 `default_asset_type` 推断类型

        如果给到的是历史遗留的自由字符串，这里返回 `None`，上层继续沿用旧逻辑，
        避免这批联动把旧草稿直接打断。
        """

        if asset_ref is None:
            return None

        if isinstance(asset_ref, dict):
            raw_asset_type = asset_ref.get("asset_type") or asset_ref.get("type") or default_asset_type
            raw_asset_id = (
                asset_ref.get("asset_id")
                or asset_ref.get("id")
                or asset_ref.get("http_asset_id")
                or asset_ref.get("sql_asset_id")
            )
            raw_version_id = asset_ref.get("version_id") or asset_ref.get("sql_asset_version_id")
            return self._build_normalized_asset_reference(
                asset_type=raw_asset_type,
                asset_id=raw_asset_id,
                version_id=raw_version_id,
            )

        if isinstance(asset_ref, str):
            normalized = asset_ref.strip()
            if not normalized:
                return None

            parts = [part.strip() for part in normalized.split(":") if part.strip()]
            if len(parts) == 1 and parts[0].isdigit() and default_asset_type:
                return self._build_normalized_asset_reference(
                    asset_type=default_asset_type,
                    asset_id=parts[0],
                    version_id=None,
                )
            if len(parts) == 2 and parts[0] in {"http", "sql"} and parts[1].isdigit():
                return self._build_normalized_asset_reference(
                    asset_type=parts[0],
                    asset_id=parts[1],
                    version_id=None,
                )
            if (
                len(parts) == 3
                and parts[0] == "sql"
                and parts[1].isdigit()
                and parts[2].isdigit()
            ):
                return self._build_normalized_asset_reference(
                    asset_type="sql",
                    asset_id=parts[1],
                    version_id=parts[2],
                )
            return None

        raise ValueError("Unsupported asset_ref payload")

    def resolve_http_asset_binding(
        self,
        asset_ref: Any,
        *,
        user: User | None = None,
    ) -> dict[str, Any]:
        """把 HTTP 资产引用解析成 resolver 可消费的资产定义与快照引用。"""

        normalized = self.normalize_asset_reference(asset_ref, default_asset_type="http")
        if normalized is None:
            raise ValueError("HTTP asset_ref must contain a structured asset id")
        if normalized["asset_type"] != "http":
            raise ValueError("HTTP step can only bind http asset_ref")

        asset = self._get_http_asset(int(normalized["asset_id"]))
        if user is not None:
            GovernanceService(db=self.db).assert_http_asset_access(asset, user)

        resolved_ref = {
            "asset_type": "http",
            "asset_id": int(asset.id),
        }
        return {
            "asset_ref": resolved_ref,
            "asset_definition": {
                "asset_type": "http",
                "asset_id": int(asset.id),
                "name": asset.name,
                "system_short": asset.system_short,
                "method": asset.method,
                "base_url": asset.base_url,
                "path_template": asset.path_template,
                "query_template": asset.query_template or {},
                "headers_template": asset.headers_template or {},
                "body_template": asset.body_template,
                "request_schema": asset.request_schema or {},
                "response_extraction_rules": asset.response_extraction_rules or {},
                "timeout_seconds": int(asset.timeout_seconds),
                "enabled": bool(asset.enabled),
                "asset_ref": resolved_ref,
            },
            "asset_version_snapshot_ref": {
                "asset_type": "http",
                "asset_id": int(asset.id),
                "system_short": asset.system_short,
                "name": asset.name,
                "snapshot_kind": "http_asset",
            },
        }

    def resolve_sql_asset_binding(
        self,
        asset_ref: Any,
        *,
        user: User | None = None,
    ) -> dict[str, Any]:
        """把 SQL 资产引用解析成逻辑资产 + 锁定版本快照。"""

        normalized = self.normalize_asset_reference(asset_ref, default_asset_type="sql")
        if normalized is None:
            raise ValueError("SQL asset_ref must contain a structured asset id")
        if normalized["asset_type"] != "sql":
            raise ValueError("SQL step can only bind sql asset_ref")

        asset = self._get_sql_asset(int(normalized["asset_id"]))
        if user is not None:
            GovernanceService(db=self.db).assert_sql_asset_access(asset, user)

        version_id = normalized.get("version_id")
        if version_id is None:
            if asset.current_active_version_id is None:
                raise ValueError(
                    f"SQL asset {asset.id} has no active version; specify version_id explicitly"
                )
            version = self._get_sql_asset_version(int(asset.current_active_version_id))
        else:
            version = self._get_sql_asset_version(int(version_id))
            if int(version.sql_asset_id) != int(asset.id):
                raise ValueError(
                    f"SQL asset version {version.id} does not belong to asset {asset.id}"
                )

        if user is not None:
            GovernanceService(db=self.db).assert_sql_asset_version_access(version, user)

        resolved_ref = {
            "asset_type": "sql",
            "asset_id": int(asset.id),
            "version_id": int(version.id),
        }
        return {
            "asset_ref": resolved_ref,
            "asset_definition": {
                "asset_type": "sql",
                "asset_id": int(asset.id),
                "version_id": int(version.id),
                "version_no": int(version.version_no),
                "system_short": asset.system_short,
                "name": asset.name,
                "whitelist": [str(item) for item in (version.whitelist or [])],
                "blacklist": [str(item) for item in (version.blacklist or [])],
                "mutation_enabled": bool(version.mutation_enabled),
                "status": version.status,
                "asset_ref": resolved_ref,
            },
            "asset_version_snapshot_ref": {
                "asset_type": "sql",
                "asset_id": int(asset.id),
                "version_id": int(version.id),
                "version_no": int(version.version_no),
                "system_short": asset.system_short,
                "name": asset.name,
                "status": version.status,
                "mutation_enabled": bool(version.mutation_enabled),
                "snapshot_kind": "sql_asset_version",
            },
        }

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

    def test_http_asset(
        self,
        asset_id: int,
        user: User,
        *,
        query_params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        body: Any = None,
        response_extraction_rules: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行一次 HTTP 资产测试调用。"""

        asset = self._get_http_asset(asset_id)
        GovernanceService(db=self.db).assert_http_asset_access(asset, user)

        plan = {
            "method": asset.method,
            "base_url": asset.base_url,
            "path_template": asset.path_template,
            "query_template": (
                query_params if query_params is not None else (asset.query_template or {})
            ),
            "headers_template": self._merge_dicts(asset.headers_template, headers),
            "body_template": body if body is not None else asset.body_template,
            "output_mapping": (
                response_extraction_rules
                if response_extraction_rules
                else (asset.response_extraction_rules or {})
            ),
            "timeout_seconds": int(asset.timeout_seconds),
        }

        output = HTTPExecutor().execute(
            ExecutorInput(
                resolved_execution_plan=plan,
                runtime_values={},
            )
        )
        raw_payload = output.raw_payload or {}
        return {
            "asset_id": asset.id,
            "execution_status": output.execution_status,
            "request_snapshot": raw_payload.get("request_snapshot") or {},
            "response_snapshot": raw_payload.get("response_snapshot"),
            "extracted_outputs": output.extracted_outputs or {},
            "execution_metrics": output.execution_metrics or {},
            "error_info": output.error_info,
        }

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

    def test_sql_asset_version(
        self,
        version_id: int,
        user: User,
        *,
        test_mode: str,
        sql: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """执行 SQL 资产版本的连接测试或查询测试。

        当前第一版只支持：
        - `connection`: 测试连接是否可建立
        - `sql`: 仅支持查询类 SQL 的最小测试
        """

        version = self._get_sql_asset_version(version_id)
        GovernanceService(db=self.db).assert_sql_asset_version_access(version, user)
        asset = version.asset
        if asset is None:
            raise ValueError(f"SQL asset {version.sql_asset_id} not found")

        database_url = self._extract_database_url(version.connection_config or {})
        engine = self._create_sql_test_engine(database_url)

        try:
            if test_mode == "connection":
                connection_summary = self._test_sql_connection(engine, database_url)
                return {
                    "asset_id": asset.id,
                    "version_id": version.id,
                    "test_mode": test_mode,
                    "execution_status": "succeeded",
                    "connection_summary": connection_summary,
                    "sql_snapshot": None,
                    "result_preview": None,
                    "execution_metrics": {},
                    "error_info": None,
                }

            if test_mode != "sql":
                raise ValueError(f"Unsupported sql asset test mode {test_mode!r}")

            normalized_sql = self._require_text(sql, "sql")
            if self._is_mutation_sql(normalized_sql):
                if not version.mutation_enabled:
                    raise ValueError(
                        "Current SQL asset version does not allow mutation SQL test execution"
                    )
                raise ValueError(
                    "SQL asset test endpoint currently only supports query statements"
                )

            execution = self._test_sql_query(
                engine=engine,
                sql=normalized_sql,
                params=params or {},
            )
            return {
                "asset_id": asset.id,
                "version_id": version.id,
                "test_mode": test_mode,
                "execution_status": execution["execution_status"],
                "connection_summary": {
                    "database_type": self._infer_database_type(database_url),
                },
                "sql_snapshot": execution["sql_snapshot"],
                "result_preview": execution["result_preview"],
                "execution_metrics": execution["execution_metrics"],
                "error_info": execution["error_info"],
            }
        finally:
            engine.dispose()

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

    def _merge_dicts(
        self,
        base: dict[str, Any] | None,
        override: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """合并两个字典，后者覆盖前者。"""

        merged = dict(base or {})
        merged.update(dict(override or {}))
        return merged

    def _extract_database_url(self, connection_config: dict[str, Any]) -> str:
        """从连接配置中提取数据库 URL。"""

        for key in ("url", "database_url", "uri"):
            value = connection_config.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise ValueError("SQL asset version connection_config is missing database url")

    def _create_sql_test_engine(self, database_url: str) -> Engine:
        """为 SQL 资产测试创建独立 engine。"""

        return create_engine(database_url, pool_pre_ping=True)

    def _test_sql_connection(self, engine: Engine, database_url: str) -> dict[str, Any]:
        """执行最小数据库连接测试。"""

        table_count: int | None = None
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            try:
                table_count = len(inspect(connection).get_table_names())
            except Exception:
                table_count = None

        return {
            "database_type": self._infer_database_type(database_url),
            "table_count": table_count,
        }

    def _test_sql_query(
        self,
        engine: Engine,
        sql: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """执行查询类 SQL 的最小测试。"""

        sql_snapshot = {
            "sql": sql,
            "params": params,
        }
        try:
            with engine.connect() as connection:
                result = connection.execute(text(sql), params)
                rows: list[dict[str, Any]] = []
                if result.returns_rows:
                    rows = [dict(row._mapping) for row in result.fetchmany(20)]
                rowcount = int(result.rowcount or 0)
        except SQLAlchemyError as exc:
            return {
                "execution_status": "failed",
                "sql_snapshot": sql_snapshot,
                "result_preview": None,
                "execution_metrics": {},
                "error_info": {"message": str(exc), "type": exc.__class__.__name__},
            }

        return {
            "execution_status": "succeeded",
            "sql_snapshot": sql_snapshot,
            "result_preview": {
                "rows": rows,
                "rowcount": rowcount,
            },
            "execution_metrics": {
                "preview_rows": len(rows),
                "rowcount": rowcount,
            },
            "error_info": None,
        }

    def _infer_database_type(self, database_url: str) -> str:
        """从 URL 推断数据库类型。"""

        normalized = str(database_url).strip().lower()
        if normalized.startswith("sqlite"):
            return "sqlite"
        if normalized.startswith("postgresql"):
            return "postgresql"
        if normalized.startswith("mysql"):
            return "mysql"
        if normalized.startswith("mssql") or normalized.startswith("sqlserver"):
            return "sqlserver"
        if normalized.startswith("oracle"):
            return "oracle"
        return "unknown"

    def _is_mutation_sql(self, sql: str) -> bool:
        """判断 SQL 是否属于 mutation 类语句。"""

        first_keyword = sql.split(None, 1)[0].lower() if sql else ""
        return first_keyword in {
            "insert",
            "update",
            "delete",
            "merge",
            "alter",
            "drop",
            "truncate",
            "create",
            "replace",
        }

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _build_normalized_asset_reference(
        self,
        *,
        asset_type: Any,
        asset_id: Any,
        version_id: Any,
    ) -> dict[str, Any]:
        """把零散字段组装成统一资产引用对象。"""

        normalized_asset_type = str(asset_type or "").strip().lower()
        if normalized_asset_type not in {"http", "sql"}:
            raise ValueError("asset_ref.asset_type must be 'http' or 'sql'")

        normalized_asset_id = int(asset_id)
        if normalized_asset_id <= 0:
            raise ValueError("asset_ref.asset_id must be positive integer")

        normalized: dict[str, Any] = {
            "asset_type": normalized_asset_type,
            "asset_id": normalized_asset_id,
        }
        if version_id is not None:
            normalized_version_id = int(version_id)
            if normalized_version_id <= 0:
                raise ValueError("asset_ref.version_id must be positive integer")
            normalized["version_id"] = normalized_version_id
        return normalized
