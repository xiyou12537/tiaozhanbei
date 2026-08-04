from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.database import SessionLocal, init_db
from backend.models_db import ChatMessage, ChatReference, KnowledgeChunk, KnowledgeDocument, User
from backend.services.knowledge_analytics import collect_reference_analytics
from backend.services.knowledge_bootstrap import import_documents_from_directory
from backend.services.knowledge_ingest import (
    collect_knowledge_diagnostics,
    collect_knowledge_stats,
    create_document_record,
    extract_document_chunks,
    index_document,
    rebuild_index,
)
from backend.services.knowledge_search import search_knowledge
from backend.services.prompt_builder import build_reference_payload


def build_simple_pdf_bytes(text: str) -> bytes:
    stream = f"BT\n/F1 18 Tf\n50 100 Td\n({text}) Tj\nET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


class KnowledgeServiceTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.db = SessionLocal()
        self.tempdir = tempfile.TemporaryDirectory()
        self.user = User(username=f"test_rag_user_{id(self)}", password_hash="test-hash")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self):
        message_ids = [item.id for item in self.db.query(ChatMessage.id).filter(ChatMessage.user_id == self.user.id).all()]
        if message_ids:
            self.db.query(ChatReference).filter(ChatReference.chat_message_id.in_(message_ids)).delete(synchronize_session=False)
        self.db.query(KnowledgeDocument).filter(KnowledgeDocument.name.like("test-rag-%")).delete()
        self.db.query(ChatMessage).filter(ChatMessage.user_id == self.user.id).delete(synchronize_session=False)
        self.db.query(User).filter(User.id == self.user.id).delete()
        self.db.commit()
        self.db.close()
        self.tempdir.cleanup()

    def test_extract_document_chunks_keeps_headings(self):
        text = "# 快速开始\n第一段内容。\n\n## 参数说明\n第二段内容。"
        chunks = extract_document_chunks(text, chunk_size=20, overlap=5)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0]["section_title"], "快速开始")
        self.assertEqual(chunks[1]["section_title"], "参数说明")

    def test_index_and_search_markdown_document(self):
        source = Path(self.tempdir.name) / "test-rag-doc.md"
        source.write_text("# 参数说明\nb1 用于控制跨分区门权重。test-rag-unique-b1\n", encoding="utf-8")

        document = create_document_record(
            self.db,
            name="test-rag-params.md",
            document_type="system_doc",
            source_path=str(source),
            content=None,
            summary="",
        )
        indexed_document, chunk_count = index_document(self.db, document)
        hits = search_knowledge(self.db, query="test-rag-unique-b1 是什么意思", top_k=3)

        self.assertEqual(indexed_document.status, "indexed")
        self.assertGreaterEqual(chunk_count, 1)
        self.assertGreaterEqual(len(hits), 1)
        self.assertTrue(any(item["document_name"] == "test-rag-params.md" for item in hits))

    def test_index_and_search_pdf_document(self):
        source = Path(self.tempdir.name) / "test-rag-paper.pdf"
        source.write_bytes(build_simple_pdf_bytes("Quantum RAG PDF"))

        document = create_document_record(
            self.db,
            name="test-rag-paper.pdf",
            document_type="paper",
            source_path=str(source),
            content=None,
            summary="",
        )
        indexed_document, chunk_count = index_document(self.db, document)
        hits = search_knowledge(self.db, query="Quantum RAG PDF", top_k=3, document_type="paper")

        self.assertEqual(indexed_document.status, "indexed")
        self.assertGreaterEqual(chunk_count, 1)
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["document_type"], "paper")
        self.assertEqual(hits[0]["document_name"], "test-rag-paper.pdf")

    def test_build_reference_payload(self):
        payload = build_reference_payload(
            [
                {
                    "document_id": 1,
                    "chunk_id": 2,
                    "document_name": "test-rag-params.md",
                    "document_type": "system_doc",
                    "section_title": "参数说明",
                    "content": "b1 用于控制跨分区门权重。",
                    "score": 0.91,
                }
            ]
        )
        self.assertEqual(payload[0]["document_name"], "test-rag-params.md")
        self.assertEqual(payload[0]["chunk_id"], 2)
        self.assertIn("b1", payload[0]["snippet"])

    def test_collect_stats_and_rebuild_by_type(self):
        md_source = Path(self.tempdir.name) / "test-rag-stats.md"
        md_source.write_text("# 系统说明\n系统知识片段。test-rag-stats-md\n", encoding="utf-8")
        pdf_source = Path(self.tempdir.name) / "test-rag-stats.pdf"
        pdf_source.write_bytes(build_simple_pdf_bytes("Paper stats test"))

        system_doc = create_document_record(
            self.db,
            name="test-rag-stats.md",
            document_type="system_doc",
            source_path=str(md_source),
            content=None,
            summary="",
        )
        paper_doc = create_document_record(
            self.db,
            name="test-rag-stats.pdf",
            document_type="paper",
            source_path=str(pdf_source),
            content=None,
            summary="",
        )
        index_document(self.db, system_doc)
        index_document(self.db, paper_doc)

        stats = collect_knowledge_stats(self.db)
        rebuild_result = rebuild_index(self.db, document_type="paper")

        self.assertGreaterEqual(stats["document_count"], 2)
        self.assertGreaterEqual(stats["chunk_count"], 2)
        self.assertGreaterEqual(stats["system_doc_count"], 1)
        self.assertGreaterEqual(stats["paper_count"], 1)
        self.assertEqual(rebuild_result["document_count"], 1)

    def test_collect_diagnostics_reports_unindexed_document(self):
        source = Path(self.tempdir.name) / "test-rag-diagnostic.md"
        source.write_text("# 诊断文档\n尚未建立索引。\n", encoding="utf-8")

        create_document_record(
            self.db,
            name="test-rag-diagnostic.md",
            document_type="system_doc",
            source_path=str(source),
            content=None,
            summary="",
        )

        diagnostics = collect_knowledge_diagnostics(self.db)

        self.assertIn(diagnostics["pdf_backend"], {"pypdf", "PyPDF2", "none"})
        self.assertGreaterEqual(diagnostics["issue_count"], 1)
        self.assertTrue(any(item["issue_type"] == "not_indexed" for item in diagnostics["issues"]))

    def test_import_documents_from_directory(self):
        paper_dir = Path(self.tempdir.name) / "papers"
        paper_dir.mkdir(parents=True, exist_ok=True)
        (paper_dir / "paper-a.md").write_text("# 论文A\npaper-a-unique\n", encoding="utf-8")
        (paper_dir / "paper-b.pdf").write_bytes(build_simple_pdf_bytes("paper-b-unique"))

        result = import_documents_from_directory(
            self.db,
            directory_path=str(paper_dir),
            document_type="paper",
            recursive=True,
        )

        self.assertEqual(result["processed_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(result["indexed_count"], 2)

    def test_collect_reference_analytics(self):
        source = Path(self.tempdir.name) / "test-rag-analytics.md"
        source.write_text("# Analytics\nanalytics-hit-unique\n", encoding="utf-8")
        document = create_document_record(
            self.db,
            name="test-rag-analytics.md",
            document_type="system_doc",
            source_path=str(source),
            content=None,
            summary="",
        )
        _, _ = index_document(self.db, document)
        chunk = (
            self.db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == document.id)
            .order_by(KnowledgeChunk.id.asc())
            .first()
        )
        self.assertIsNotNone(chunk)

        message = ChatMessage(user_id=self.user.id, role="assistant", content="analytics answer")
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)

        self.db.add(
            ChatReference(
                chat_message_id=message.id,
                document_id=document.id,
                chunk_id=chunk.id,
                rank=1,
                score=0.88,
            )
        )
        self.db.commit()

        result = collect_reference_analytics(self.db, limit=5)

        self.assertGreaterEqual(result["total_reference_count"], 1)
        self.assertGreaterEqual(result["referenced_document_count"], 1)
        self.assertTrue(any(item["document_name"] == "test-rag-analytics.md" for item in result["top_documents"]))


if __name__ == "__main__":
    unittest.main()
