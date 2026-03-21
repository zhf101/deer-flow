import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from deerflow.nlp2sql.errors import DataSourceAlreadyExistsError, DataSourceNotFoundError
from deerflow.nlp2sql.registry import get_data_source_registry
from deerflow.nlp2sql.service import get_database_service
from deerflow.nlp2sql.types import DataSourceConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/nlp2sql", tags=["nlp2sql"])


class DataSourcesResponse(BaseModel):
    data_sources: list[DataSourceConfig]


class ConnectionTestResponse(BaseModel):
    ok: bool
    data_source_id: str
    message: str


class SchemaCacheClearResponse(BaseModel):
    ok: bool
    data_source_id: str
    message: str


@router.get(
    "/data-sources",
    response_model=DataSourcesResponse,
    summary="List Data Sources",
    description="List configured nlp2sql data sources.",
)
async def list_data_sources(enabled_only: bool = Query(default=False)) -> DataSourcesResponse:
    try:
        data_sources = get_data_source_registry().list(enabled_only=enabled_only)
        return DataSourcesResponse(data_sources=data_sources)
    except Exception as e:
        logger.error("Failed to list data sources: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list data sources: {e}")


@router.get(
    "/data-sources/{data_source_id}",
    response_model=DataSourceConfig,
    summary="Get Data Source",
    description="Get one configured data source by ID.",
)
async def get_data_source(data_source_id: str) -> DataSourceConfig:
    try:
        return get_data_source_registry().get(data_source_id)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get data source %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get data source: {e}")


@router.post(
    "/data-sources",
    response_model=DataSourceConfig,
    status_code=201,
    summary="Create Data Source",
    description="Create a data source configuration for nlp2sql.",
)
async def create_data_source(request: DataSourceConfig) -> DataSourceConfig:
    try:
        return get_data_source_registry().create(request)
    except DataSourceAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to create data source %s: %s", request.id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create data source: {e}")


@router.put(
    "/data-sources/{data_source_id}",
    response_model=DataSourceConfig,
    summary="Update Data Source",
    description="Update an existing data source configuration.",
)
async def update_data_source(data_source_id: str, request: DataSourceConfig) -> DataSourceConfig:
    if request.id != data_source_id:
        raise HTTPException(status_code=422, detail="Path data_source_id must match request.id")
    try:
        return get_data_source_registry().upsert(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to update data source %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update data source: {e}")


@router.delete(
    "/data-sources/{data_source_id}",
    status_code=204,
    summary="Delete Data Source",
    description="Delete a configured data source.",
)
async def delete_data_source(data_source_id: str) -> None:
    try:
        get_data_source_registry().delete(data_source_id)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete data source %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete data source: {e}")


@router.post(
    "/data-sources/{data_source_id}/test",
    response_model=ConnectionTestResponse,
    summary="Test Data Source Connection",
    description="Test that the configured data source can connect successfully.",
)
async def test_data_source(data_source_id: str) -> ConnectionTestResponse:
    try:
        payload = get_data_source_registry().test_connection(data_source_id)
        return ConnectionTestResponse(**payload)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to test data source %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test data source: {e}")


@router.delete(
    "/data-sources/{data_source_id}/schema-cache",
    response_model=SchemaCacheClearResponse,
    summary="Clear Schema Cache",
    description="Clear cached schema metadata for one data source.",
)
async def clear_schema_cache(data_source_id: str) -> SchemaCacheClearResponse:
    try:
        get_data_source_registry().get(data_source_id)
        get_database_service().clear_schema_cache(data_source_id)
        return SchemaCacheClearResponse(
            ok=True,
            data_source_id=data_source_id,
            message=f"Cleared schema cache for '{data_source_id}'",
        )
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to clear schema cache for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to clear schema cache: {e}")
