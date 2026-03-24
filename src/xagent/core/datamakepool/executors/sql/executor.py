from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ...contracts import ExecutorInput, ExecutorOutput
from ...orchestration.runtime_values import build_value_context, render_template


class SQLExecutor:
    """SQL 节点执行器。"""

    def __init__(self, db: Session):
        self.db = db

    def execute(self, execution_input: ExecutorInput) -> ExecutorOutput:
        plan = execution_input.resolved_execution_plan
        runtime_values = execution_input.runtime_values or {}
        context = build_value_context(
            runtime_values.get("user_inputs"),
            runtime_values.get("step_outputs"),
            {"upstream_outputs": runtime_values.get("upstream_outputs", {})},
        )

        sql = str(plan.get("sql") or "")
        params = render_template(plan.get("param_template") or {}, context)
        query_snapshot = {"sql": sql, "params": params}

        try:
            result = self.db.execute(text(sql), params if isinstance(params, dict) else {})
            rows: list[dict[str, Any]] = []
            if result.returns_rows:
                rows = [dict(row._mapping) for row in result.fetchall()]
            rowcount = int(result.rowcount or 0)
        except SQLAlchemyError as exc:
            return ExecutorOutput(
                execution_status="failed",
                error_info={"message": str(exc), "type": exc.__class__.__name__},
                raw_payload={"sql_snapshot": query_snapshot},
            )

        result_snapshot = {
            "rows": rows,
            "rowcount": rowcount,
        }
        response_context = {
            "response": {
                "rows": rows,
                "first_row": rows[0] if rows else None,
                "rowcount": rowcount,
            }
        }
        extracted_outputs = (
            render_template(
                plan.get("output_mapping"),
                build_value_context(
                    runtime_values.get("user_inputs"),
                    runtime_values.get("step_outputs"),
                    {
                        "upstream_outputs": runtime_values.get("upstream_outputs", {}),
                        **response_context,
                    },
                ),
            )
            if plan.get("output_mapping")
            else result_snapshot
        )

        return ExecutorOutput(
            execution_status="succeeded",
            extracted_outputs=extracted_outputs if isinstance(extracted_outputs, dict) else {"result": extracted_outputs},
            execution_metrics={"rowcount": rowcount},
            raw_payload={
                "sql_snapshot": query_snapshot,
                "result_snapshot": result_snapshot,
            },
        )
