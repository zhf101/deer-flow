from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp

from deerflow.nlp2sql.types import SqlValidationResult, ValidationMode

_FORBIDDEN_KEYWORDS_RE = re.compile(
    r"\b(insert|update|delete|alter|drop|truncate|create|grant|revoke|merge|call|execute|copy)\b",
    re.IGNORECASE,
)


def _walk_plan_nodes(plan: Any):
    if isinstance(plan, dict):
        yield plan
        for value in plan.values():
            yield from _walk_plan_nodes(value)
    elif isinstance(plan, list):
        for item in plan:
            yield from _walk_plan_nodes(item)


class SqlValidator:
    def _dialect_name(self, adapter) -> str | None:
        dialect = getattr(adapter, "dialect", None)
        return dialect if isinstance(dialect, str) else None

    def _is_read_only_query(self, expression: exp.Expression) -> bool:
        return isinstance(expression, exp.Query)

    def _extract_limit_value(self, expression: exp.Expression) -> int | None:
        limit = expression.args.get("limit")
        if not isinstance(limit, exp.Limit):
            return None
        limit_expression = limit.expression
        if isinstance(limit_expression, exp.Literal) and not limit_expression.is_string:
            try:
                return int(limit_expression.this)
            except (TypeError, ValueError):
                return None
        return None

    def validate(
        self,
        sql: str,
        *,
        mode: ValidationMode = ValidationMode.RELAXED,
        readonly: bool = True,
        force_limit: int | None = 200,
        allowed_schemas: list[str] | None = None,
        allowed_tables: list[str] | None = None,
        adapter=None,
    ) -> SqlValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        stripped = sql.strip().rstrip(";")

        if not stripped:
            errors.append("SQL cannot be empty")
            return SqlValidationResult(
                ok=False,
                mode=mode,
                normalized_sql="",
                errors=errors,
                warnings=warnings,
                readonly=readonly,
                has_limit=False,
            )

        try:
            statements = sqlglot.parse(stripped, read=self._dialect_name(adapter))
        except Exception as exc:
            errors.append(f"SQL parse error: {exc}")
            return SqlValidationResult(
                ok=False,
                mode=mode,
                normalized_sql=stripped,
                errors=errors,
                warnings=warnings,
                readonly=readonly,
                has_limit=False,
            )

        if len(statements) != 1:
            errors.append("Only a single SQL statement is allowed")

        expression = statements[0]
        lowered = stripped.lower()
        if readonly and not self._is_read_only_query(expression):
            errors.append("Only read-only SELECT queries are allowed")

        if _FORBIDDEN_KEYWORDS_RE.search(lowered):
            errors.append("Query contains forbidden write or DDL keywords")

        table_refs = {table.name for table in expression.find_all(exp.Table)}
        if allowed_tables:
            disallowed_tables = sorted(table_refs - set(allowed_tables))
            if disallowed_tables:
                errors.append(f"Query references tables outside the whitelist: {', '.join(disallowed_tables)}")

        schema_refs = {table.db for table in expression.find_all(exp.Table) if table.db}
        if allowed_schemas:
            disallowed_schemas = sorted(schema_refs - set(allowed_schemas))
            if disallowed_schemas:
                errors.append(f"Query references schemas outside the whitelist: {', '.join(disallowed_schemas)}")

        has_limit = expression.find(exp.Limit) is not None
        row_cap_applied = False
        normalized_sql = stripped
        if force_limit is not None and not errors:
            safe_limit = int(force_limit)
            current_limit = self._extract_limit_value(expression)
            if current_limit is None and not has_limit:
                normalized_sql = expression.limit(safe_limit, copy=True).sql(dialect=self._dialect_name(adapter))
                has_limit = True
                row_cap_applied = True
                warnings.append(f"Added LIMIT {safe_limit} to protect against large result sets")
            elif current_limit is not None and current_limit > safe_limit:
                normalized_sql = expression.limit(safe_limit, copy=True).sql(dialect=self._dialect_name(adapter))
                has_limit = True
                row_cap_applied = True
                warnings.append(f"Adjusted LIMIT from {current_limit} to {safe_limit} to enforce the data source row cap")

        explain_summary: dict[str, Any] | None = None
        if mode == ValidationMode.STRICT and not errors and adapter is not None:
            try:
                explain_summary = adapter.explain_query(normalized_sql)
            except Exception as exc:
                errors.append(f"Database EXPLAIN failed: {exc}")
            else:
                explain_errors, explain_warnings = self._analyze_explain(explain_summary)
                errors.extend(explain_errors)
                warnings.extend(explain_warnings)

        return SqlValidationResult(
            ok=len(errors) == 0,
            mode=mode,
            normalized_sql=normalized_sql,
            errors=errors,
            warnings=warnings,
            readonly=readonly,
            has_limit=has_limit,
            row_cap_applied=row_cap_applied,
            explain_summary=explain_summary,
        )

    def _analyze_explain(self, explain_summary: dict[str, Any]) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        seen_messages: set[str] = set()

        for node in _walk_plan_nodes(explain_summary):
            row_estimate = node.get("rows") or node.get("Plan Rows")
            if isinstance(row_estimate, str) and row_estimate.isdigit():
                row_estimate = int(row_estimate)
            if isinstance(row_estimate, (int, float)):
                if row_estimate > 1_000_000:
                    message = f"Execution plan estimates {int(row_estimate)} rows, which exceeds the strict safety threshold"
                    if message not in seen_messages:
                        errors.append(message)
                        seen_messages.add(message)
                elif row_estimate > 100_000:
                    message = f"Execution plan estimates {int(row_estimate)} rows; review whether the query is sufficiently selective"
                    if message not in seen_messages:
                        warnings.append(message)
                        seen_messages.add(message)

            scan_type = str(node.get("access_type") or node.get("Node Type") or "")
            if scan_type.upper() == "ALL" or scan_type == "Seq Scan":
                message = f"Execution plan contains a full scan node ({scan_type})"
                if message not in seen_messages:
                    warnings.append(message)
                    seen_messages.add(message)

        return errors, warnings
