from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .knowledge_service import KnowledgeService
    from .registry import DataSourceRegistry
    from .retrieval_service import RetrievalService
    from .service import DatabaseService
    from .session import ThreadSessionStore


def get_data_source_registry():
    from .registry import get_data_source_registry as _get_data_source_registry

    return _get_data_source_registry()


def get_database_service():
    from .service import get_database_service as _get_database_service

    return _get_database_service()


def get_knowledge_service():
    from .knowledge_service import get_knowledge_service as _get_knowledge_service

    return _get_knowledge_service()


def get_retrieval_service():
    from .retrieval_service import get_retrieval_service as _get_retrieval_service

    return _get_retrieval_service()


def get_session_store():
    from .session import get_session_store as _get_session_store

    return _get_session_store()


def reset_data_source_registry():
    from .registry import _reset_data_source_registry

    _reset_data_source_registry()


def reset_database_service():
    from .service import _reset_database_service

    _reset_database_service()


def reset_knowledge_service():
    from .knowledge_service import _reset_knowledge_service

    _reset_knowledge_service()


def reset_retrieval_service():
    from .retrieval_service import _reset_retrieval_service

    _reset_retrieval_service()


def reset_session_store():
    from .session import _reset_session_store

    _reset_session_store()

__all__ = [
    "DataSourceRegistry",
    "KnowledgeService",
    "RetrievalService",
    "DatabaseService",
    "ThreadSessionStore",
    "get_data_source_registry",
    "get_database_service",
    "get_knowledge_service",
    "get_retrieval_service",
    "get_session_store",
    "reset_data_source_registry",
    "reset_database_service",
    "reset_knowledge_service",
    "reset_retrieval_service",
    "reset_session_store",
]
