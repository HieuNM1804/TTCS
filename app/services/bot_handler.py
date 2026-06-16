"""Telegram bot command and message handling."""
from __future__ import annotations

import json
import logging
import re
import html
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from app.services.telegram_utils import format_html, query_ollama, send_message, download_telegram_file

log = logging.getLogger(__name__)

MAX_MEMORY = 0


@dataclass
class Session:
    paper: dict | None = None
    memory: deque = field(default_factory=lambda: deque(maxlen=MAX_MEMORY))
    created_at: datetime = field(default_factory=datetime.now)
    waiting_for_pdf: bool = False


class BotHandler:

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def handle_update(self, update: dict) -> None:
        msg = update.get("message")
        if not msg:
            return
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()
        if not text:
            text = msg.get("caption", "").strip()
        is_doc = "document" in msg

        if not chat_id or (not text and not is_doc):
            return

        log.info("Message from %s: %s", chat_id, text[:80] if text else "Document")

        if text.startswith("/"):
            self._handle_command(chat_id, text)
        if is_doc:
            self._handle_document(chat_id, msg["document"])
            return
        if text.startswith("/"):
            return

        if chat_id in self.sessions and self.sessions[chat_id].paper is not None:
            self._handle_question(chat_id, text)
        else:
            send_message(
                chat_id,
                "📚 <b>Daily Paper Bot</b>\n\n"
                "• Gõ /paper1 đến /paper5 để thảo luận.\n"
                "• Gõ /up để tải lên file PDF của bạn.\n"
                "• Gõ /help để biết chi tiết.",
            )

    def _handle_command(self, chat_id: str, text: str) -> None:
        cmd = text.split()[0].lower()

        if cmd == "/start":
            send_message(chat_id, "📚 <b>Daily Paper Brief Bot</b>\n\nĐang tìm kiếm paper mới từ arXiv …")
            threading.Thread(target=self._bg_fetch_papers, args=(chat_id,), daemon=True).start()
            return

        if cmd == "/help":
            send_message(
                chat_id,
                "📚 <b>Daily Paper Brief Bot</b>\n\n"
                "• /start: Tìm và gửi 5 paper mới nhất từ arXiv\n"
                "• /fetch: Cập nhật lại danh sách paper\n"
                "• /paper1 đến /paper5: Thảo luận về bài báo\n"
                "• /up: Tải lên file PDF của riêng bạn\n"
                "• /exit: Kết thúc phiên thảo luận\n"
                "• Nhập câu hỏi bất kỳ để hỏi đáp về bài báo",
            )
            return

        if cmd == "/fetch":
            send_message(chat_id, "🔄 Đang cập nhật danh sách paper …")
            threading.Thread(target=self._bg_fetch_papers, args=(chat_id,), daemon=True).start()
            return

        if cmd == "/exit":
            if chat_id in self.sessions:
                paper = self.sessions[chat_id].paper
                title = paper["title"] if paper else "Tài liệu đang tải"
                del self.sessions[chat_id]
                send_message(chat_id, f"✅ Đã kết thúc thảo luận về:\n<b>{title}</b>")
            else:
                send_message(chat_id, "Bạn chưa tham gia thảo luận. Gõ /paper1..5 để bắt đầu.")
            return

        match = re.match(r"^/paper(\d+)$", cmd)
        if match:
            self._start_paper_session(chat_id, int(match.group(1)))
            return

        if cmd == "/up":
            if chat_id not in self.sessions:
                self.sessions[chat_id] = Session(paper=None)
            self.sessions[chat_id].waiting_for_pdf = True
            send_message(chat_id, "📎 Vui lòng gửi/upload file PDF của bạn cho tôi.")
            return

        send_message(chat_id, "❌ Lệnh không hợp lệ. Gõ /help để xem hướng dẫn.")

    def _bg_fetch_papers(self, chat_id: str) -> None:
        try:
            from app.tasks.arxiv_fetcher import fetch_papers, filter_and_rank, format_digest

            papers = fetch_papers()
            if not papers:
                send_message(chat_id, "Không tìm thấy paper mới. Thử lại sau.")
                return

            top = filter_and_rank(papers)
            if not top:
                send_message(chat_id, "Không có paper nào phù hợp với topics hiện tại.")
                return

            cache_path = Path("data/last_sent_papers.json")
            cache_data = [
                {
                    "index": idx, "title": p["title"], "abstract": p["abstract"],
                    "authors": p["authors"], "published": p["published"],
                    "url": p["url"], "arxiv_id": p["arxiv_id"], "score": p["score"],
                }
                for idx, p in enumerate(top, 1)
            ]
            cache_path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")
            send_message(chat_id, format_digest(top))
            log.info("Fetched and sent %d papers to %s", len(top), chat_id)
        except Exception as exc:
            log.error("Failed to fetch papers: %s", exc, exc_info=True)
            send_message(chat_id, f"❌ Lỗi khi tìm paper: {exc}")

    def _handle_document(self, chat_id: str, document: dict) -> None:
        session = self.sessions.get(chat_id)
        if not session or not session.waiting_for_pdf:
            send_message(chat_id, "⚠️ Vui lòng gõ lệnh /up trước khi tải file lên.")
            return
        if document.get("mime_type", "") != "application/pdf":
            send_message(chat_id, "❌ Chỉ hỗ trợ file định dạng PDF. Vui lòng thử lại.")
            return
        file_id = document["file_id"]
        file_name = document.get("file_name", "custom_paper.pdf")
        send_message(chat_id, f"📥 Đang tải file <b>{html.escape(file_name)}</b> ...")
        threading.Thread(
            target=self._bg_download_and_build_custom,
            args=(chat_id, file_id, file_name), daemon=True,
        ).start()

    def _bg_download_and_build_custom(self, chat_id: str, file_id: str, file_name: str) -> None:
        try:
            from app.core.rag import PaperRAG

            dest_path = Path("data/papers") / f"custom_{file_id}.pdf"
            success = download_telegram_file(file_id, dest_path)
            if not success:
                send_message(chat_id, "❌ Lỗi khi tải file từ Telegram. Có thể file quá lớn (>20MB).")
                self.sessions[chat_id].waiting_for_pdf = False
                return

            send_message(chat_id, "⚙️ Đang phân tích và tạo chỉ mục (indexing) ...")
            rag = PaperRAG(f"custom_{file_id}", OLLAMA_BASE_URL, "nomic-embed-text")
            rag.build()

            paper = {
                "arxiv_id": f"custom_{file_id}",
                "title": file_name,
                "abstract": "Tài liệu PDF do người dùng tải lên.",
                "authors": ["Người dùng"],
                "published": "N/A",
                "url": "N/A",
            }
            self.sessions[chat_id] = Session(paper=paper)
            send_message(
                chat_id,
                f"✅ <b>Đã xử lý xong tài liệu:</b> {html.escape(file_name)}\n"
                "💬 Bạn có thể bắt đầu đặt câu hỏi ngay bây giờ!\n"
                "Gõ /exit để dừng thảo luận.",
            )
        except Exception as exc:
            log.error("Failed to build custom PDF: %s", exc, exc_info=True)
            send_message(chat_id, f"❌ Lỗi xử lý file PDF: {exc}")
            if chat_id in self.sessions:
                self.sessions[chat_id].waiting_for_pdf = False

    def _start_paper_session(self, chat_id: str, index: int) -> None:
        cache_path = Path("data/last_sent_papers.json")
        if not cache_path.exists():
            send_message(chat_id, "Chưa có dữ liệu bài báo. Hãy chờ digest tiếp theo.")
            return

        papers = json.loads(cache_path.read_text(encoding="utf-8"))
        selected = next((p for p in papers if p.get("index") == index), None)
        if not selected:
            send_message(chat_id, f"Không tìm thấy paper #{index}. Danh sách: /paper1 đến /paper{len(papers)}.")
            return

        self.sessions[chat_id] = Session(paper=selected)
        threading.Thread(target=self._bg_build_index, args=(chat_id, selected["arxiv_id"]), daemon=True).start()

        authors = ", ".join(selected["authors"][:3])
        if len(selected["authors"]) > 3:
            authors += "..."
        abstract = format_html(selected["abstract"])
        send_message(
            chat_id,
            f"📖 <b>Paper #{index}</b>\n"
            f"<b>{selected['title']}</b>\n\n"
            f"👤 {authors}\n📅 {selected['published']}\n"
            f"🔗 <a href=\"{selected['url']}\">{selected['arxiv_id']}</a>\n\n"
            f"<i>{abstract[:500]}</i>\n\n"
            "💬 Hãy đặt câu hỏi về bài báo này.\nGõ /exit để dừng thảo luận.",
        )

    def _bg_build_index(self, chat_id: str, arxiv_id: str) -> None:
        try:
            from app.core.rag import PaperRAG
            log.info("Building index for %s ...", arxiv_id)
            rag = PaperRAG(arxiv_id, OLLAMA_BASE_URL, "nomic-embed-text")
            rag.build()
            log.info("Index built successfully for %s", arxiv_id)
        except Exception as exc:
            log.error("Failed to build index for %s: %s", arxiv_id, exc, exc_info=True)

    def _handle_question(self, chat_id: str, question: str) -> None:
        session = self.sessions[chat_id]
        paper = session.paper
        log.info("Processing question from %s: %s", chat_id, question[:60])

        from app.core.rag import PaperRAG
        rag = PaperRAG(paper["arxiv_id"], OLLAMA_BASE_URL, "nomic-embed-text")
        context = rag.retrieve(question, k=5)
        log.info("Retrieved context: %d chars", len(context))

        memory_text = self._format_memory(session)
        prompt = self._build_prompt(paper, context, question, memory_text)

        answer = query_ollama(prompt, num_predict=2048)
        log.info("Ollama response: %d chars", len(answer))

        if not answer:
            send_message(chat_id, "⚠️ Không nhận được phản hồi từ model. Hãy thử hỏi lại.")
            return

        session.memory.append((question, answer))
        send_message(chat_id, format_html(answer))

    @staticmethod
    def _format_memory(session: Session) -> str:
        if not session.memory:
            return ""
        lines = ["\n[Lịch sử hỏi đáp gần đây trong phiên]"]
        for q, a in session.memory:
            short_a = a[:300] + "..." if len(a) > 300 else a
            lines.extend([f"Người dùng: {q}", f"Trả lời: {short_a}", ""])
        return "\n".join(lines)

    @staticmethod
    def _build_prompt(paper: dict, context: str, question: str, memory: str) -> str:
        return f"""Bạn là trợ lý AI chuyên phân tích bài báo nghiên cứu AI/ML từ arXiv. Trả lời câu hỏi dựa trên thông tin bài báo bên dưới.

[Bài báo]
Tiêu đề: {paper['title']}
Tóm tắt: {paper['abstract'][:500]}

[Trích xuất từ PDF]
{context[:3000]}
{memory}
[Câu hỏi]
"{question}"

[Yêu cầu]
- Trả lời đi thẳng vào trọng tâm, chỉ liệt kê ý chính.
- TUYỆT ĐỐI KHÔNG dùng ký hiệu Toán học hay LaTeX. 
- KHÔNG dùng tiếng Trung. Giữ nguyên thuật ngữ tiếng Anh gốc nếu không dịch được.
"""
