from __future__ import annotations

from typing import Any

import requests

from ...contracts import ExecutorInput, ExecutorOutput
from ..runtime_values import build_value_context, render_template


class HTTPExecutor:
    """HTTP 节点执行器。"""

    def execute(self, execution_input: ExecutorInput) -> ExecutorOutput:
        plan = execution_input.resolved_execution_plan
        runtime_values = execution_input.runtime_values or {}
        context = build_value_context(
            runtime_values.get("user_inputs"),
            runtime_values.get("step_outputs"),
            {"upstream_outputs": runtime_values.get("upstream_outputs", {})},
        )

        params = render_template(plan.get("query_template") or {}, context)
        headers = render_template(plan.get("headers_template") or {}, context)
        body = render_template(plan.get("body_template"), context)
        url = self._build_url(plan)

        request_snapshot = {
            "method": str(plan.get("method") or "GET").upper(),
            "url": url,
            "params": params,
            "headers": headers,
            "body": body,
        }

        try:
            response = requests.request(
                method=request_snapshot["method"],
                url=url,
                params=params if isinstance(params, dict) else None,
                headers=headers if isinstance(headers, dict) else None,
                json=body if isinstance(body, (dict, list)) else None,
                data=body if body is not None and not isinstance(body, (dict, list)) else None,
                timeout=float(plan.get("timeout_seconds") or 30),
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            return ExecutorOutput(
                execution_status="failed",
                error_info={"message": str(exc), "type": exc.__class__.__name__},
                raw_payload={"request_snapshot": request_snapshot},
            )

        response_body = self._parse_response_body(response)
        response_context = {
            "response": {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "json": response_body if isinstance(response_body, (dict, list)) else None,
                "text": response.text,
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
            else {
                "status_code": response.status_code,
                "body": response_body,
            }
        )

        return ExecutorOutput(
            execution_status="succeeded",
            extracted_outputs=extracted_outputs if isinstance(extracted_outputs, dict) else {"result": extracted_outputs},
            execution_metrics={
                "status_code": response.status_code,
                "elapsed_ms": int(response.elapsed.total_seconds() * 1000),
            },
            raw_payload={
                "request_snapshot": request_snapshot,
                "response_snapshot": {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_body,
                },
            },
        )

    def _build_url(self, plan: dict[str, Any]) -> str:
        """优先使用绝对 url，其次拼 base_url + path_template。"""

        url = plan.get("url")
        if isinstance(url, str) and url:
            return url

        base_url = str(plan.get("base_url") or "").rstrip("/")
        path = str(plan.get("path_template") or "").lstrip("/")
        if path:
            return f"{base_url}/{path}" if base_url else path
        return base_url

    def _parse_response_body(self, response: requests.Response) -> Any:
        """优先尝试 JSON，失败后退化为纯文本。"""

        try:
            return response.json()
        except ValueError:
            return response.text
