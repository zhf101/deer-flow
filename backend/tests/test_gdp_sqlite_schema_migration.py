from sqlalchemy import create_engine, text

from app.gdp.persistence.schema import ensure_sqlite_gdp_schema


def _columns(conn, table_name: str) -> set[str]:
    return {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})")}


def test_ensure_sqlite_gdp_schema_adds_missing_sql_source_columns(tmp_path):
    db_path = tmp_path / "gdp_old.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE df_sql_source (
                    id VARCHAR(64) PRIMARY KEY,
                    source_code VARCHAR(128) NOT NULL,
                    source_name VARCHAR(256) NOT NULL,
                    sys_code VARCHAR(64) NOT NULL,
                    datasource_code VARCHAR(128) NOT NULL,
                    operation VARCHAR(32) NOT NULL,
                    sql_text TEXT NOT NULL,
                    normalized_sql TEXT NOT NULL,
                    tables_json TEXT NOT NULL,
                    result_fields_json TEXT NOT NULL,
                    condition_fields_json TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    safety_json TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )

        ensure_sqlite_gdp_schema(conn)

        columns = _columns(conn, "df_sql_source")
        assert "tags_json" in columns
        assert "capability_type" in columns
        assert "business_domain" in columns
        assert "side_effects_json" in columns
        assert "agent_description" in columns
