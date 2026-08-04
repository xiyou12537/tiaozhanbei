from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from ..models_db import KnowledgeDocument
from .knowledge_ingest import create_document_record, index_document, resolve_source_path

ROOT_DIR = Path(__file__).resolve().parents[2]

DEFAULT_SYSTEM_DOCS = [
    ROOT_DIR / "README.md",
    ROOT_DIR / "docs" / "fe-n4c66-li2s4-benchmark-protocol.md",
    ROOT_DIR / "docs" / "fe-n4c66-li2s4-quantum-closure-protocol.md",
    ROOT_DIR / "reference" / "fe-n4c-li2s4-v1" / "README.md",
    ROOT_DIR / "修改意见" / "已完成" / "科研结构建模前后端联调说明.md",
    ROOT_DIR / "修改意见" / "已完成" / "后端-FeN4C66-Li2S4文献基准导入任务.md",
    ROOT_DIR / "修改意见" / "已完成" / "后端-科研基准案例与DFT接入整改需求.md",
    ROOT_DIR / "修改意见" / "已完成" / "前端-科研输入确认与结构驱动计算结果页需求.md",
    ROOT_DIR / "修改意见" / "已完成" / "前端-FeN4C66-Li2S4文献基准工作台需求.md",
    ROOT_DIR / "修改意见" / "待完成" / "前端-科研模型界面去工作流化改版需求.md",
    ROOT_DIR / "修改意见" / "待完成" / "后端-FeN4C66-Li2S4量子闭环基准实现需求.md",
]

DEFAULT_PAPER_DIRS = [
    ROOT_DIR / "papers",
    ROOT_DIR / "docs" / "papers",
    ROOT_DIR / "data" / "papers",
]

DOCUMENT_TYPE_EXTENSIONS = {
    "system_doc": {".md", ".txt"},
    "paper": {".pdf", ".md", ".txt"},
}


def _iter_matching_files(directory: Path, *, recursive: bool, extensions: set[str]) -> list[Path]:
    if recursive:
        candidates = directory.rglob("*")
    else:
        candidates = directory.glob("*")
    return sorted(path for path in candidates if path.is_file() and path.suffix.lower() in extensions)


def _upsert_document(db: Session, path: Path, document_type: str) -> tuple[KnowledgeDocument, bool]:
    resolved = resolve_source_path(str(path))
    document = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_path == str(resolved)).first()
    created = False
    if document is None:
        document = create_document_record(
            db,
            name=resolved.name,
            document_type=document_type,
            source_path=str(resolved),
            content=None,
            summary="",
        )
        created = True
    return document, created


def import_documents_from_directory(
    db: Session,
    *,
    directory_path: str,
    document_type: str,
    recursive: bool = True,
) -> dict[str, int | str]:
    directory = resolve_source_path(directory_path)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Knowledge directory not found: {directory}")

    extensions = DOCUMENT_TYPE_EXTENSIONS.get(document_type, {".md"})
    files = _iter_matching_files(directory, recursive=recursive, extensions=extensions)

    created_count = 0
    indexed_count = 0
    failed_count = 0

    for path in files:
        try:
            document, was_created = _upsert_document(db, path, document_type)
            if was_created:
                created_count += 1
            index_document(db, document)
            indexed_count += 1
        except Exception:
            failed_count += 1

    return {
        "directory_path": str(directory),
        "document_type": document_type,
        "processed_count": len(files),
        "created_count": created_count,
        "indexed_count": indexed_count,
        "failed_count": failed_count,
    }


def bootstrap_default_documents(db: Session) -> dict[str, int]:
    created = 0
    indexed = 0

    for path in DEFAULT_SYSTEM_DOCS:
        resolved = resolve_source_path(str(path))
        if not resolved.exists() or not resolved.is_file():
            continue
        document, was_created = _upsert_document(db, resolved, "system_doc")
        if was_created:
            created += 1
        index_document(db, document)
        indexed += 1

    for directory in DEFAULT_PAPER_DIRS:
        if not directory.exists() or not directory.is_dir():
            continue
        result = import_documents_from_directory(
            db,
            directory_path=str(directory),
            document_type="paper",
            recursive=True,
        )
        created += int(result["created_count"])
        indexed += int(result["indexed_count"])

    return {"created": created, "indexed": indexed}
