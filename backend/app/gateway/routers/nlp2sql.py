import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from deerflow.nlp2sql.errors import DataSourceAlreadyExistsError, DataSourceNotFoundError
from deerflow.nlp2sql.knowledge_service import get_knowledge_service
from deerflow.nlp2sql.knowledge_types import (
    EmbeddingProfile,
    EmbeddingProfileCreate,
    EmbeddingProfilesResponse,
    EmbeddingRebuildRequest,
    HistoricalSqlImportRequest,
    IndexJob,
    IndexJobsResponse,
    KnowledgeFilesResponse,
    KnowledgeItem,
    KnowledgeItemCreate,
    KnowledgeItemsResponse,
    KnowledgeItemType,
    KnowledgeItemUpdate,
    RetrievalPreviewRequest,
    RetrievalPreviewResponse,
)
from deerflow.nlp2sql.registry import get_data_source_registry
from deerflow.nlp2sql.retrieval_service import get_retrieval_service
from deerflow.nlp2sql.service import get_database_service
from deerflow.nlp2sql.types import (
    DataSourceConfig,
    SchemaCommentUpsertRequest,
    SchemaCommentUpsertResponse,
    SchemaDocument,
)

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


class EmbeddingProfileActivateResponse(BaseModel):
    ok: bool
    embedding_profile: EmbeddingProfile


class IndexJobResponse(BaseModel):
    index_job: IndexJob


def _safe_upload_filename(raw_name: str) -> str:
    file_name = Path(raw_name).name
    if not file_name or file_name in {".", ".."} or "/" in file_name or "\\" in file_name:
        raise ValueError(f"Invalid file name: {raw_name!r}")
    return file_name


def _clear_schema_cache_best_effort(data_source_id: str) -> None:
    try:
        get_database_service().clear_schema_cache(data_source_id)
    except Exception:
        logger.warning("Failed to clear schema cache for %s during data-source mutation", data_source_id, exc_info=True)


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
        created = get_data_source_registry().create(request)
        _clear_schema_cache_best_effort(request.id)
        return created
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
        updated = get_data_source_registry().upsert(request)
        _clear_schema_cache_best_effort(data_source_id)
        return updated
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
        _clear_schema_cache_best_effort(data_source_id)
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


@router.get(
    "/data-sources/{data_source_id}/schema",
    response_model=SchemaDocument,
    summary="Get Data Source Schema",
    description="Return the merged schema view for one data source, including user-authored table and column comments.",
)
async def get_data_source_schema(
    data_source_id: str,
    force_refresh: bool = Query(default=False),
) -> SchemaDocument:
    try:
        get_data_source_registry().get(data_source_id)
        schema_doc = get_database_service().get_schema(data_source_id, force_refresh=force_refresh)
        return SchemaDocument.model_validate(schema_doc)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to load schema for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load schema: {e}")


@router.put(
    "/data-sources/{data_source_id}/schema-comments",
    response_model=SchemaCommentUpsertResponse,
    summary="Upsert Schema Comment",
    description="Create, update, or clear a user-authored table or column comment for one data source.",
)
async def upsert_schema_comment(
    data_source_id: str,
    request: SchemaCommentUpsertRequest,
) -> SchemaCommentUpsertResponse:
    try:
        get_data_source_registry().get(data_source_id)
        action, item = get_knowledge_service().upsert_schema_comment(
            data_source_id,
            schema_name=request.schema_name,
            table_name=request.table_name,
            column_name=request.column_name,
            comment=request.comment,
        )
        target = ".".join(
            part
            for part in [request.schema_name, request.table_name, request.column_name]
            if part
        )
        if action == "deleted":
            message = f"Cleared schema comment for '{target}'"
        elif action == "noop":
            message = f"No schema comment to clear for '{target}'"
        elif action == "created":
            message = f"Created schema comment for '{target}'"
        else:
            message = f"Updated schema comment for '{target}'"
        return SchemaCommentUpsertResponse(
            ok=True,
            data_source_id=data_source_id,
            action=action,
            message=message,
            note_item_id=item.id if item is not None else None,
        )
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to save schema comment for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save schema comment: {e}")


@router.get(
    "/data-sources/{data_source_id}/index-jobs",
    response_model=IndexJobsResponse,
    summary="List Index Jobs",
    description="List indexing and rebuild jobs for one nlp2sql data source.",
)
async def list_index_jobs(data_source_id: str) -> IndexJobsResponse:
    try:
        get_data_source_registry().get(data_source_id)
        jobs = get_knowledge_service().list_index_jobs(data_source_id)
        return IndexJobsResponse(index_jobs=jobs)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to list index jobs for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list index jobs: {e}")


