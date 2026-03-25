from __future__ import annotations

from typing import Any

from ...contracts import EditableFieldSpec, ResolverInput, ResolverOutput


class HTTPResolver:
    """HTTP 节点的最小收敛器。"""

    def resolve(self, node: dict[str, Any], resolver_input: ResolverInput) -> ResolverOutput:
        existing_plan = node.get("resolved_execution_plan") or {}
        asset_definition = resolver_input.asset_definition or {}
        plan = {
            "step_type": "http_step",
            "asset_ref": (
                existing_plan.get("asset_ref")
                or existing_plan.get("asset_id")
                or node.get("asset_ref")
                or node.get("asset_id")
                or asset_definition.get("asset_ref")
            ),
            "method": str(
                existing_plan.get("method")
                or node.get("method")
                or asset_definition.get("method")
                or "GET"
            ).upper(),
            "url": existing_plan.get("url") or node.get("url"),
            "base_url": (
                existing_plan.get("base_url")
                or node.get("base_url")
                or asset_definition.get("base_url")
            ),
            "path_template": (
                existing_plan.get("path_template")
                or node.get("path_template")
                or asset_definition.get("path_template")
            ),
            "query_template": (
                existing_plan.get("query_template")
                or existing_plan.get("param_template")
                or existing_plan.get("input_template")
                or node.get("query_template")
                or node.get("param_template")
                or node.get("input_template")
                or asset_definition.get("query_template")
                or {}
            ),
            "headers_template": (
                existing_plan.get("headers_template")
                or node.get("headers_template")
                or asset_definition.get("headers_template")
                or {}
            ),
            "body_template": (
                existing_plan.get("body_template")
                or node.get("body_template")
                or asset_definition.get("body_template")
            ),
            "output_mapping": (
                existing_plan.get("output_mapping")
                or node.get("output_mapping")
                or asset_definition.get("response_extraction_rules")
                or {}
            ),
            "timeout_seconds": int(
                existing_plan.get("timeout_seconds")
                or node.get("timeout_seconds")
                or asset_definition.get("timeout_seconds")
                or 30
            ),
        }

        blocking_issues: list[dict[str, Any]] = []
        if not plan["asset_ref"] and not (plan["url"] or plan["base_url"]):
            blocking_issues.append(
                {
                    "issue_type": "asset_pending",
                    "message": "HTTP step has neither asset reference nor concrete URL/base_url",
                }
            )

        if not plan["url"] and not plan["base_url"]:
            blocking_issues.append(
                {
                    "issue_type": "resolution_missing",
                    "message": "HTTP step is missing executable URL information",
                }
            )

        return ResolverOutput(
            resolution_status="blocked" if blocking_issues else "resolved",
            blocking_issues=blocking_issues,
            resolution_rationale={
                "strategy": "reuse_existing_http_plan",
                "upstream_steps": sorted(resolver_input.upstream_outputs.keys()),
                "asset_binding": {
                    "asset_id": asset_definition.get("asset_id"),
                    "system_short": asset_definition.get("system_short"),
                }
                if asset_definition
                else {},
            },
            resolved_execution_plan=plan,
            editable_fields=[
                EditableFieldSpec(name="query_template", mode="direct_edit"),
                EditableFieldSpec(name="headers_template", mode="direct_edit"),
                EditableFieldSpec(name="body_template", mode="direct_edit"),
                EditableFieldSpec(name="output_mapping", mode="direct_edit"),
                EditableFieldSpec(name="asset_ref", mode="needs_resolution"),
            ],
        )
