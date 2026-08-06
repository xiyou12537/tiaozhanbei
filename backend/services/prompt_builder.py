from __future__ import annotations

from ..models_db import ChatMessage

RAG_SYSTEM_PROMPT = """
你是一位专业的量子计算与平台使用助手。

回答规则：
1. 优先依据提供的知识库片段回答，不要伪造来源。
2. 如果知识库没有直接命中，请明确说明“当前知识库没有直接依据”，再基于已有常识给出谨慎回答。
3. 回答平台使用问题时，优先给出步骤化说明。
4. 回答专业概念问题时，优先给出定义、结论和适用前提。
5. 回答尽量使用中文，并在结尾列出来源文档名称。
""".strip()


def build_retrieval_context(references: list[dict]) -> str:
    if not references:
        return "[知识库检索结果]\n当前知识库没有命中可直接引用的内容。"

    blocks = ["[知识库检索结果]"]
    for index, item in enumerate(references, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[知识片段 {index}]",
                    f"文档名: {item['document_name']}",
                    f"类型: {item['document_type']}",
                    f"章节: {item['section_title'] or '未命名章节'}",
                    f"内容: {item['content']}",
                ]
            )
        )
    return "\n\n".join(blocks)


def build_llm_messages(history: list[ChatMessage], references: list[dict]) -> list[dict]:
    messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": build_retrieval_context(references)})
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    return messages


def build_reference_payload(references: list[dict]) -> list[dict]:
    payload = []
    for item in references:
        payload.append(
            {
                "document_id": item["document_id"],
                "chunk_id": item["chunk_id"],
                "document_name": item["document_name"],
                "document_type": item["document_type"],
                "section_title": item["section_title"],
                "score": item["score"],
                "snippet": item["content"][:180],
            }
        )
    return payload