@router.get(
    "/data-sources/{data_source_id}/index-jobs/{job_id}",
    response_model=IndexJobResponse,
    summary="Get Index Job",
    description="Get one indexing or rebuild job by ID.",
)
async def get_index_job(data_source_id: str, job_id: str) -> IndexJobResponse:
    try:
        get_data_source_registry().get(data_source_id)
        job = get_knowledge_service().get_index_job(data_source_id, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Index job '{job_id}' not found")
        return IndexJobResponse(index_job=job)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get index job %s for %s: %s", job_id, data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get index job: {e}")


@router.get(
    "/data-sources/{data_source_id}/knowledge-items",
    response_model=KnowledgeItemsResponse,
    summary="List Knowledge Items",
    description="List trainable knowledge items for one nlp2sql data source.",
)
async def list_knowledge_items(
    data_source_id: str,
    item_type: KnowledgeItemType | None = Query(default=None),
    query: str | None = Query(default=None),
) -> KnowledgeItemsResponse:
    try:
        get_data_source_registry().get(data_source_id)
        items = get_knowledge_service().list_items(
            data_source_id,
            item_type=item_type,
            query=query,
        )
        return KnowledgeItemsResponse(knowledge_items=items)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to list knowledge items for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list knowledge items: {e}")


@router.post(
    "/data-sources/{data_source_id}/knowledge-items",
    response_model=KnowledgeItem,
    status_code=201,
    summary="Create Knowledge Item",
    description="Create a trainable knowledge item for one nlp2sql data source.",
)
async def create_knowledge_item(data_source_id: str, request: KnowledgeItemCreate) -> KnowledgeItem:
    try:
        get_data_source_registry().get(data_source_id)
        return get_knowledge_service().create_item(data_source_id, request)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to create knowledge item for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create knowledge item: {e}")


@router.get(
    "/data-sources/{data_source_id}/knowledge-items/{item_id}",
    response_model=KnowledgeItem,
    summary="Get Knowledge Item",
    description="Get one trainable knowledge item by ID.",
)
async def get_knowledge_item(data_source_id: str, item_id: str) -> KnowledgeItem:
    try:
        get_data_source_registry().get(data_source_id)
        item = get_knowledge_service().get_item(data_source_id, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Knowledge item '{item_id}' not found")
        return item
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get knowledge item %s for %s: %s", item_id, data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get knowledge item: {e}")


@router.put(
    "/data-sources/{data_source_id}/knowledge-items/{item_id}",
    response_model=KnowledgeItem,
    summary="Update Knowledge Item",
    description="Update one trainable knowledge item.",
)
async def update_knowledge_item(
    data_source_id: str,
    item_id: str,
    request: KnowledgeItemUpdate,
) -> KnowledgeItem:
    try:
        get_data_source_registry().get(data_source_id)
        return get_knowledge_service().update_item(data_source_id, item_id, request)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Knowledge item '{item_id}' not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to update knowledge item %s for %s: %s", item_id, data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update knowledge item: {e}")


@router.delete(
    "/data-sources/{data_source_id}/knowledge-items/{item_id}",
    status_code=204,
    summary="Delete Knowledge Item",
    description="Delete one trainable knowledge item.",
)
async def delete_knowledge_item(data_source_id: str, item_id: str) -> None:
    try:
        get_data_source_registry().get(data_source_id)
        deleted = get_knowledge_service().delete_item(data_source_id, item_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Knowledge item '{item_id}' not found")
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete knowledge item %s for %s: %s", item_id, data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete knowledge item: {e}")


@router.get(
    "/data-sources/{data_source_id}/knowledge-files",
    response_model=KnowledgeFilesResponse,
    summary="List Knowledge Files",
    description="List uploaded file knowledge for one nlp2sql data source.",
)
async def list_knowledge_files(data_source_id: str) -> KnowledgeFilesResponse:
    try:
        get_data_source_registry().get(data_source_id)
        files = get_knowledge_service().list_files(data_source_id)
        return KnowledgeFilesResponse(knowledge_files=files)
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to list knowledge files for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list knowledge files: {e}")


@router.post(
    "/data-sources/{data_source_id}/knowledge-files",
    response_model=IndexJobsResponse,
    status_code=201,
    summary="Upload Knowledge Files",
    description="Create an asynchronous import job for one or more trainable knowledge files.",
)
async def upload_knowledge_files(
    data_source_id: str,
    files: list[UploadFile] = File(...),
) -> IndexJobsResponse:
    try:
        get_data_source_registry().get(data_source_id)
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        knowledge_service = get_knowledge_service()
        payloads: list[dict[str, object]] = []
        for upload in files:
            if not upload.filename:
                continue
            safe_name = _safe_upload_filename(upload.filename)
            content = await upload.read()
            payloads.append(
                {
                    "file_name": safe_name,
                    "content": content,
                    "mime_type": upload.content_type,
                }
            )

        job = knowledge_service.submit_file_import_job(
            data_source_id,
            files=payloads,
        )
        return IndexJobsResponse(index_jobs=[job])
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to upload knowledge files for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload knowledge files: {e}")


