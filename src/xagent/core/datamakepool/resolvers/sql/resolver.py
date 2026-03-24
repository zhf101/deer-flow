from __future__ import annotations

from typing import Any

from ...contracts import EditableFieldSpec, ResolverInput, ResolverOutput


class SQLResolver:
    """SQL 节点的最小收敛器。"""

    def resolve(self, node: dict[str, Any], resolver_input: ResolverInput) -> ResolverOutput:
        existing_plan = node.get("resolved_execution_plan") or {}
        governance_result = (
            existing_plan.get("governance_check_result")
            or node.get("governance_check_result")
            or {}
        )

        plan = {
            "step_type": "sql_step",
            "asset_ref": (
                existing_plan.get("asset_ref")
                or existing_plan.get("asset_id")
                or node.get("asset_ref")
                or node.get("asset_id")
            ),
            "sql": existing_plan.get("sql") or existing_plan.get("statement") or node.get("sql"),
            "param_template": (
                existing_plan.get("param_template")
                or existing_plan.get("input_template")
                or node.get("param_template")
                or node.get("input_template")
                or {}
            ),
            "output_mapping": (
                existing_plan.get("output_mapping") or node.get("output_mapping") or {}
            ),
            "lane": existing_plan.get("lane") or node.get("lane"),
            "risk_level": existing_plan.get("risk_level") or node.get("risk_level"),
            "confirmation_required": bool(
                existing_plan.get("confirmation_required")
                or node.get("confirmation_required")
            ),
            "governance_check_result": governance_result,
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
            },
            resolved_execution_plan=plan,
            editable_fields=[
                EditableFieldSpec(name="param_template", mode="direct_edit"),
                EditableFieldSpec(name="output_mapping", mode="direct_edit"),
                EditableFieldSpec(name="asset_ref", mode="needs_resolution"),
                EditableFieldSpec(name="sql", mode="needs_resolution"),
            ],
        )
