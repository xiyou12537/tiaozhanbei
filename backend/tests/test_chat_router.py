from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.middleware import create_token
from backend.models_db import ChatMessage, ChatReference, KnowledgeChunk, KnowledgeDocument, User
from backend.routers import chat as chat_router


class ChatRouterTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.db = SessionLocal()
        self.user = User(username=f"chat_test_user_{id(self)}", password_hash="test-hash")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

        self.app = FastAPI()
        self.app.include_router(chat_router.router)
        self.client = TestClient(self.app)
        self.headers = {"Authorization": f"Bearer {create_token(self.user.id, self.user.username)}"}

    def tearDown(self):
        message_ids = [item.id for item in self.db.query(ChatMessage.id).filter(ChatMessage.user_id == self.user.id).all()]
        if message_ids:
            self.db.query(ChatReference).filter(ChatReference.chat_message_id.in_(message_ids)).delete(synchronize_session=False)
        self.db.query(ChatMessage).filter(ChatMessage.user_id == self.user.id).delete(synchronize_session=False)
        self.db.query(KnowledgeChunk).delete(synchronize_session=False)
        self.db.query(KnowledgeDocument).delete(synchronize_session=False)
        self.db.query(User).filter(User.id == self.user.id).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_clear_history_removes_chat_references(self):
        document = KnowledgeDocument(
            name="test-chat-doc.md",
            type="system_doc",
            source_path="C:/tmp/test-chat-doc.md",
            status="indexed",
            summary="summary",
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        chunk = KnowledgeChunk(
            document_id=document.id,
            chunk_index=0,
            section_title="section",
            content="content",
            token_length=1,
            embedding_json={},
        )
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)

        assistant_message = ChatMessage(user_id=self.user.id, role="assistant", content="answer")
        self.db.add(assistant_message)
        self.db.commit()
        self.db.refresh(assistant_message)

        self.db.add(
            ChatReference(
                chat_message_id=assistant_message.id,
                document_id=document.id,
                chunk_id=chunk.id,
                rank=1,
                score=0.9,
            )
        )
        self.db.commit()

        response = self.client.delete("/api/chat/clear", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.query(ChatMessage).filter(ChatMessage.user_id == self.user.id).count(), 0)
        self.assertEqual(self.db.query(ChatReference).count(), 0)

    def test_load_recent_history_returns_latest_messages(self):
        original_limit = chat_router.MAX_HISTORY
        chat_router.MAX_HISTORY = 2
        try:
            for index in range(1, 8):
                self.db.add(
                    ChatMessage(
                        user_id=self.user.id,
                        role="user" if index % 2 else "assistant",
                        content=f"message-{index}",
                    )
                )
            self.db.commit()

            history = chat_router._load_recent_history(self.db, self.user.id, chat_router.MAX_HISTORY * 2)
            contents = [item.content for item in history]

            self.assertEqual(contents, ["message-4", "message-5", "message-6", "message-7"])
        finally:
            chat_router.MAX_HISTORY = original_limit

    def test_history_returns_reference_payload_shape(self):
        document = KnowledgeDocument(
            name="history-doc.md",
            type="system_doc",
            source_path="C:/tmp/history-doc.md",
            status="indexed",
            summary="summary",
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        chunk = KnowledgeChunk(
            document_id=document.id,
            chunk_index=0,
            section_title="Usage",
            content="This is a long enough knowledge snippet for frontend rendering.",
            token_length=8,
            embedding_json={},
        )
        self.db.add(chunk)
        self.db.commit()
        self.db.refresh(chunk)

        user_message = ChatMessage(user_id=self.user.id, role="user", content="question")
        assistant_message = ChatMessage(user_id=self.user.id, role="assistant", content="answer")
        self.db.add(user_message)
        self.db.add(assistant_message)
        self.db.commit()
        self.db.refresh(assistant_message)

        self.db.add(
            ChatReference(
                chat_message_id=assistant_message.id,
                document_id=document.id,
                chunk_id=chunk.id,
                rank=1,
                score=0.95,
            )
        )
        self.db.commit()

        response = self.client.get("/api/chat/history", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][0]["references"], [])

        assistant_payload = payload["messages"][1]["references"]
        self.assertEqual(len(assistant_payload), 1)
        self.assertEqual(
            assistant_payload[0],
            {
                "document_id": document.id,
                "chunk_id": chunk.id,
                "document_name": "history-doc.md",
                "document_type": "system_doc",
                "section_title": "Usage",
                "score": 0.95,
                "snippet": "This is a long enough knowledge snippet for frontend rendering.",
            },
        )


if __name__ == "__main__":
    unittest.main()
