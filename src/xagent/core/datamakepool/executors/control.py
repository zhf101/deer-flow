from __future__ import annotations

from typing import Any

from ..contracts import ExecutorInput, ExecutorOutput
from ..orchestration.runtime_values import build_value_context, render_template


class ControlExecutor:
    """控制节点执行器。"""

    def execute(
        self,
        step_type: str,
        execution_input: ExecutorInput,
        depends_on: list[str] | None = None,
    ) -> ExecutorOutput:
        runtime_values = execution_input.runtime_values or {}
        step_outputs = runtime_values.get("step_outputs") or {}
        user_inputs = runtime_values.get("user_inputs") or {}
        upstream_outputs = runtime_values.get("upstream_outputs") or {}
        context = build_value_context(
            user_inputs,
            step_outputs,
            {"upstream_outputs": upstream_outputs},
        )
        plan = execution_input.resolved_execution_plan

        if step_type == "start":
            return ExecutorOutput(
                execution_status="succeeded",
                extracted_outputs={},
                raw_payload={"control": "start"},
            )

        if step_type == "confirm":
            if plan.get("auto_confirm") or not plan.get("confirmation_required"):
                return ExecutorOutput(
                    execution_status="succeeded",
                    extracted_outputs={"confirmed": True},
                    raw_payload={"control": "confirm", "auto_confirm": True},
                )
            return ExecutorOutput(
                execution_status="blocked",
                error_info={
                    "message": "Confirmation step requires manual confirmation in a later phase",
                    "type": "confirmation_required",
                },
                raw_payload={"control": "confirm", "auto_confirm": False},
            )

        if step_type == "mapping":
            mapping_template = (
                plan.get("output_mapping") or plan.get("mapping") or upstream_outputs or {}
            )
            mapped_output = render_template(mapping_template, context)
            if not isinstance(mapped_output, dict):
                mapped_output = {"result": mapped_output}
            return ExecutorOutput(
                execution_status="succeeded",
                extracted_outputs=mapped_output,
                raw_payload={"mapped_output": mapped_output},
            )

        if step_type == "end":
            output_mapping = plan.get("output_mapping")
            if output_mapping:
                final_output = render_template(output_mapping, context)
            else:
                final_output = self._default_end_output(depends_on or [], upstream_outputs)
            if not isinstance(final_output, dict):
                final_output = {"result": final_output}
            return ExecutorOutput(
                execution_status="succeeded",
                extracted_outputs=final_output,
                raw_payload={"final_output": final_output},
            )

        return ExecutorOutput(
            execution_status="failed",
            error_info={
                "message": f"Unsupported control step type: {step_type}",
                "type": "unsupported_step_type",
            },
        )

    def _default_end_output(
        self, depends_on: list[str], upstream_outputs: dict[str, Any]
    ) -> Any:
        """没有显式 output_mapping 时，按依赖关系推断最小输出。"""

        if len(depends_on) == 1:
            return upstream_outputs.get(depends_on[0], {})
        return upstream_outputs
