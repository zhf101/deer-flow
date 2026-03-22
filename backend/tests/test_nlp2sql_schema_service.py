from deerflow.nlp2sql.schema.service import SchemaService
from deerflow.nlp2sql.types import DataSourceConfig


def _schema_doc() -> dict:
    return {
        "schemas": [
            {
                "name": "public",
                "tables": [
                    {
                        "name": "orders",
                        "comment": "Customer orders",
                        "columns": [
                            {"name": "id", "comment": "Primary key"},
                            {"name": "status", "comment": "Order status"},
                        ],
                        "foreign_keys": [
                            {
                                "column": "customer_id",
                                "referred_schema": "public",
                                "referred_table": "customers",
                                "referred_column": "id",
                            }
                        ],
                    },
                    {
                        "name": "customers",
                        "comment": "Customer profile",
                        "columns": [{"name": "id", "comment": "Primary key"}],
                        "foreign_keys": [],
                    },
                ],
            }
        ]
    }


def _build_config(**overrides) -> DataSourceConfig:
    payload = {
        "id": "sales-db",
        "name": "Sales DB",
        "db_type": "postgres",
        "host": "localhost",
        "port": 5432,
        "database": "sales",
        "username": "readonly",
        "password_env": "SALES_DB_PASSWORD",
        "readonly": True,
        "enabled": True,
        "description": "Test database",
        "schema_whitelist": ["public"],
        "table_whitelist": ["orders"],
        "connect_timeout_seconds": 10,
        "query_timeout_seconds": 60,
        "max_rows": 200,
        "default_validation_mode": "relaxed",
    }
    payload.update(overrides)
    return DataSourceConfig.model_validate(payload)


class StubSnapshotStore:
    def __init__(self, snapshots: dict[str, dict] | None = None):
        self.snapshots = dict(snapshots or {})
        self.get_calls: list[str] = []
        self.upsert_calls: list[tuple[str, dict]] = []
        self.clear_calls: list[str] = []

    def get_snapshot(self, data_source_id: str) -> dict | None:
        self.get_calls.append(data_source_id)
        return self.snapshots.get(data_source_id)

    def upsert_snapshot(self, data_source_id: str, schema_doc: dict) -> None:
        self.upsert_calls.append((data_source_id, schema_doc))
        self.snapshots[data_source_id] = schema_doc

    def clear_snapshot(self, data_source_id: str) -> None:
        self.clear_calls.append(data_source_id)
        self.snapshots.pop(data_source_id, None)


def _schema_note_provider(_data_source_id: str):
    return [
        {
            "id": "note-table-orders",
            "content": "Core order fact table curated by analytics.",
            "metadata": {
                "schema_name": "public",
                "table_name": "orders",
            },
        },
        {
            "id": "note-column-status",
            "content": "Business status after payment reconciliation.",
            "metadata": {
                "schema_name": "public",
                "table_name": "orders",
                "column_name": "status",
            },
        },
    ]


def test_search_schema_scores_exact_column_matches_first():
    service = SchemaService()

    hits = service.search_schema(_schema_doc(), "status", limit=5)

    assert hits[0].match_type == "column"
    assert hits[0].column_name == "status"
    assert hits[0].score == 1.0


def test_get_relationships_marks_when_reference_is_in_selection():
    service = SchemaService()

    relationships = service.get_relationships(_schema_doc(), ["orders", "customers"])

    assert relationships == [
        {
            "schema": "public",
            "table": "orders",
            "column": "customer_id",
            "referred_schema": "public",
            "referred_table": "customers",
            "referred_column": "id",
            "in_selection": True,
        }
    ]


def test_get_table_info_matches_table_name_case_insensitively():
    service = SchemaService()

    table = service.get_table_info(
        {
            "schemas": [
                {
                    "name": "SALES",
                    "tables": [
                        {
                            "name": "ORDERS",
                            "comment": "",
                            "columns": [],
                            "foreign_keys": [],
                        }
                    ],
                }
            ]
        },
        "orders",
        schema="sales",
    )

    assert table["schema"] == "SALES"
    assert table["name"] == "ORDERS"


def test_get_relationships_matches_selection_case_insensitively():
    service = SchemaService()

    relationships = service.get_relationships(
        {
            "schemas": [
                {
                    "name": "SALES",
                    "tables": [
                        {
                            "name": "ORDERS",
                            "comment": "",
                            "columns": [],
                            "foreign_keys": [
                                {
                                    "column": "CUSTOMER_ID",
                                    "referred_schema": "SALES",
                                    "referred_table": "CUSTOMERS",
                                    "referred_column": "ID",
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        ["orders", "customers"],
    )

    assert relationships[0]["in_selection"] is True


def test_get_cached_schema_reads_persisted_snapshot_and_warms_memory_cache():
    snapshot_store = StubSnapshotStore({"sales-db": _schema_doc()})
    service = SchemaService(snapshot_store=snapshot_store)

    cached = service.get_cached_schema("sales-db")

    assert cached == _schema_doc()
    assert snapshot_store.get_calls == ["sales-db"]
    assert service.get_cached_schema("sales-db") == _schema_doc()
    assert snapshot_store.get_calls == ["sales-db"]


def test_get_schema_persists_fetched_snapshot():
    snapshot_store = StubSnapshotStore()
    service = SchemaService(snapshot_store=snapshot_store)
    config = _build_config()

    class StubAdapter:
        def get_schema(self, *, schema_whitelist=None, table_whitelist=None):
            assert schema_whitelist == ["public"]
            assert table_whitelist == ["orders"]
            return _schema_doc()

    schema_doc = service.get_schema(StubAdapter(), config, force_refresh=True)

    assert schema_doc == _schema_doc()
    assert snapshot_store.upsert_calls == [(config.id, _schema_doc())]


def test_clear_cache_clears_persisted_snapshot():
    snapshot_store = StubSnapshotStore({"sales-db": _schema_doc()})
    service = SchemaService(snapshot_store=snapshot_store)
    service.get_cached_schema("sales-db")

    service.clear_cache("sales-db")

    assert snapshot_store.clear_calls == ["sales-db"]
    assert service.get_cached_schema("sales-db") is None


def test_get_cached_schema_applies_user_schema_notes():
    snapshot_store = StubSnapshotStore({"sales-db": _schema_doc()})
    service = SchemaService(
        snapshot_store=snapshot_store,
        schema_note_provider=_schema_note_provider,
    )

    cached = service.get_cached_schema("sales-db")

    assert cached is not None
    orders = cached["schemas"][0]["tables"][0]
    assert orders["comment"] == "Core order fact table curated by analytics."
    assert orders["source_comment"] == "Customer orders"
    assert orders["user_comment"] == "Core order fact table curated by analytics."
    assert orders["comment_source"] == "user"
    assert orders["note_item_id"] == "note-table-orders"
    status_column = orders["columns"][1]
    assert status_column["comment"] == "Business status after payment reconciliation."
    assert status_column["source_comment"] == "Order status"
    assert status_column["user_comment"] == "Business status after payment reconciliation."
    assert status_column["comment_source"] == "user"
