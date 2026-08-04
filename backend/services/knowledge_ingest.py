from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ..models_db import KnowledgeChunk, KnowledgeDocument

PDF_BACKEND = "none"

try:
    from pypdf import PdfReader

    PDF_BACKEND = "pypdf"
except ImportError:
    try:
        from PyPDF2 import PdfReader

        PDF_BACKEND = "PyPDF2"
    except ImportError:
        PdfReader = None


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
KNOWLEDGE_SOURCE_DIR = DATA_DIR / "knowledge_sources"
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 120


def ensure_knowledge_dirs() -> None:
    KNOWLEDGE_SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def resolve_source_path(source_path: str) -> Path:
    raw_path = Path(source_path)
    if not raw_path.is_absolute():
        raw_path = ROOT_DIR / raw_path
    return raw_path.resolve()


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def get_pdf_backend_name() -> str:
    return PDF_BACKEND


def extract_pdf_text(path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError("Current environment is missing PDF parser support. Install pypdf or PyPDF2.")

    reader = PdfReader(str(path))
    pages: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        pages.append(f"# Page {index}\n{page_text}")
    return "\n\n".join(pages).strip()


def read_source_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return extract_pdf_text(path)
    return read_text_file(path)


def persist_inline_document(name: str, content: str) -> Path:
    ensure_knowledge_dirs()
    safe_name = re.sub(r"[^\w\-\u4e00-\u9fff\.]+", "-", name).strip("-") or "knowledge-doc"
    if "." not in safe_name:
        safe_name += ".md"
    target = KNOWLEDGE_SOURCE_DIR / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{safe_name}"
    target.write_text(content, encoding="utf-8")
    return target


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize_text(text: str) -> list[str]:
    tokens: list[str] = []
    lowered = text.lower()
    for match in re.finditer(r"[a-z0-9_]+|[\u4e00-\u9fff]+", lowered):
        fragment = match.group(0)
        if re.fullmatch(r"[a-z0-9_]+", fragment):
            tokens.append(fragment)
            continue
        if len(fragment) == 1:
            tokens.append(fragment)
            continue
        tokens.extend(fragment[index : index + 2] for index in range(len(fragment) - 1))
    return tokens


def build_sparse_embedding(text: str) -> dict[str, float]:
    tokens = tokenize_text(text)
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = sum(counts.values())
    norm = math.sqrt(sum((value / total) ** 2 for value in counts.values()))
    if norm == 0:
        return {}
    return {token: round((value / total) / norm, 8) for token, value in counts.items()}


def estimate_token_length(text: str) -> int:
    return max(1, len(tokenize_text(text)))


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "Untitled Section"
    buffer: list[str] = []

    for line in text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            if buffer:
                sections.append((current_title, "\n".join(buffer).strip()))
                buffer = []
            current_title = heading.group(2).strip()
            continue
        buffer.append(line)

    if buffer:
        sections.append((current_title, "\n".join(buffer).strip()))

    return [(title, content) for title, content in sections if content]


def split_section_into_chunks(section_title: str, content: str, chunk_size: int, overlap: int) -> list[dict]:
    normalized = clean_text(content)
    if not normalized:
        return []

    chunks: list[dict] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk_text = normalized[start:end].strip()
        if chunk_text:
            chunks.append({"section_title": section_title, "content": chunk_text})
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_document_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict]:
    normalized = clean_text(text)
    sections = split_markdown_sections(normalized)
    if not sections:
        sections = [("Body", normalized)]

    chunks: list[dict] = []
    for section_title, content in sections:
        chunks.extend(split_section_into_chunks(section_title, content, chunk_size, overlap))
    return chunks


