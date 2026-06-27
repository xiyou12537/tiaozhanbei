"""
AI Chat 路由 —— 量子计算助手对话接口。

提供与 LLM 的流式对话能力，支持 DeepSeek / OpenAI 兼容 API。
通过环境变量配置：

    LLM_BASE_URL  - API 地址 (默认 https://api.deepseek.com/v1)
    LLM_API_KEY   - API 密钥 (必填)
    LLM_MODEL     - 模型名称 (默认 deepseek-chat)
"""

from __future__ import annotations

import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..middleware import get_current_user
from ..models import ChatRequest
from ..models_db import ChatMessage, User

router = APIRouter(prefix="/api/chat", tags=["AI对话"])

# ── LLM 配置 ──────────────────────────────────────────────────────
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
MAX_HISTORY = 20

SYSTEM_PROMPT = (
    "你是一位专业的量子计算助手，专注于分布式量子计算、量子电路分区和芯片拓扑映射领域。"
    "你可以帮助用户理解以下内容：\n"
    "- 量子电路的基本概念和 QASM 格式\n"
    "- 电路分区算法及其参数（b1 控制跨分区门权重、b2 控制隐形传态权重、alpha、beta）\n"
    "- 芯片拓扑设计（环形、星形、线形、网格、全连接）\n"
    "- EPR 代价优化和量子隐形传态\n"
    "- SWAP 门优化和远程门合并\n"
    "- 贪心多起点启发式分区算法的工作原理\n\n"
    "回答时请：\n"
    "- 保持专业且准确，避免过度简化导致误导\n"
    "- 用中文回答，除非用户使用英文提问\n"
    "- 如果用户询问与量子计算无关的问题，礼貌地引导回量子计算话题\n"
    "- 对于你不确定的技术细节，坦承不确定而非编造"
)


# ── 辅助函数 ──────────────────────────────────────────────────────

def _build_llm_messages(history: list[ChatMessage]) -> list[dict]:
    """将数据库历史消息转换为 LLM API 的消息格式。"""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        msgs.append({"role": msg.role, "content": msg.content})
    return msgs


async def _stream_from_llm(llm_messages: list[dict]):
    """
    调用 LLM API 并流式 yield SSE 事件。

    每个 yield 是一行完整的 SSE 数据（含 "data: " 前缀和换行）。
    最后 yield 的 done 事件中包含完整回复文本。
    """
    if not LLM_API_KEY:
        yield "data: " + json.dumps({"error": "AI 服务未配置。请设置 LLM_API_KEY 环境变量。"}) + "\n\n"
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
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    full = ""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    error_msg = f"LLM API 错误 ({resp.status_code})"
                    try:
                        err = json.loads(body)
                        error_msg = err.get("error", {}).get("message", error_msg)
                    except json.JSONDecodeError:
                        error_msg = body.decode("utf-8", errors="replace")[:200]
                    yield "data: " + json.dumps({"error": error_msg}) + "\n\n"
                    return

                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            yield "data: " + json.dumps({"done": True, "content": full}) + "\n\n"
                            return
                        try:
                            chunk = json.loads(data_str)
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                full += content
                                yield "data: " + json.dumps({"token": content}) + "\n\n"
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
    except httpx.TimeoutException:
        yield "data: " + json.dumps({"error": "AI 服务响应超时，请稍后重试"}) + "\n\n"
    except httpx.ConnectError:
        yield "data: " + json.dumps({"error": f"无法连接到 AI 服务 ({LLM_BASE_URL})，请检查 LLM_BASE_URL 配置"}) + "\n\n"
    except Exception as exc:
        yield "data: " + json.dumps({"error": f"对话出错: {str(exc)}"}) + "\n\n"


# ── API 端点 ──────────────────────────────────────────────────────

@router.post("/send")
async def send_message(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发送消息并流式返回 AI 回复（Server-Sent Events）。"""
    # 1. 保存用户消息
    user_msg = ChatMessage(user_id=user.id, role="user", content=req.message)
    db.add(user_msg)
    db.commit()

    # 2. 获取历史消息作为上下文
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(MAX_HISTORY * 2)
        .all()
    )

    # 3. 构建 LLM 请求
    llm_messages = _build_llm_messages(history)

    # 4. 包装 generator：流式发送给前端，并在完成后保存 assistant 回复
    async def event_stream():
        full_content = ""
        has_error = False
        async for sse_line in _stream_from_llm(llm_messages):
            # 解析 done / error 事件以决定是否保存
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

        # 流结束后保存 assistant 回复到数据库
        if full_content.strip() and not has_error:
            assistant_msg = ChatMessage(
                user_id=user.id,
                role="assistant",
                content=full_content.strip(),
            )
            db.add(assistant_msg)
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
    """获取当前用户的对话历史（最近 100 条消息）。"""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at.asc())
        .limit(100)
        .all()
    )

    return {
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in messages
        ]
    }


@router.delete("/clear")
def clear_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """清除当前用户的所有对话历史。"""
    db.query(ChatMessage).filter(ChatMessage.user_id == user.id).delete()
    db.commit()
    return {"status": "ok", "message": "对话历史已清除"}
