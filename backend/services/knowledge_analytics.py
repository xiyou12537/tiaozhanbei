from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models_db import ChatReference, KnowledgeChunk, KnowledgeDocument


def collect_reference_analytics(db: Session, *, limit: int = 10) -> dict:
    references = (
        db.query(ChatReference, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == ChatReference.document_id)
        .order_by(ChatReference.created_at.desc(), ChatReference.id.desc())
        .all()
    )

    aggregated: dict[int, dict] = {}
    for reference, document in references:
        item = aggregated.setdefault(
            document.id,
            {
                "document_id": document.id,
                "document_name": document.name,
                "document_type": document.type,
                "reference_count": 0,
                "score_total": 0.0,
                "last_referenced_at": "",
            },
        )
        item["reference_count"] += 1
        item["score_total"] += float(reference.score or 0.0)
        created_at = reference.created_at.isoformat() if reference.created_at else ""
        if created_at and created_at > item["last_referenced_at"]:
            item["last_referenced_at"] = created_at

    top_documents = []
    for item in aggregated.values():
        avg_score = item["score_total"] / item["reference_count"] if item["reference_count"] else 0.0
        top_documents.append(
            {
                "document_id": item["document_id"],
                "document_name": item["document_name"],
                "document_type": item["document_type"],
                "reference_count": item["reference_count"],
                "avg_score": round(avg_score, 6),
                "last_referenced_at": item["last_referenced_at"],
            }
        )

    top_documents.sort(
        key=lambda item: (item["reference_count"], item["avg_score"], item["last_referenced_at"]),
        reverse=True,
    )
    top_documents = top_documents[:limit]

    referenced_ids = set(aggregated.keys())
    indexed_documents = db.query(KnowledgeDocument).filter(KnowledgeDocument.status == "indexed").all()
    unreferenced_indexed_document_count = sum(1 for item in indexed_documents if item.id not in referenced_ids)

    return {
        "total_reference_count": len(references),
        "referenced_document_count": len(referenced_ids),
        "unreferenced_indexed_document_count": unreferenced_indexed_document_count,
        "top_documents": top_documents,
    }
