from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware import get_current_user
from ..models import (
    KnowledgeAnalyticsDocumentResponse,
    KnowledgeAnalyticsResponse,
    KnowledgeDiagnosticsResponse,
    KnowledgeDocumentCreateRequest,
    KnowledgeDocumentResponse,
    KnowledgeImportDirectoryRequest,
    KnowledgeImportDirectoryResponse,
    KnowledgeIndexResponse,
    KnowledgeRebuildRequest,
    KnowledgeRebuildResponse,
    KnowledgeSearchHitResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeStatsResponse,
)
from ..models_db import ChatReference, KnowledgeChunk, KnowledgeDocument, User
from ..services.knowledge_analytics import collect_reference_analytics
from ..services.knowledge_bootstrap import import_documents_from_directory
from ..services.knowledge_ingest import (
    collect_knowledge_diagnostics,
    collect_knowledge_stats,
    create_document_record,
    index_document,
    rebuild_index,
)
from ..services.knowledge_search import search_knowledge

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


def _serialize_document(document: KnowledgeDocument, db: Session) -> KnowledgeDocumentResponse:
    chunk_count = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).count()
    return KnowledgeDocumentResponse(
        id=document.id,
        name=document.name,
        document_type=document.type,
        source_path=document.source_path,
        status=document.status,
        summary=document.summary or "",
        chunk_count=chunk_count,
        created_at=document.created_at.isoformat() if document.created_at else "",
        updated_at=document.updated_at.isoformat() if document.updated_at else "",
    )


@router.post("/documents", response_model=KnowledgeDocumentResponse)
def create_document(
    body: KnowledgeDocumentCreateRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        document = create_document_record(
            db,
            name=body.name,
            document_type=body.document_type,
            source_path=body.source_path,
            content=body.content,
            summary=body.summary,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _serialize_document(document, db)


@router.post("/import-directory", response_model=KnowledgeImportDirectoryResponse)
def import_directory(
    body: KnowledgeImportDirectoryRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = import_documents_from_directory(
            db,
            directory_path=body.directory_path,
            document_type=body.document_type,
            recursive=body.recursive,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return KnowledgeImportDirectoryResponse(status="ok", **result)


@router.post("/documents/{document_id}/index", response_model=KnowledgeIndexResponse)
def index_single_document(
    document_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="知识文档不存在。")
    try:
        indexed_document, chunk_count = index_document(db, document)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return KnowledgeIndexResponse(
        document_id=indexed_document.id,
        status=indexed_document.status,
        chunk_count=chunk_count,
    )


@router.get("/documents", response_model=list[KnowledgeDocumentResponse])
def list_documents(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    documents = db.query(KnowledgeDocument).order_by(KnowledgeDocument.updated_at.desc()).all()
    return [_serialize_document(document, db) for document in documents]


@router.get("/stats", response_model=KnowledgeStatsResponse)
def get_stats(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return KnowledgeStatsResponse(**collect_knowledge_stats(db))


@router.get("/diagnostics", response_model=KnowledgeDiagnosticsResponse)
def get_diagnostics(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return KnowledgeDiagnosticsResponse(**collect_knowledge_diagnostics(db))


@router.get("/analytics", response_model=KnowledgeAnalyticsResponse)
def get_analytics(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = collect_reference_analytics(db)
    return KnowledgeAnalyticsResponse(
        total_reference_count=result["total_reference_count"],
        referenced_document_count=result["referenced_document_count"],
        unreferenced_indexed_document_count=result["unreferenced_indexed_document_count"],
        top_documents=[KnowledgeAnalyticsDocumentResponse(**item) for item in result["top_documents"]],
    )


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
    if document is None:
        raise HTTPException(status_code=404, detail="知识文档不存在。")
    chunk_ids = [item.id for item in db.query(KnowledgeChunk.id).filter(KnowledgeChunk.document_id == document_id).all()]
    if chunk_ids:
        db.query(ChatReference).filter(ChatReference.chunk_id.in_(chunk_ids)).delete(synchronize_session=False)
    db.query(ChatReference).filter(ChatReference.document_id == document_id).delete(synchronize_session=False)
    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document_id).delete(synchronize_session=False)
    db.delete(document)
    db.commit()
    return {"status": "ok", "message": "知识文档已删除。"}


@router.post("/rebuild", response_model=KnowledgeRebuildResponse)
def rebuild_documents(
    body: KnowledgeRebuildRequest | None = None,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document_type = body.document_type if body else None
    try:
        result = rebuild_index(db, document_type=document_type)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return KnowledgeRebuildResponse(status="ok", document_type=document_type, **result)


@router.post("/search", response_model=KnowledgeSearchResponse)
def debug_search(
    body: KnowledgeSearchRequest,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hits = search_knowledge(db, query=body.query, top_k=body.top_k, document_type=body.document_type)
    return KnowledgeSearchResponse(
        query=body.query,
        hits=[KnowledgeSearchHitResponse(**item) for item in hits],
    )
