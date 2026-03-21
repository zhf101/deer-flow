from deerflow.nlp2sql.safety.sql_validator import SqlValidator
from deerflow.nlp2sql.types import ValidationMode


def test_validator_adds_limit_for_relaxed_select():
    validator = SqlValidator()

    result = validator.validate("select * from orders", force_limit=200)

    assert result.ok is True
    assert result.has_limit is True
    assert "LIMIT 200" in result.normalized_sql
    assert any("Added LIMIT 200" in warning for warning in result.warnings)


def test_validator_rejects_write_keyword():
    validator = SqlValidator()

    result = validator.validate("delete from orders where id = 1")

    assert result.ok is False
    assert any("read-only SELECT" in error or "forbidden" in error for error in result.errors)


def test_validator_rejects_with_insert_even_when_statement_starts_with_with():
    validator = SqlValidator()

    result = validator.validate(
        "with pending as (select id from orders) insert into archive_orders select * from pending"
    )

    assert result.ok is False
    assert "Only read-only SELECT queries are allowed" in result.errors


def test_validator_caps_existing_limit_and_marks_row_cap():
    validator = SqlValidator()

    result = validator.validate("select * from orders limit 500", force_limit=200)

    assert result.ok is True
    assert result.normalized_sql == "SELECT * FROM orders LIMIT 200"
    assert result.row_cap_applied is True
    assert any("Adjusted LIMIT from 500 to 200" in warning for warning in result.warnings)


def test_validator_strict_analyzes_explain_plan():
    class StubAdapter:
        dialect = "postgres"

        def explain_query(self, sql: str):
            assert sql == "SELECT * FROM orders LIMIT 200"
            return {"plan": {"Plan": {"Node Type": "Seq Scan", "Plan Rows": 200000}}}

    validator = SqlValidator()

    result = validator.validate(
        "select * from orders",
        mode=ValidationMode.STRICT,
        adapter=StubAdapter(),
    )

    assert result.ok is True
    assert result.row_cap_applied is True
    assert any("Execution plan estimates 200000 rows" in warning for warning in result.warnings)
    assert any("full scan node" in warning for warning in result.warnings)
