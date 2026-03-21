---
name: nlp2sql
description: Use this skill when the user wants to query a configured SQL database in natural language. Enforces schema grounding before SQL generation, then validate_sql before execute_sql.
---

# NLP2SQL Skill

Use this skill when the user wants to explore or query a configured SQL database through DeerFlow's native `nlp2sql` tools.

## Workflow

1. If no data source is selected, call `list_data_sources` and ask the user to choose one, or call `use_data_source` when the intended source is obvious from context.
2. Ground on schema before writing SQL:
   - Start with `search_schema`
   - Then use `get_table_info`
   - Use `get_relationships`, `get_enum_values`, or `get_sample_rows` only when they materially reduce ambiguity
3. Generate a read-only SQL query.
4. Call `validate_sql` before execution.
5. Only call `execute_sql` after validation passes.
6. If the user wants a downloadable result file, call `export_query_result`.

## Rules

- Never guess table names or column names when schema tools can confirm them.
- Prefer narrow, explicit queries over `SELECT *`.
- Keep queries read-only.
- Explain the result in natural language and include the executed SQL when it helps the user audit the answer.
