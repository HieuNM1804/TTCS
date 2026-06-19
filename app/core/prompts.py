"""Centralized prompt templates for the Web RAG system."""
from __future__ import annotations

import logging
import re

import requests

from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System Prompt — Vai trò + Ràng buộc cứng
# Đặt ở role "system" để Qwen tuân thủ nghiêm ngặt nhất.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Bạn là trợ lý AI chuyên phân tích tài liệu PDF học thuật.

## Nguyên tắc bắt buộc
1. CHỈ trả lời dựa trên nội dung tài liệu được cung cấp bên dưới. Nếu tài liệu không chứa thông tin liên quan, hãy nói rõ: "Tài liệu không đề cập đến vấn đề này."
2. Trả lời bằng tiếng Việt. Giữ nguyên các thuật ngữ kỹ thuật tiếng Anh gốc (ví dụ: Transformer, Attention, Loss function).
3. TUYỆT ĐỐI KHÔNG sử dụng tiếng Trung (Chinese) trong bất kỳ trường hợp nào.
4. KHÔNG sử dụng ký hiệu Toán học hoặc LaTeX.
5. Trả lời ngắn gọn, đi thẳng vào trọng tâm. Ưu tiên dùng danh sách gạch đầu dòng.
6. Định dạng bằng Markdown (in đậm, danh sách, tiêu đề nhỏ)."""

# ---------------------------------------------------------------------------
# User Prompt Template — Chứa context, lịch sử, câu hỏi
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE = """Dưới đây là nội dung trích xuất từ tài liệu PDF:

{context}
{memory}
Câu hỏi: {question}"""


def query_chat(context: str, memory: str, question: str,
               timeout: int = 600) -> str:
    """Gọi Ollama /api/chat với cấu trúc messages (system + user role).

    Ưu điểm so với /api/generate:
    - Tách rõ System Prompt (luật lệ) và User Message (dữ liệu + câu hỏi).
    - Qwen tuân thủ ràng buộc trong System Prompt nghiêm ngặt hơn.
    """
    user_content = USER_PROMPT_TEMPLATE.format(
        context=context,
        memory=memory,
        question=question,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    log.info("Calling Ollama /api/chat (%s), user msg: %d chars", OLLAMA_MODEL, len(user_content))

    resp = requests.post(
        url,
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "num_ctx": 4096,
                "num_predict": 2048,
                "temperature": 0.1,
            },
        },
        timeout=timeout,
    )
    resp.raise_for_status()

    raw = resp.json().get("message", {}).get("content", "")

    # Fallback: lọc bỏ thẻ <think> nếu model vẫn trả về
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if not cleaned and "</think>" in raw:
        cleaned = raw.split("</think>")[-1].strip()

    if not cleaned:
        log.warning("Ollama returned empty response (raw length: %d)", len(raw))
    return cleaned
