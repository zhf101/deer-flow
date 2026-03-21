from deerflow.nlp2sql.schema.service import SchemaService


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
