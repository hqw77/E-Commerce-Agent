from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentAdmin, CurrentUser
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.knowledge import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentResponse,
    RetrievalRequest,
    RetrievalResponse,
    VersionResponse,
)
from app.services.rag.document_service import KnowledgeDocumentService
from app.services.rag.retrieval_service import KnowledgeRetrievalService
from app.services.rag.runtime import (
    get_chunker,
    get_embedding_provider,
    get_vector_store,
)

router = APIRouter()

DocumentVisibilityParam = Literal["PUBLIC", "ADMIN_ONLY"]
DocumentStatusParam = Literal["ACTIVE", "ARCHIVED", "DELETED"]


def _document_detail(document: object) -> DocumentDetailResponse:
    base = DocumentResponse.model_validate(document)
    versions = [
        VersionResponse.model_validate(version)
        for version in getattr(document, "versions", [])
    ]
    return DocumentDetailResponse(
        **base.model_dump(),
        versions=versions,
    )


def _document_service(session: AsyncSession) -> KnowledgeDocumentService:
    settings = get_settings()
    return KnowledgeDocumentService(
        session,
        settings,
        chunker=get_chunker(settings),
        embedding=get_embedding_provider(settings),
        vector_store=get_vector_store(settings),
    )


@router.post(
    "/documents",
    response_model=DocumentDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a knowledge document",
)
async def upload_document(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    description: Annotated[str | None, Form()] = None,
    visibility: Annotated[DocumentVisibilityParam, Form()] = "PUBLIC",
) -> DocumentDetailResponse:
    content = await file.read()
    service = _document_service(session)
    document = await service.create_document(
        user=admin,
        title=title,
        description=description,
        visibility=visibility,
        original_filename=file.filename or "document",
        content=content,
    )
    return _document_detail(document)


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List knowledge documents",
)
async def list_documents(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: Annotated[str | None, Query(max_length=255)] = None,
    status_filter: Annotated[
        DocumentStatusParam | None,
        Query(alias="status"),
    ] = None,
    visibility: Annotated[DocumentVisibilityParam | None, Query()] = None,
) -> DocumentListResponse:
    service = _document_service(session)
    items, total = await service.list_documents(
        user=user,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status_filter,
        visibility=visibility,
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get knowledge document detail",
)
async def get_document(
    document_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> DocumentDetailResponse:
    service = _document_service(session)
    document = await service.get_document(user=user, document_id=document_id)
    return _document_detail(document)


@router.post(
    "/documents/{document_id}/versions",
    response_model=DocumentDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document version",
)
async def upload_version(
    document_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
    file: Annotated[UploadFile, File()],
) -> DocumentDetailResponse:
    content = await file.read()
    service = _document_service(session)
    document = await service.create_version(
        user=admin,
        document_id=document_id,
        original_filename=file.filename or "document",
        content=content,
    )
    return _document_detail(document)


@router.get(
    "/documents/{document_id}/versions/{version_id}",
    response_model=VersionResponse,
    summary="Get a document version",
)
async def get_version(
    document_id: Annotated[int, Path(ge=1)],
    version_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> VersionResponse:
    service = _document_service(session)
    version = await service.get_version(
        user=user,
        document_id=document_id,
        version_id=version_id,
    )
    return VersionResponse.model_validate(version)


@router.post(
    "/documents/{document_id}/versions/{version_id}/publish",
    response_model=VersionResponse,
    summary="Publish an indexed document version",
)
async def publish_version(
    document_id: Annotated[int, Path(ge=1)],
    version_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> VersionResponse:
    service = _document_service(session)
    version = await service.publish_version(
        user=admin,
        document_id=document_id,
        version_id=version_id,
    )
    return VersionResponse.model_validate(version)


@router.post(
    "/documents/{document_id}/versions/{version_id}/retry",
    response_model=VersionResponse,
    summary="Retry a failed version",
)
async def retry_version(
    document_id: Annotated[int, Path(ge=1)],
    version_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> VersionResponse:
    service = _document_service(session)
    version = await service.retry_version(
        user=admin,
        document_id=document_id,
        version_id=version_id,
    )
    return VersionResponse.model_validate(version)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a knowledge document",
)
async def delete_document(
    document_id: Annotated[int, Path(ge=1)],
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: CurrentAdmin,
) -> None:
    service = _document_service(session)
    await service.delete_document(user=admin, document_id=document_id)


@router.post(
    "/retrieve",
    response_model=RetrievalResponse,
    summary="Retrieve knowledge chunks",
)
async def retrieve(
    request: RetrievalRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
) -> RetrievalResponse:
    service = KnowledgeRetrievalService(
        session,
        get_settings(),
        embedding=get_embedding_provider(get_settings()),
        vector_store=get_vector_store(get_settings()),
    )
    items = await service.retrieve(
        user=user,
        query=request.query,
        top_k=request.top_k,
    )
    return RetrievalResponse(items=items, total=len(items))
