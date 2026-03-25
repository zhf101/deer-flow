from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session

from xagent.web.models.admin_system_scope import AdminSystemScope
from xagent.web.models.dm_asset import DMHTTPAsset, DMSQLAsset, DMSQLAssetVersion
from xagent.web.models.dm_audit import DMAuditRecord
from xagent.web.models.dm_flow_draft import DMFlowDraft
from xagent.web.models.dm_run import DMRun, DMRunStep
from xagent.web.models.dm_template import DMTemplate, DMTemplateRevision
from xagent.web.models.user import User

from ..preflight import PreflightService


@dataclass
class GovernanceService:
    """datamakepool 治理服务。

    这一层统一承接三类治理能力：

    1. 预检阶段的治理口径复用
    2. SQL 风险/确认/执行的审计真相源落库
    3. 基于 `system_short` 的最小对象级访问边界

    当前实现只做 V1 第一阶段所需的最小闭环，不扩展到完整 RBAC。
    """

    db: Session

    def preflight_check(self, technical_graph: dict[str, Any]) -> dict[str, Any]:
        """执行面向治理视角的预检。"""
        return PreflightService().evaluate(technical_graph).model_dump()

    def get_scope_context(self, user: User) -> dict[str, Any]:
        """解析当前用户在 datamakepool 下的最小权限上下文。

        约定如下：

        - `is_admin=False`：普通用户，只能访问自己发起的 Run
        - `is_admin=True` 且没有 scope：视为 system_admin，可看全部 system_short
        - `is_admin=True` 且存在 scope：视为 domain_admin，只能看 scope 覆盖范围
        """

        scopes: list[str] = []
        if user.is_admin:
            scope_rows = (
                self.db.query(AdminSystemScope)
                .filter(AdminSystemScope.user_id == user.id)
                .order_by(AdminSystemScope.system_short.asc())
                .all()
            )
            scopes = [row.system_short for row in scope_rows if row.system_short]

        if not user.is_admin:
            role = "user"
        elif scopes:
            role = "domain_admin"
        else:
            role = "system_admin"

        return {
            "role": role,
            "is_admin": user.is_admin,
            "scopes": scopes,
        }

    def assert_run_access(self, run: DMRun, user: User) -> None:
        """校验当前用户是否可访问指定 Run。"""

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "system_admin":
            return

        if scope_context["role"] == "domain_admin":
            if run.initiator_user_id == user.id:
                return
            if run.system_short and run.system_short in scope_context["scopes"]:
                return
            raise PermissionError(
                f"User {user.id} has no datamakepool scope for system_short={run.system_short!r}"
            )

        if run.initiator_user_id != user.id:
            raise PermissionError(f"User {user.id} cannot access run {run.id}")

    def assert_flowdraft_access(self, flowdraft: DMFlowDraft, user: User) -> None:
        """校验当前用户是否可访问 FlowDraft。

        FlowDraft 目前还没有稳定的 `system_short` 归属字段，因此这一版采用更保守的策略：
        - system_admin 可看全部
        - 草稿创建者可看自己的草稿
        - task 所属用户可看挂在自己任务下的草稿
        - domain_admin 暂不因 admin scope 自动放开，避免在缺少稳定归属字段时越权
        """

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "system_admin":
            return

        if flowdraft.created_by == user.id:
            return

        if flowdraft.task is not None and flowdraft.task.user_id == user.id:
            return

        raise PermissionError(f"User {user.id} cannot access flowdraft {flowdraft.id}")

    def assert_audit_access(self, audit: DMAuditRecord, user: User) -> None:
        """校验当前用户是否可查看审计记录。

        审计数据属于治理视图。当前最小策略只开放给管理员：

        - system_admin：可看全部
        - domain_admin：仅可看 scope 覆盖的 system_short
        - 普通用户：不可看
        """

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "system_admin":
            return

        if scope_context["role"] == "domain_admin":
            if audit.system_short and audit.system_short in scope_context["scopes"]:
                return
            raise PermissionError(
                f"User {user.id} has no audit scope for system_short={audit.system_short!r}"
            )

        raise PermissionError(f"User {user.id} cannot access audit {audit.id}")

    def assert_template_access(self, template: DMTemplate, user: User) -> None:
        """校验当前用户是否可访问模板对象。"""

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "system_admin":
            return

        if template.owner_user_id == user.id:
            return

        if scope_context["role"] == "domain_admin":
            if template.system_short and template.system_short in scope_context["scopes"]:
                return
            raise PermissionError(
                f"User {user.id} has no template scope for system_short={template.system_short!r}"
            )

        raise PermissionError(f"User {user.id} cannot access template {template.id}")

    def assert_http_asset_access(self, asset: DMHTTPAsset, user: User) -> None:
        """校验当前用户是否可访问 HTTP 资产。"""

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "system_admin":
            return

        if asset.owner_user_id == user.id:
            return

        if scope_context["role"] == "domain_admin":
            if asset.system_short and asset.system_short in scope_context["scopes"]:
                return
            raise PermissionError(
                f"User {user.id} has no http asset scope for system_short={asset.system_short!r}"
            )

        raise PermissionError(f"User {user.id} cannot access http asset {asset.id}")

    def assert_sql_asset_access(self, asset: DMSQLAsset, user: User) -> None:
        """校验当前用户是否可访问 SQL 资产。"""

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "system_admin":
            return

        if asset.owner_user_id == user.id:
            return

        if scope_context["role"] == "domain_admin":
            if asset.system_short and asset.system_short in scope_context["scopes"]:
                return
            raise PermissionError(
                f"User {user.id} has no sql asset scope for system_short={asset.system_short!r}"
            )

        raise PermissionError(f"User {user.id} cannot access sql asset {asset.id}")

    def assert_sql_asset_version_access(self, version: DMSQLAssetVersion, user: User) -> None:
        """校验当前用户是否可访问 SQL 资产版本。"""

        asset = version.asset
        if asset is None:
            raise ValueError(f"SQL asset {version.sql_asset_id} not found")
        self.assert_sql_asset_access(asset, user)

    def assert_can_submit_sql_asset_review(
        self,
        version: DMSQLAssetVersion,
        user: User,
    ) -> None:
        """校验当前用户是否可提交 SQL 资产版本送审。"""

        self.assert_sql_asset_version_access(version, user)
        if version.status != "draft":
            raise ValueError(
                f"SQL asset version {version.id} status is {version.status!r}; only draft can submit review"
            )

    def assert_can_approve_sql_asset_version(
        self,
        version: DMSQLAssetVersion,
        user: User,
    ) -> None:
        """校验当前用户是否可审批 SQL 资产版本。"""

        asset = version.asset
        if asset is None:
            raise ValueError(f"SQL asset {version.sql_asset_id} not found")

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "user":
            raise PermissionError(
                f"User {user.id} is not allowed to approve sql asset version {version.id}"
            )
        if scope_context["role"] == "domain_admin":
            if not asset.system_short or asset.system_short not in scope_context["scopes"]:
                raise PermissionError(
                    f"User {user.id} has no approval scope for system_short={asset.system_short!r}"
                )

        if version.status != "pending_review":
            raise ValueError(
                f"SQL asset version {version.id} status is {version.status!r}; only pending_review can approve"
            )

        if version.created_by == user.id:
            raise PermissionError(
                f"User {user.id} cannot approve sql asset version {version.id} created by self"
            )

    def assert_template_revision_access(self, revision: DMTemplateRevision, user: User) -> None:
        """校验当前用户是否可访问模板版本。"""

        template = revision.template
        if template is None:
            raise ValueError(f"Template {revision.template_id} not found")
        self.assert_template_access(template, user)

    def assert_can_submit_template_review(
        self, revision: DMTemplateRevision, user: User
    ) -> None:
        """校验当前用户是否可发起模板送审。"""

        self.assert_template_revision_access(revision, user)
        if revision.status != "draft":
            raise ValueError(
                f"Template revision {revision.id} status is {revision.status!r}; only draft can submit review"
            )

    def assert_can_approve_template_revision(
        self, revision: DMTemplateRevision, user: User
    ) -> None:
        """校验当前用户是否可审批模板版本。"""

        template = revision.template
        if template is None:
            raise ValueError(f"Template {revision.template_id} not found")

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "user":
            raise PermissionError(
                f"User {user.id} is not allowed to approve template revision {revision.id}"
            )
        if scope_context["role"] == "domain_admin":
            if not template.system_short or template.system_short not in scope_context["scopes"]:
                raise PermissionError(
                    f"User {user.id} has no approval scope for system_short={template.system_short!r}"
                )

        if revision.status != "pending_review":
            raise ValueError(
                f"Template revision {revision.id} status is {revision.status!r}; only pending_review can approve"
            )

        if revision.created_by == user.id:
            raise PermissionError(
                f"User {user.id} cannot approve template revision {revision.id} created by self"
            )

    def assert_initiator_override_allowed(
        self,
        requested_initiator_user_id: int | None,
        current_user: User,
    ) -> int:
        """校验调用方是否允许覆盖执行发起人。

        默认规则：
        - 不传则使用当前登录用户
        - 传且等于当前登录用户：允许
        - 只有 system_admin 允许替别人发起
        """

        if requested_initiator_user_id is None:
            return int(current_user.id)

        if int(requested_initiator_user_id) == int(current_user.id):
            return int(current_user.id)

        scope_context = self.get_scope_context(current_user)
        if scope_context["role"] == "system_admin":
            return int(requested_initiator_user_id)

        raise PermissionError(
            f"User {current_user.id} cannot override initiator_user_id to {requested_initiator_user_id}"
        )

    def assert_template_execution_access(
        self,
        revision: DMTemplateRevision,
        user: User,
        requested_system_short: str | None = None,
    ) -> None:
        """校验当前用户是否可基于模板版本发起执行。"""

        self.assert_template_revision_access(revision, user)
        template = revision.template
        if template is None:
            raise ValueError(f"Template {revision.template_id} not found")

        if requested_system_short and requested_system_short != template.system_short:
            raise PermissionError(
                "Requested system_short does not match the published template ownership"
            )

    def build_sql_audit_payload(
        self,
        run: DMRun,
        step: DMRunStep,
        resolved_plan: dict[str, Any],
        execution_status: str,
        raw_payload: dict[str, Any] | None = None,
        extracted_outputs: dict[str, Any] | None = None,
        error_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一拼装 SQL 审计载荷。

        这里不追求完整 SQL 解析，而是保证以下信息在同一结构里稳定可查：
        - 风险判定结果
        - 是否需要确认
        - 真正执行时的 SQL / 参数 / 结果摘要
        - 执行失败或阻塞原因
        """

        governance_result = resolved_plan.get("governance_check_result") or {}
        sql_snapshot = (raw_payload or {}).get("sql_snapshot") or {
            "sql": resolved_plan.get("sql"),
            "params": resolved_plan.get("param_template") or {},
        }
        result_snapshot = (raw_payload or {}).get("result_snapshot") or {}

        return {
            "run_id": run.id,
            "run_step_id": step.id,
            "step_id": step.step_id,
            "step_name": step.step_name,
            "step_type": step.step_type,
            "system_short": run.system_short,
            "asset_ref": resolved_plan.get("asset_ref"),
            "lane": resolved_plan.get("lane"),
            "risk_level": resolved_plan.get("risk_level") or governance_result.get("risk_level"),
            "confirmation_required": bool(resolved_plan.get("confirmation_required")),
            "confirmation_reason": governance_result.get("reason")
            or governance_result.get("message"),
            "governance_check_result": governance_result,
            "execution_status": execution_status,
            "sql_snapshot": sql_snapshot,
            "result_snapshot": result_snapshot,
            "extracted_outputs": extracted_outputs or {},
            "error_info": error_info or {},
            "target_objects": self._normalize_target_objects(
                resolved_plan=resolved_plan,
                sql_snapshot=sql_snapshot,
            ),
        }

    def record_sql_audit(
        self,
        run: DMRun,
        step: DMRunStep,
        actor_user_id: int,
        execution_status: str,
        audit_payload: dict[str, Any],
        error_info: dict[str, Any] | None = None,
    ) -> DMAuditRecord:
        """为 SQL 节点落一条治理/审计记录。

        一次 SQL 节点执行或阻塞，对应一条审计记录。
        这样后续即使同一个步骤多次试跑，也能保留完整历史。
        """

        confirmation_required = bool(audit_payload.get("confirmation_required"))
        if execution_status == "blocked" and confirmation_required:
            status = "pending_confirmation"
        elif execution_status == "blocked":
            status = "blocked"
        elif execution_status == "succeeded":
            status = "succeeded"
        else:
            status = "failed"

        record = DMAuditRecord(
            run_id=run.id,
            run_step_id=step.id,
            actor_user_id=actor_user_id,
            system_short=run.system_short,
            audit_type="sql_execution",
            risk_level=audit_payload.get("risk_level"),
            confirmation_mode="manual_confirm" if confirmation_required else "auto",
            target_objects=audit_payload.get("target_objects") or [],
            payload=audit_payload,
            status=status,
            error_message=(error_info or {}).get("message"),
        )
        self.db.add(record)
        self.db.flush()
        return record

    def confirm_dangerous_sql(
        self,
        run_id: int,
        user: User,
        reason: str | None = None,
        step_ids: Iterable[int] | None = None,
    ) -> dict[str, Any]:
        """确认某个 Run 中待确认的危险 SQL。

        当前这一版不直接做“自动继续执行”，而是把治理状态推进到
        “已确认，可重新进入执行链”的状态：

        - 审计记录写入确认人和确认时间
        - SQL 步骤的执行方案去掉 `confirmation_required`
        - 被确认阻塞的步骤回到 `pending`
        - 如果 Run 之前处于 `blocked`，则回退到 `pending`
        """

        run = self.db.query(DMRun).filter(DMRun.id == run_id).first()
        if run is None:
            raise ValueError(f"Run {run_id} not found")

        self.assert_run_access(run, user)

        query = self.db.query(DMAuditRecord).filter(
            DMAuditRecord.run_id == run_id,
            DMAuditRecord.audit_type == "sql_execution",
            DMAuditRecord.status == "pending_confirmation",
        )
        if step_ids:
            query = query.filter(DMAuditRecord.run_step_id.in_(list(step_ids)))

        audits = query.order_by(DMAuditRecord.id.asc()).all()
        if not audits:
            raise ValueError(f"Run {run_id} has no pending dangerous SQL confirmations")

        confirmed_at = self._now()
        confirmed_step_ids: list[str] = []

        try:
            for audit in audits:
                audit.status = "confirmed"
                audit.confirmed_by = user.id
                audit.confirmed_at = confirmed_at
                audit.error_message = None
                payload = dict(audit.payload or {})
                payload["confirmation_required"] = False
                payload["confirmed_by"] = int(user.id)
                payload["confirmed_at"] = confirmed_at.isoformat()
                if reason:
                    payload["confirmation_reason"] = reason
                audit.payload = payload

                step = audit.run_step
                if step is None:
                    continue

                plan = dict(step.resolved_execution_plan_snapshot or {})
                plan["confirmation_required"] = False
                plan["confirmation_confirmed"] = True
                plan["confirmed_by"] = int(user.id)
                plan["confirmed_at"] = confirmed_at.isoformat()
                if reason:
                    plan["confirmation_reason"] = reason
                step.resolved_execution_plan_snapshot = plan

                if step.status == "blocked":
                    step.status = "pending"
                    step.error_message = None
                    step.finished_at = None

                confirmed_step_ids.append(step.step_id)

            if run.status == "blocked":
                remaining_blocked = any(step.status == "blocked" for step in run.steps)
                if not remaining_blocked:
                    run.status = "pending"
                    run.error_summary = None

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return {
            "run_id": run.id,
            "status": run.status,
            "confirmed_count": len(audits),
            "confirmed_step_ids": confirmed_step_ids,
        }

    def list_sql_audits(self, user: User) -> list[dict[str, Any]]:
        """按当前用户权限列出 SQL 审计记录。"""

        scope_context = self.get_scope_context(user)
        if scope_context["role"] == "user":
            raise PermissionError("Only datamakepool admins can view SQL audits")

        query = self.db.query(DMAuditRecord).filter(DMAuditRecord.audit_type == "sql_execution")
        if scope_context["role"] == "domain_admin":
            query = query.filter(DMAuditRecord.system_short.in_(scope_context["scopes"]))

        audits = query.order_by(DMAuditRecord.created_at.desc(), DMAuditRecord.id.desc()).all()
        return [self._serialize_audit_summary(audit) for audit in audits]

    def get_sql_audit(self, audit_id: int, user: User) -> dict[str, Any]:
        """读取单条 SQL 审计详情。"""

        audit = self.db.query(DMAuditRecord).filter(DMAuditRecord.id == audit_id).first()
        if audit is None:
            raise ValueError(f"Audit {audit_id} not found")

        self.assert_audit_access(audit, user)
        return self._serialize_audit_detail(audit)

    def _normalize_target_objects(
        self,
        resolved_plan: dict[str, Any],
        sql_snapshot: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """把目标对象整理成统一列表结构，便于审计列表和详情复用。"""

        target_objects = resolved_plan.get("target_objects")
        if isinstance(target_objects, list):
            return [item for item in target_objects if isinstance(item, dict)]

        normalized: dict[str, Any] = {}
        if resolved_plan.get("asset_ref"):
            normalized["asset_ref"] = resolved_plan.get("asset_ref")
        if resolved_plan.get("lane"):
            normalized["lane"] = resolved_plan.get("lane")
        if sql_snapshot.get("sql"):
            normalized["sql"] = sql_snapshot.get("sql")
        return [normalized] if normalized else []

    def _serialize_audit_summary(self, audit: DMAuditRecord) -> dict[str, Any]:
        payload = audit.payload or {}
        return {
            "audit_id": audit.id,
            "run_id": audit.run_id,
            "run_step_id": audit.run_step_id,
            "system_short": audit.system_short,
            "audit_type": audit.audit_type,
            "risk_level": audit.risk_level,
            "confirmation_mode": audit.confirmation_mode,
            "status": audit.status,
            "step_id": payload.get("step_id"),
            "step_name": payload.get("step_name"),
            "created_at": audit.created_at.isoformat() if audit.created_at else None,
        }

    def _serialize_audit_detail(self, audit: DMAuditRecord) -> dict[str, Any]:
        payload = audit.payload or {}
        return {
            "audit_id": audit.id,
            "run_id": audit.run_id,
            "run_step_id": audit.run_step_id,
            "actor_user_id": audit.actor_user_id,
            "system_short": audit.system_short,
            "audit_type": audit.audit_type,
            "risk_level": audit.risk_level,
            "confirmation_mode": audit.confirmation_mode,
            "confirmed_by": audit.confirmed_by,
            "confirmed_at": audit.confirmed_at.isoformat() if audit.confirmed_at else None,
            "status": audit.status,
            "error_message": audit.error_message,
            "target_objects": audit.target_objects or [],
            "payload": payload,
            "created_at": audit.created_at.isoformat() if audit.created_at else None,
        }

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
