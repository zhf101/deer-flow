from deerflow.nlp2sql import (
    get_data_source_registry,
    get_database_service,
    get_session_store,
    reset_data_source_registry,
    reset_database_service,
    reset_session_store,
)


def test_singleton_reset_helpers_replace_instances():
    registry_a = get_data_source_registry()
    service_a = get_database_service()
    session_store_a = get_session_store()

    reset_data_source_registry()
    reset_database_service()
    reset_session_store()

    registry_b = get_data_source_registry()
    service_b = get_database_service()
    session_store_b = get_session_store()

    assert registry_a is not registry_b
    assert service_a is not service_b
    assert session_store_a is not session_store_b
