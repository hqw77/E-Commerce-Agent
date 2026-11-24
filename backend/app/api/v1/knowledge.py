"""知识库 API.

上传/发布/删除属于管理端操作, 列表/详情/检索属于用户端操作.
文档内容会进入 RAG 链路, 但本层只负责文件接收和协议转换, 解析, 切分, 向量化
和权限过滤由 KnowledgeDocumentService/KnowledgeRetrievalService 负责.
"""

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
    """把文档及其版本列表组装成详情响应."""
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
    """按当前配置组装文档服务, 复用 Embedding 和 Qdrant 运行时组件."""
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
    """上传知识文档. 只有管理员可以调用, 文件大小和类型由 Service 校验."""
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
    """分页查询当前用户可见的知识文档, PUBLIC/ADMIN_ONLY 由 Service 过滤."""
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
    """查看文档详情, 无权限或不存在的文档统一按 404 处理."""
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
    """上传文档的新版本. 旧发布版本不会被新版本自动替换, 需要显式发布."""
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
    """查看单个版本的处理状态和元数据."""
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
    """发布一个已完成索引的版本. 发布后该版本成为检索可见版本."""
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
    """重试失败的版本处理. 只有失败状态允许重试."""
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
    """删除文档. 软删除/关联数据清理由 Service 统一处理."""
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
    """检索知识片段. 返回原始 Top-K, 无答案策略只在 Agent 边界执行."""
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