@router.delete(
    "/data-sources/{data_source_id}/knowledge-files/{file_id}",
    status_code=204,
    summary="Delete Knowledge File",
    description="Delete one uploaded knowledge file by its derived knowledge item id.",
)
async def delete_knowledge_file(data_source_id: str, file_id: str) -> None:
    try:
        get_data_source_registry().get(data_source_id)
        deleted = get_knowledge_service().delete_item(data_source_id, file_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Knowledge file '{file_id}' not found")
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete knowledge file %s for %s: %s", file_id, data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete knowledge file: {e}")


@router.post(
    "/data-sources/{data_source_id}/historical-sql/import",
    response_model=IndexJobsResponse,
    status_code=201,
    summary="Import Historical SQL",
    description="Create an asynchronous import job for one or more historical SQL statements.",
)
async def import_historical_sql(
    data_source_id: str,
    request: HistoricalSqlImportRequest,
) -> IndexJobsResponse:
    try:
        get_data_source_registry().get(data_source_id)
        job = get_knowledge_service().submit_historical_sql_job(
            data_source_id,
            sql_text=request.sql_text,
            source_name=request.source_name,
        )
        return IndexJobsResponse(index_jobs=[job])
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to import historical SQL for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to import historical SQL: {e}")


@router.get(
    "/embedding-profiles",
    response_model=EmbeddingProfilesResponse,
    summary="List Embedding Profiles",
    description="List configured embedding profiles for NLP2SQL knowledge indexing.",
)
async def list_embedding_profiles() -> EmbeddingProfilesResponse:
    try:
        return EmbeddingProfilesResponse(
            embedding_profiles=get_knowledge_service().list_embedding_profiles()
        )
    except Exception as e:
        logger.error("Failed to list embedding profiles: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list embedding profiles: {e}")


@router.post(
    "/embedding-profiles",
    response_model=EmbeddingProfile,
    status_code=201,
    summary="Create Embedding Profile",
    description="Create a new embedding profile for future re-indexing.",
)
async def create_embedding_profile(request: EmbeddingProfileCreate) -> EmbeddingProfile:
    try:
        return get_knowledge_service().create_embedding_profile(request)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to create embedding profile: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create embedding profile: {e}")


@router.post(
    "/embedding-profiles/{profile_id}/activate",
    response_model=EmbeddingProfileActivateResponse,
    summary="Activate Embedding Profile",
    description="Activate one embedding profile for retrieval.",
)
async def activate_embedding_profile(profile_id: str) -> EmbeddingProfileActivateResponse:
    try:
        profile = get_knowledge_service().activate_embedding_profile(profile_id)
        return EmbeddingProfileActivateResponse(ok=True, embedding_profile=profile)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Embedding profile '{profile_id}' not found")
    except Exception as e:
        logger.error("Failed to activate embedding profile %s: %s", profile_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to activate embedding profile: {e}")


@router.post(
    "/embedding-profiles/{profile_id}/rebuild",
    response_model=IndexJobsResponse,
    status_code=201,
    summary="Rebuild Embedding Profile",
    description="Queue one or more embedding rebuild jobs for a target profile.",
)
async def rebuild_embedding_profile(
    profile_id: str,
    request: EmbeddingRebuildRequest,
) -> IndexJobsResponse:
    try:
        registry = get_data_source_registry()
        knowledge_service = get_knowledge_service()

        if request.all_data_sources:
            data_sources = registry.list(enabled_only=False)
            if not data_sources:
                raise HTTPException(status_code=422, detail="No data sources are configured")
            jobs = [
                knowledge_service.submit_embedding_rebuild_job(
                    profile_id,
                    data_source_id=data_source.id,
                )
                for data_source in data_sources
            ]
            return IndexJobsResponse(index_jobs=jobs)

        if request.data_source_id is None:
            raise HTTPException(
                status_code=422,
                detail="Either data_source_id or all_data_sources=true is required",
            )
        registry.get(request.data_source_id)
        job = knowledge_service.submit_embedding_rebuild_job(
            profile_id,
            data_source_id=request.data_source_id,
        )
        return IndexJobsResponse(index_jobs=[job])
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Embedding profile '{profile_id}' not found")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to rebuild embedding profile %s: %s", profile_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to rebuild embedding profile: {e}")


@router.post(
    "/data-sources/{data_source_id}/retrieve-preview",
    response_model=RetrievalPreviewResponse,
    summary="Retrieve Preview",
    description="Preview the knowledge and schema context that would be recalled for an NLP2SQL question.",
)
async def retrieve_preview(
    data_source_id: str,
    request: RetrievalPreviewRequest,
) -> RetrievalPreviewResponse:
    try:
        get_data_source_registry().get(data_source_id)
        return get_retrieval_service().preview(
            data_source_id=data_source_id,
            query=request.query,
            limit_per_bucket=request.limit_per_bucket,
        )
    except DataSourceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Failed to preview retrieval for %s: %s", data_source_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to preview retrieval: {e}")
