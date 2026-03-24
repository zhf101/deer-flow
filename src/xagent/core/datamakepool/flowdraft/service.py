from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from xagent.web.models.dm_flow_draft import DMFlowDraft
from xagent.web.models.user import User

from ..contracts import FlowDraftStatus, ResolverInput
from ..governance import GovernanceService
from ..preflight import PreflightService
from ..resolvers import HTTPResolver, SQLResolver
from ..snapshots import SnapshotService


@dataclass
class FlowDraftService:
    """FlowDraft 生命周期服务。

    当前这一版优先补齐最小编辑闭环：

    - 读取草稿
    - 读取预检
    - patch 单步可编辑字段
    - 对单步触发局部重收敛
    - 创建快照
    - 输出最小 diff
    """

    db: Session
    preflight_service: Optional[PreflightService] = None
    snapshot_service: SnapshotService | None = None
    http_resolver: HTTPResolver = field(default_factory=HTTPResolver)
    sql_resolver: SQLResolver = field(default_factory=SQLResolver)

    def get_flowdraft(self, flowdraft_id: int, user: User | None = None) -> dict[str, Any]:
        """读取单个 FlowDraft。"""

        flowdraft = self._get_flowdraft_model(flowdraft_id)
        if user is not None:
            GovernanceService(db=self.db).assert_flowdraft_access(flowdraft, user)

        return self._serialize_flowdraft(flowdraft)

    def mark_needs_resolution(
        self, flowdraft_id: int, step_id: Optional[str] = None
    ) -> dict[str, Any]:
        """将整个草稿或某个步骤标记为 needs_resolution。"""

        return {
            "flowdraft_id": flowdraft_id,
            "step_id": step_id,
            "status": FlowDraftStatus.NEEDS_RESOLUTION.value,
        }

    def evaluate_preflight(self, technical_graph: dict[str, Any]) -> dict[str, Any]:
        """对 technical_graph 执行预检。"""

        service = self.preflight_service or PreflightService()
        return service.evaluate(technical_graph).model_dump()

    def get_preflight(self, flowdraft_id: int, user: User | None = None) -> dict[str, Any]:
        """读取指定 FlowDraft 的预检结果。"""

        flowdraft = self._get_flowdraft_model(flowdraft_id)
        if user is not None:
            GovernanceService(db=self.db).assert_flowdraft_access(flowdraft, user)

        if flowdraft.preflight_summary_payload:
            return flowdraft.preflight_summary_payload
        return self.evaluate_preflight(flowdraft.technical_graph_payload or {})

    def get_flowdraft_model(self, flowdraft_id: int, user: User | None = None) -> DMFlowDraft:
        """返回 FlowDraft ORM 对象。"""

        flowdraft = self._get_flowdraft_model(flowdraft_id)
        if user is not None:
            GovernanceService(db=self.db).assert_flowdraft_access(flowdraft, user)
        return flowdraft

    def list_snapshots(
        self,
        flowdraft_id: int,
        user: User,
    ) -> list[dict[str, Any]]:
        """列出 FlowDraft 的关键版本快照。"""

        flowdraft = self.get_flowdraft_model(flowdraft_id, user)
        return self._snapshot_service().list_snapshots(flowdraft)

    def diff_flowdraft(
        self,
        flowdraft_id: int,
        user: User,
        before_snapshot_id: int | None = None,
        after_snapshot_id: int | None = None,
    ) -> dict[str, Any]:
        """查看 FlowDraft 差异。

        默认策略：
        - `before_snapshot_id` 不传：取 `latest_snapshot_id`
        - `after_snapshot_id` 不传：取当前 FlowDraft
        """

        flowdraft = self.get_flowdraft_model(flowdraft_id, user)
        snapshot_service = self._snapshot_service()

        before_snapshot = None
        if before_snapshot_id is not None:
            before_snapshot = snapshot_service.get_snapshot(flowdraft.id, before_snapshot_id)
        elif flowdraft.latest_snapshot_id is not None:
            before_snapshot = snapshot_service.get_snapshot(flowdraft.id, flowdraft.latest_snapshot_id)

        if before_snapshot is None:
            raise ValueError(f"FlowDraft {flowdraft.id} has no available snapshot for diff")

        before_payload = {
            "business_graph": before_snapshot.business_graph_snapshot or {},
            "technical_graph": before_snapshot.technical_graph_snapshot or {},
            "preflight_summary": before_snapshot.preflight_summary_snapshot or {},
        }

        if after_snapshot_id is not None:
            after_snapshot = snapshot_service.get_snapshot(flowdraft.id, after_snapshot_id)
            after_payload = {
                "business_graph": after_snapshot.business_graph_snapshot or {},
                "technical_graph": after_snapshot.technical_graph_snapshot or {},
                "preflight_summary": after_snapshot.preflight_summary_snapshot or {},
            }
            after_label = f"snapshot:{after_snapshot.id}"
        else:
            after_payload = {
                "business_graph": flowdraft.business_graph_payload or {},
                "technical_graph": flowdraft.technical_graph_payload or {},
                "preflight_summary": flowdraft.preflight_summary_payload or {},
            }
            after_label = "current"

        return {
            "flowdraft_id": flowdraft.id,
            "before": {
                "snapshot_id": before_snapshot.id,
                "label": f"snapshot:{before_snapshot.id}",
            },
            "after": {
                "snapshot_id": after_snapshot_id,
                "label": after_label,
            },
            "business_graph_diff": snapshot_service.diff(
                before_payload["business_graph"],
                after_payload["business_graph"],
            ),
            "technical_graph_diff": snapshot_service.diff(
                before_payload["technical_graph"],
                after_payload["technical_graph"],
            ),
            "preflight_summary_diff": snapshot_service.diff(
                before_payload["preflight_summary"],
                after_payload["preflight_summary"],
            ),
        }

    def patch_flowdraft_step(
        self,
        flowdraft_id: int,
        step_id: str,
        changes: dict[str, Any],
        user: User,
    ) -> dict[str, Any]:
        """更新单个步骤的可编辑字段。"""

        if not isinstance(changes, dict) or not changes:
            raise ValueError("FlowDraft step patch requires non-empty changes")

        flowdraft = self.get_flowdraft_model(flowdraft_id, user)
        node = self._find_node(flowdraft, step_id)
        editable_fields = self._build_editable_field_modes(node)

        direct_updates: list[str] = []
        needs_resolution_fields: list[str] = []

        for field_name, field_value in changes.items():
            mode = editable_fields.get(field_name)
            if mode is None:
                raise ValueError(
                    f"Field {field_name!r} is not editable for step {step_id!r}"
                )

            if mode == "direct_edit":
                self._apply_direct_edit(node, field_name, field_value)
                direct_updates.append(field_name)
                continue

            self._apply_resolution_edit(node, field_name, field_value)
            needs_resolution_fields.append(field_name)

        flowdraft.technical_graph_payload = flowdraft.technical_graph_payload or {}
        flag_modified(flowdraft, "technical_graph_payload")
        flowdraft.preflight_summary_payload = None

        if needs_resolution_fields:
            flowdraft.status = FlowDraftStatus.NEEDS_RESOLUTION.value
        else:
            preflight_result = self.evaluate_preflight(flowdraft.technical_graph_payload or {})
            flowdraft.preflight_summary_payload = preflight_result
            flowdraft.status = self._derive_flowdraft_status(preflight_result)

        snapshot = self._snapshot_service().create_snapshot(
            flowdraft=flowdraft,
            snapshot_type="manual_edit",
            created_by=int(user.id),
        )
        self.db.commit()

        return {
            "flowdraft_id": flowdraft.id,
            "step_id": step_id,
            "status": flowdraft.status,
            "direct_updates": direct_updates,
            "needs_resolution_fields": needs_resolution_fields,
            "latest_snapshot_id": snapshot["snapshot_id"],
        }

    def resolve_flowdraft_step(
        self,
        flowdraft_id: int,
        step_id: str,
        user: User,
    ) -> dict[str, Any]:
        """只对单个步骤触发局部重收敛。"""

        flowdraft = self.get_flowdraft_model(flowdraft_id, user)
        node = self._find_node(flowdraft, step_id)
        resolver_output = self._resolve_node(flowdraft, node)

        if resolver_output is not None:
            node["resolved_execution_plan"] = resolver_output.resolved_execution_plan
            node["resolution_rationale"] = resolver_output.resolution_rationale
            node["editable_fields"] = [
                field.model_dump() for field in resolver_output.editable_fields
            ]
            node["pending_flags"] = []
        flag_modified(flowdraft, "technical_graph_payload")

        flowdraft.preflight_summary_payload = self.evaluate_preflight(
            flowdraft.technical_graph_payload or {}
        )
        flowdraft.status = self._derive_flowdraft_status(flowdraft.preflight_summary_payload)

        snapshot = self._snapshot_service().create_snapshot(
            flowdraft=flowdraft,
            snapshot_type="re_resolved",
            created_by=int(user.id),
        )
        self.db.commit()

        return {
            "flowdraft_id": flowdraft.id,
            "step_id": step_id,
            "status": flowdraft.status,
            "resolution_status": (
                resolver_output.resolution_status if resolver_output is not None else "resolved"
            ),
            "blocking_issues": (
                resolver_output.blocking_issues if resolver_output is not None else []
            ),
            "latest_snapshot_id": snapshot["snapshot_id"],
        }

    def _get_flowdraft_model(self, flowdraft_id: int) -> DMFlowDraft:
        """读取 FlowDraft ORM 对象。"""

        flowdraft = self.db.query(DMFlowDraft).filter(DMFlowDraft.id == flowdraft_id).first()
        if flowdraft is None:
            raise ValueError(f"FlowDraft {flowdraft_id} not found")
        return flowdraft

    def _serialize_flowdraft(self, flowdraft: DMFlowDraft) -> dict[str, Any]:
        """把 ORM 对象压平成 API 可直接返回的结构。"""

        return {
            "id": flowdraft.id,
            "task_id": flowdraft.task_id,
            "status": flowdraft.status,
            "title": flowdraft.title,
            "objective": flowdraft.objective,
            "business_graph": flowdraft.business_graph_payload or {},
            "technical_graph": flowdraft.technical_graph_payload or {},
            "pending_issues": flowdraft.pending_issues_payload or [],
            "preflight_summary": flowdraft.preflight_summary_payload,
            "input_schema_draft": flowdraft.input_schema_draft,
            "output_mapping_draft": flowdraft.output_mapping_draft,
            "latest_snapshot_id": flowdraft.latest_snapshot_id,
        }

    def _find_node(self, flowdraft: DMFlowDraft, step_id: str) -> dict[str, Any]:
        """从 technical_graph 中定位指定步骤。"""

        technical_graph = flowdraft.technical_graph_payload or {}
        nodes = technical_graph.get("nodes", []) if isinstance(technical_graph, dict) else []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_step_id = str(node.get("step_id") or node.get("id") or "")
            if node_step_id == step_id:
                return node
        raise ValueError(f"FlowDraft step {step_id!r} not found")

    def _build_editable_field_modes(self, node: dict[str, Any]) -> dict[str, str]:
        """构建步骤的最小可编辑字段表。"""

        editable_fields = node.get("editable_fields") or []
        editable_map: dict[str, str] = {}
        for item in editable_fields:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            mode = str(item.get("mode") or "").strip()
            if name and mode:
                editable_map[name] = mode

        if editable_map:
            return editable_map

        step_type = str(node.get("step_type") or "")
        if step_type == "http_step":
            return {
                "query_template": "direct_edit",
                "headers_template": "direct_edit",
                "body_template": "direct_edit",
                "output_mapping": "direct_edit",
                "asset_ref": "needs_resolution",
            }
        if step_type == "sql_step":
            return {
                "param_template": "direct_edit",
                "output_mapping": "direct_edit",
                "asset_ref": "needs_resolution",
                "sql": "needs_resolution",
            }
        if step_type == "mapping":
            return {
                "mapping": "direct_edit",
                "output_mapping": "direct_edit",
            }
        if step_type == "confirm":
            return {
                "confirmation_required": "direct_edit",
                "auto_confirm": "direct_edit",
            }
        return {}

    def _apply_direct_edit(self, node: dict[str, Any], field_name: str, field_value: Any) -> None:
        """应用 direct_edit 类型修改。"""

        plan = node.setdefault("resolved_execution_plan", {})
        if not isinstance(plan, dict):
            plan = {}
            node["resolved_execution_plan"] = plan

        plan[field_name] = field_value
        if field_name in {"mapping", "output_mapping"}:
            node[field_name] = field_value

    def _apply_resolution_edit(
        self,
        node: dict[str, Any],
        field_name: str,
        field_value: Any,
    ) -> None:
        """应用 needs_resolution 类型修改。"""

        node[field_name] = field_value
        node["resolution_rationale"] = {}
        node["editable_fields"] = []
        node["pending_flags"] = ["needs_resolution"]
        node.pop("resolved_execution_plan", None)

    def _resolve_node(
        self,
        flowdraft: DMFlowDraft,
        node: dict[str, Any],
    ):
        """对单个节点触发最小重收敛。"""

        step_type = str(node.get("step_type") or "")
        if step_type == "http_step":
            return self.http_resolver.resolve(
                node,
                ResolverInput(
                    design_intent=node.get("design_intent") or {},
                    user_inputs=flowdraft.input_schema_draft or {},
                    template_context={"flowdraft_id": flowdraft.id},
                    governance_rules=node.get("governance_rules") or {},
                ),
            )

        if step_type == "sql_step":
            return self.sql_resolver.resolve(
                node,
                ResolverInput(
                    design_intent=node.get("design_intent") or {},
                    user_inputs=flowdraft.input_schema_draft or {},
                    template_context={"flowdraft_id": flowdraft.id},
                    governance_rules=node.get("governance_rules") or {},
                ),
            )

        if step_type in {"mapping", "confirm", "start", "end"}:
            node["pending_flags"] = []
            existing_plan = node.get("resolved_execution_plan") or {}
            if step_type == "mapping":
                node["resolved_execution_plan"] = {
                    **existing_plan,
                    "mapping": node.get("mapping") or existing_plan.get("mapping"),
                    "output_mapping": node.get("output_mapping")
                    or existing_plan.get("output_mapping"),
                }
            elif step_type == "confirm":
                node["resolved_execution_plan"] = {
                    **existing_plan,
                    "confirmation_required": bool(
                        node.get("confirmation_required")
                        if node.get("confirmation_required") is not None
                        else existing_plan.get("confirmation_required")
                    ),
                    "auto_confirm": bool(
                        node.get("auto_confirm")
                        if node.get("auto_confirm") is not None
                        else existing_plan.get("auto_confirm")
                    ),
                }
            else:
                node["resolved_execution_plan"] = existing_plan or {}
            return None

        raise ValueError(f"Unsupported flowdraft step type {step_type!r} for resolve")

    def _derive_flowdraft_status(self, preflight_result: dict[str, Any]) -> str:
        """根据预检结果推断当前 FlowDraft 状态。"""

        if preflight_result.get("is_runnable", False):
            return FlowDraftStatus.READY_FOR_TRIAL.value
        return FlowDraftStatus.NEEDS_RESOLUTION.value

    def _snapshot_service(self) -> SnapshotService:
        """返回快照服务实例。"""

        return self.snapshot_service or SnapshotService(db=self.db)
