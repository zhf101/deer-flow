from __future__ import annotations

from typing import Any

from ...contracts import EditableFieldSpec, ResolverInput, ResolverOutput


class SQLResolver:
    """SQL 节点的最小收敛器。"""

    def resolve(self, node: dict[str, Any], resolver_input: ResolverInput) -> ResolverOutput:
        existing_plan = node.get("resolved_execution_plan") or {}
        asset_definition = resolver_input.asset_definition or {}
        governance_result = (
            existing_plan.get("governance_check_result")
            or node.get("governance_check_result")
            or {}
        )
        sql_text = existing_plan.get("sql") or existing_plan.get("statement") or node.get("sql")
        inferred_governance = self._infer_governance(
            sql=sql_text,
            lane=existing_plan.get("lane") or node.get("lane"),
            risk_level=existing_plan.get("risk_level") or node.get("risk_level"),
            confirmation_required=(
                existing_plan.get("confirmation_required") or node.get("confirmation_required")
            ),
            governance_result=governance_result,
        )

        plan = {
            "step_type": "sql_step",
            "asset_ref": (
                existing_plan.get("asset_ref")
                or existing_plan.get("asset_id")
                or node.get("asset_ref")
                or node.get("asset_id")
                or asset_definition.get("asset_ref")
            ),
            "sql": sql_text,
            "param_template": (
                existing_plan.get("param_template")
                or existing_plan.get("input_template")
                or node.get("param_template")
                or node.get("input_template")
                or asset_definition.get("param_template")
                or {}
            ),
            "output_mapping": (
                existing_plan.get("output_mapping") or node.get("output_mapping") or {}
            ),
            "lane": inferred_governance["lane"],
            "risk_level": inferred_governance["risk_level"],
            "confirmation_required": inferred_governance["confirmation_required"],
            "governance_check_result": inferred_governance["governance_check_result"],
        }

        blocking_issues: list[dict[str, Any]] = []
        if not plan["asset_ref"]:
            blocking_issues.append(
                {"issue_type": "asset_pending", "message": "SQL step has no resolved asset"}
            )
        if not plan["sql"]:
            blocking_issues.append(
                {
                    "issue_type": "resolution_missing",
                    "message": "SQL step has no executable SQL statement",
                }
            )

        governance_status = str(governance_result.get("status") or "")
        if governance_status in {"blocked", "rejected"}:
            blocking_issues.append(
                {
                    "issue_type": "governance_blocked",
                    "message": "SQL governance pre-check blocks execution",
                }
            )

        if plan["confirmation_required"]:
            blocking_issues.append(
                {
                    "issue_type": "confirmation_required",
                    "message": "SQL step requires confirmation and cannot auto-run in phase 2A",
                }
            )

        return ResolverOutput(
            resolution_status="blocked" if blocking_issues else "resolved",
            blocking_issues=blocking_issues,
            resolution_rationale={
                "strategy": "reuse_existing_sql_plan",
                "governance_rules": resolver_input.governance_rules,
                "governance_inference": inferred_governance,
                "asset_binding": {
                    "asset_id": asset_definition.get("asset_id"),
                    "version_id": asset_definition.get("version_id"),
                    "version_status": asset_definition.get("status"),
                }
                if asset_definition
                else {},
            },
            resolved_execution_plan=plan,
            editable_fields=[
                EditableFieldSpec(name="param_template", mode="direct_edit"),
                EditableFieldSpec(name="output_mapping", mode="direct_edit"),
                EditableFieldSpec(name="asset_ref", mode="needs_resolution"),
                EditableFieldSpec(name="sql", mode="needs_resolution"),
            ],
        )

    def _infer_governance(
        self,
        sql: Any,
        lane: Any,
        risk_level: Any,
        confirmation_required: Any,
        governance_result: dict[str, Any],
    ) -> dict[str, Any]:
        """为 SQL 节点补最小治理判定。

        当前规则只做 V1 第一阶段需要的粗粒度判断：
        - `select / with / show / desc / explain` 视为 query
        - `insert / update / delete / merge / alter / drop / truncate / create / replace`
          视为 mutation
        - mutation 默认要求确认
        """

        sql_text = str(sql or "").strip()
        first_keyword = sql_text.split(None, 1)[0].lower() if sql_text else ""
        inferred_lane = str(lane or "").strip().lower()
        if not inferred_lane:
            if first_keyword in {"select", "with", "show", "desc", "describe", "explain"}:
                inferred_lane = "query"
            elif first_keyword in {
                "insert",
                "update",
                "delete",
                "merge",
                "alter",
                "drop",
                "truncate",
                "create",
                "replace",
            }:
                inferred_lane = "mutation"

        inferred_risk = str(risk_level or "").strip().lower()
        if not inferred_risk:
            if inferred_lane == "mutation":
                inferred_risk = "high"
            elif inferred_lane == "query":
                inferred_risk = "low"

        requires_confirmation = bool(confirmation_required)
        if not confirmation_required and inferred_lane == "mutation":
            requires_confirmation = True

        resolved_governance = dict(governance_result or {})
        if not resolved_governance:
            if requires_confirmation:
                resolved_governance = {
                    "status": "review_required",
                    "reason": "mutation_sql_requires_manual_confirmation",
                    "lane": inferred_lane,
                    "risk_level": inferred_risk,
                }
            else:
                resolved_governance = {
                    "status": "passed",
                    "reason": "query_sql_can_run_directly",
                    "lane": inferred_lane,
                    "risk_level": inferred_risk,
                }

        return {
            "lane": inferred_lane or None,
            "risk_level": inferred_risk or None,
            "confirmation_required": requires_confirmation,
            "governance_check_result": resolved_governance,
        }
