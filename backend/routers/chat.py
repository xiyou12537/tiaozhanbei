from __future__ import annotations

import json
import os

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware import get_current_user
from ..models import ChatRequest
from ..models_db import ChatMessage, ChatReference, KnowledgeChunk, KnowledgeDocument, User
from ..services.knowledge_search import search_knowledge
from ..services.prompt_builder import build_llm_messages, build_reference_payload

router = APIRouter(prefix="/api/chat", tags=["AI对话"])

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
MAX_HISTORY = 20
DEFAULT_TOP_K = 5


def _serialize_message_references(message: ChatMessage, db: Session) -> list[dict]:
    rows = (
        db.query(ChatReference, KnowledgeDocument, KnowledgeChunk)
        .join(KnowledgeDocument, KnowledgeDocument.id == ChatReference.document_id)
        .join(KnowledgeChunk, KnowledgeChunk.id == ChatReference.chunk_id)
        .filter(ChatReference.chat_message_id == message.id)
        .order_by(ChatReference.rank.asc(), ChatReference.id.asc())
        .all()
    )

    payload = []
    for reference, document, chunk in rows:
        payload.append(
            {
                "document_id": document.id,
                "chunk_id": chunk.id,
                "document_name": document.name,
                "document_type": document.type,
                "section_title": chunk.section_title or "",
                "score": reference.score,
                "snippet": chunk.content[:180],
            }
        )
    return payload


def _load_recent_history(db: Session, user_id: int, limit: int) -> list[ChatMessage]:
    recent_history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(recent_history))


async def _stream_from_llm(llm_messages: list[dict], references_payload: list[dict]):
    if not LLM_API_KEY:
        yield "data: " + json.dumps(
            {"error": "AI 服务未配置。请设置 LLM_API_KEY 环境变量。"},
            ensure_ascii=False,
        ) + "\n\n"
        return

    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": llm_messages,
        "stream": True,
        "temperature": 0.4,
        "max_tokens": 2048,
    }

    full_content = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    error_message = f"LLM API error ({response.status_code})"
                    try:
                        error_payload = json.loads(body)
                        error_message = error_payload.get("error", {}).get("message", error_message)
                    except json.JSONDecodeError:
                        error_message = body.decode("utf-8", errors="replace")[:200]
                    yield "data: " + json.dumps({"error": error_message}, ensure_ascii=False) + "\n\n"
                    return

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        yield "data: " + json.dumps(
                            {"done": True, "content": full_content, "references": references_payload},
                            ensure_ascii=False,
                        ) + "\n\n"
                        return

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if token:
                        full_content += token
                        yield "data: " + json.dumps({"token": token}, ensure_ascii=False) + "\n\n"
    except httpx.TimeoutException:
        yield "data: " + json.dumps({"error": "AI 服务响应超时，请稍后重试。"}, ensure_ascii=False) + "\n\n"
    except httpx.ConnectError:
        yield "data: " + json.dumps(
            {"error": f"无法连接到 AI 服务 ({LLM_BASE_URL})，请检查 LLM_BASE_URL 配置。"},
            ensure_ascii=False,
        ) + "\n\n"
    except Exception as exc:
        yield "data: " + json.dumps({"error": f"对话出错: {str(exc)}"}, ensure_ascii=False) + "\n\n"


@router.post("/send")
async def send_message(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_message = ChatMessage(user_id=user.id, role="user", content=req.message)
    db.add(user_message)
    db.commit()

    history = _load_recent_history(db, user.id, MAX_HISTORY * 2)
    references = search_knowledge(db, query=req.message, top_k=DEFAULT_TOP_K)
    references_payload = build_reference_payload(references)
    llm_messages = build_llm_messages(history, references)

    async def event_stream():
        full_content = ""
        has_error = False

        async for sse_line in _stream_from_llm(llm_messages, references_payload):
            if sse_line.startswith("data: "):
                try:
                    data = json.loads(sse_line[6:].strip())
                    if "done" in data:
                        full_content = data.get("content", full_content)
                    elif "error" in data:
                        has_error = True
                except json.JSONDecodeError:
                    pass
            yield sse_line

        if full_content.strip() and not has_error:
            assistant_message = ChatMessage(
                user_id=user.id,
                role="assistant",
                content=full_content.strip(),
            )
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            for rank, item in enumerate(references_payload, start=1):
                db.add(
                    ChatReference(
                        chat_message_id=assistant_message.id,
                        document_id=item["document_id"],
                        chunk_id=item["chunk_id"],
                        rank=rank,
                        score=item["score"],
                    )
                )
            db.commit()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history")
def get_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .limit(100)
        .all()
    )

    return {
        "messages": [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat() if message.created_at else "",
                "references": _serialize_message_references(message, db) if message.role == "assistant" else [],
            }
            for message in messages
        ]
    }


@router.delete("/clear")
def clear_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message_ids = [item.id for item in db.query(ChatMessage.id).filter(ChatMessage.user_id == user.id).all()]
    if message_ids:
        db.query(ChatReference).filter(ChatReference.chat_message_id.in_(message_ids)).delete(synchronize_session=False)

    db.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete(synchronize_session=False)
    db.commit()

    return {"status": "ok", "message": "对话历史已清空。"}
