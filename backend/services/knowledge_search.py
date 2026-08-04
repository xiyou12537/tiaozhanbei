from __future__ import annotations

import math
from collections import Counter

from sqlalchemy.orm import Session

from ..models_db import KnowledgeChunk, KnowledgeDocument
from .knowledge_ingest import tokenize_text

OPERATIONAL_HINTS = (
    "怎么",
    "如何",
    "步骤",
    "参数",
    "页面",
    "上传",
    "导出",
    "历史",
    "任务",
    "系统",
    "平台",
)


def infer_preferred_document_type(query: str) -> str | None:
    lowered = query.lower()
    if any(keyword in query for keyword in OPERATIONAL_HINTS):
        return "system_doc"
    if "paper" in lowered or "论文" in query:
        return "paper"
    return None


def build_query_weights(query: str) -> dict[str, float]:
    tokens = tokenize_text(query)
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = sum(counts.values())
    norm = math.sqrt(sum((value / total) ** 2 for value in counts.values()))
    if norm == 0:
        return {}
    return {token: (value / total) / norm for token, value in counts.items()}


def cosine_sparse_score(query_weights: dict[str, float], chunk_weights: dict[str, float]) -> float:
    if not query_weights or not chunk_weights:
        return 0.0
    return sum(query_weights[token] * chunk_weights.get(token, 0.0) for token in query_weights)


def search_knowledge(
    db: Session,
    *,
    query: str,
    top_k: int = 5,
    document_type: str | None = None,
) -> list[dict]:
    preferred_type = document_type or infer_preferred_document_type(query)
    rows = (
        db.query(KnowledgeChunk, KnowledgeDocument)
        .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
        .filter(KnowledgeDocument.status == "indexed")
        .all()
    )

    query_weights = build_query_weights(query)
    hits: list[dict] = []
    for chunk, document in rows:
        if preferred_type and document.type != preferred_type:
            continue
        score = cosine_sparse_score(query_weights, chunk.embedding_json or {})
        if score <= 0:
            continue
        hits.append(
            {
                "chunk_id": chunk.id,
                "document_id": document.id,
                "document_name": document.name,
                "document_type": document.type,
                "section_title": chunk.section_title or "",
                "content": chunk.content,
                "score": round(float(score), 6),
            }
        )

    if not hits and preferred_type is not None:
        return search_knowledge(db, query=query, top_k=top_k, document_type=None)

    hits.sort(key=lambda item: item["score"], reverse=True)
    return hits[:top_k]
