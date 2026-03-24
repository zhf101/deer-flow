from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts import PreflightIssue, PreflightResult


@dataclass
class PreflightService:
    """Evaluates whether a FlowDraft has converged enough to enter trial execution."""

    def evaluate(self, technical_graph: dict[str, Any]) -> PreflightResult:
        issues: list[PreflightIssue] = []
        nodes = technical_graph.get("nodes", []) if isinstance(technical_graph, dict) else []

        for node in nodes:
            if not isinstance(node, dict):
                continue

            step_id = str(node.get("step_id") or node.get("id") or "")
            step_type = str(node.get("step_type") or "")
            pending_flags = node.get("pending_flags") or []
            resolved_plan = node.get("resolved_execution_plan") or {}

            for flag in pending_flags:
                issue_type = str(flag)
                issues.append(
                    PreflightIssue(
                        issue_type=issue_type,
                        step_id=step_id or None,
                        message=f"Step {step_id or '<unknown>'} has pending flag: {issue_type}",
                        suggested_action=self._suggest_action(issue_type),
                        payload={"step_type": step_type},
                    )
                )

            if step_type in {"http_step", "sql_step"} and not resolved_plan:
                issues.append(
                    PreflightIssue(
                        issue_type="resolution_missing",
                        step_id=step_id or None,
                        message=f"Step {step_id or '<unknown>'} has no resolved execution plan",
                        suggested_action="resolve_step",
                        payload={"step_type": step_type},
                    )
                )

        grouped_by_type: dict[str, list[dict[str, Any]]] = {}
        grouped_by_step: dict[str, list[dict[str, Any]]] = {}

        for issue in issues:
            issue_dict = issue.model_dump()
            grouped_by_type.setdefault(issue.issue_type, []).append(issue_dict)
            step_key = issue.step_id or "__global__"
            grouped_by_step.setdefault(step_key, []).append(issue_dict)

        suggested_actions = sorted(
            {
                action
                for action in (issue.suggested_action for issue in issues)
                if action
            }
        )

        return PreflightResult(
            is_runnable=len(issues) == 0,
            issues=issues,
            grouped_by_type=grouped_by_type,
            grouped_by_step=grouped_by_step,
            suggested_actions=suggested_actions,
        )

    def _suggest_action(self, issue_type: str) -> str:
        if issue_type in {"route_pending", "asset_intent_mismatch"}:
            return "return_to_chat"
        if issue_type in {"asset_pending", "param_pending", "mapping_incomplete"}:
            return "edit_step_design"
        if issue_type == "governance_blocked":
            return "review_governance"
        return "resolve_step"