def create_document_record(
    db: Session,
    *,
    name: str | None,
    document_type: str,
    source_path: str | None,
    content: str | None,
    summary: str | None,
) -> KnowledgeDocument:
    if not source_path and not content:
        raise ValueError("source_path and content cannot both be empty.")

    ensure_knowledge_dirs()
    if content is not None:
        if not name:
            name = "inline-knowledge-doc.md"
        stored_path = persist_inline_document(name, content)
        final_name = name
        final_source_path = str(stored_path)
    else:
        resolved = resolve_source_path(source_path or "")
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(f"Knowledge document not found: {resolved}")
        final_name = name or resolved.name
        final_source_path = str(resolved)

    document = KnowledgeDocument(
        name=final_name,
        type=document_type,
        source_path=final_source_path,
        status="uploaded",
        summary=(summary or "").strip(),
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def index_document(db: Session, document: KnowledgeDocument) -> tuple[KnowledgeDocument, int]:
    source_path = Path(document.source_path)
    raw_text = read_source_text(source_path)
    chunks = extract_document_chunks(raw_text)

    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).delete()

    for index, chunk in enumerate(chunks):
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=index,
                section_title=chunk["section_title"],
                content=chunk["content"],
                token_length=estimate_token_length(chunk["content"]),
                embedding_json=build_sparse_embedding(chunk["content"]),
            )
        )

    document.status = "indexed"
    if not document.summary:
        document.summary = clean_text(raw_text)[:200]
    document.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(document)
    return document, len(chunks)


def rebuild_index(db: Session, document_type: str | None = None) -> dict[str, int]:
    query = db.query(KnowledgeDocument)
    if document_type:
        query = query.filter(KnowledgeDocument.type == document_type)
    documents = query.all()
    total_chunks = 0
    for document in documents:
        _, chunk_count = index_document(db, document)
        total_chunks += chunk_count
    return {"document_count": len(documents), "chunk_count": total_chunks}


def collect_knowledge_stats(db: Session) -> dict[str, int]:
    documents = db.query(KnowledgeDocument).all()
    chunks = db.query(KnowledgeChunk).all()
    return {
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "indexed_document_count": sum(1 for item in documents if item.status == "indexed"),
        "uploaded_document_count": sum(1 for item in documents if item.status == "uploaded"),
        "failed_document_count": sum(1 for item in documents if item.status == "failed"),
        "system_doc_count": sum(1 for item in documents if item.type == "system_doc"),
        "paper_count": sum(1 for item in documents if item.type == "paper"),
    }


def collect_knowledge_diagnostics(db: Session) -> dict:
    issues: list[dict] = []
    documents = db.query(KnowledgeDocument).all()

    for document in documents:
        chunk_count = db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).count()
        source_exists = Path(document.source_path).exists()

        if not source_exists:
            issues.append(
                {
                    "issue_type": "missing_source",
                    "severity": "error",
                    "document_id": document.id,
                    "document_name": document.name,
                    "document_type": document.type,
                    "status": document.status,
                    "chunk_count": chunk_count,
                    "source_path": document.source_path,
                    "message": "Document source file no longer exists on disk.",
                }
            )

        if document.status != "indexed":
            issues.append(
                {
                    "issue_type": "not_indexed",
                    "severity": "warning",
                    "document_id": document.id,
                    "document_name": document.name,
                    "document_type": document.type,
                    "status": document.status,
                    "chunk_count": chunk_count,
                    "source_path": document.source_path,
                    "message": "Document has not completed indexing.",
                }
            )

        if document.status == "indexed" and chunk_count == 0:
            issues.append(
                {
                    "issue_type": "empty_index",
                    "severity": "error",
                    "document_id": document.id,
                    "document_name": document.name,
                    "document_type": document.type,
                    "status": document.status,
                    "chunk_count": chunk_count,
                    "source_path": document.source_path,
                    "message": "Indexed document has zero chunks.",
                }
            )

        if document.status == "indexed" and not (document.summary or "").strip():
            issues.append(
                {
                    "issue_type": "missing_summary",
                    "severity": "warning",
                    "document_id": document.id,
                    "document_name": document.name,
                    "document_type": document.type,
                    "status": document.status,
                    "chunk_count": chunk_count,
                    "source_path": document.source_path,
                    "message": "Indexed document is missing summary text.",
                }
            )

    return {
        "pdf_backend": get_pdf_backend_name(),
        "issue_count": len(issues),
        "issues": issues,
    }
