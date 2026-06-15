# 🤖 Daily Paper Brief Bot

Một AI Agent chạy ngầm trên máy tính của bạn, tự động thu thập các bài báo mới nhất từ arXiv mỗi ngày, đánh giá chất lượng, tải PDF, và gửi báo cáo tóm tắt qua Telegram. Đặc biệt, Bot được tích hợp hệ thống **RAG (Retrieval-Augmented Generation)** cho phép bạn thảo luận và hỏi đáp trực tiếp (Q&A) với bài báo ngay trên Telegram.

## 🌟 Tính năng chính

1. **Daily Fetch**: Tự động lấy danh sách bài báo AI/ML mới nhất mỗi ngày từ arXiv theo khung giờ bạn đặt (ví dụ 11:17 sáng).
2. **Auto-ranking**: Sử dụng LLM để chấm điểm và lọc ra Top 5 bài báo hay nhất (dựa trên abstract, github code, xu hướng SOTA).
3. **Deep RAG Q&A**: 
   - Khi bạn chọn 1 bài báo, bot sẽ tự động tải PDF, cắt nhỏ theo cấu trúc Section, nhúng (embedding) và lưu vào VectorDB (FAISS).
   - Bạn có thể hỏi bất cứ chi tiết nào trong bài, LLM sẽ tìm đúng đoạn văn bản đó và trả lời cho bạn. Bot có bộ nhớ ngữ cảnh để bạn hỏi follow-up.
4. **Custom PDF Upload**: Kéo thả một file PDF bất kỳ vào Telegram, bot sẽ tự động đọc hiểu file đó và cho phép bạn hỏi đáp lập tức.

## ⚙️ Công nghệ sử dụng
- **LLM**: Ollama (chạy local, khuyên dùng `qwen3.5:4b` hoặc `llama3.1:8b`).
- **RAG Stack**: LangChain, FAISS, Nomic-Embed-Text, PyMuPDF4LLM.
- **Interface**: Telegram Bot API (Long polling).

## 🚀 Cài đặt & Khởi động

### Bước 1: Cài đặt thư viện
Yêu cầu: Python 3.10+
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Bước 2: Lấy Token Telegram
Để Bot có thể gửi tin nhắn cho bạn, bạn cần tạo một con Bot riêng và lấy ID cá nhân của bạn trên Telegram:

1. **Lấy Bot Token**: 
   - Mở ứng dụng Telegram, tìm kiếm **@BotFather** (có tích xanh) và bấm `Start`.
   - Gõ lệnh `/newbot`, sau đó nhập tên hiển thị cho Bot.
   - Nhập username cho Bot (bắt buộc phải kết thúc bằng chữ `bot`, ví dụ: `my_ai_agent_bot`).
   - BotFather sẽ cấp cho bạn một chuỗi Token dài (ví dụ: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`). Đây chính là `TELEGRAM_BOT_TOKEN`.

2. **Lấy Chat ID cá nhân**:
   **Cách 1: Dùng Bot có sẵn (Dành cho người mới)**
   - Lên thanh tìm kiếm của Telegram, gõ tìm **@RawDataBot** hoặc **@userinfobot**.
   - Bấm `Start` (hoặc gửi một tin nhắn). Nó sẽ trả về cho bạn một đoạn văn bản. Tìm dãy số ở dòng `id` hoặc `chat id` (ví dụ: `7738904186`).

   **Cách 2: Tự lấy qua API (Dành cho Developer)**
   - Mở ứng dụng Telegram, tìm con Bot bạn vừa tạo ở Bước 1 và nhắn cho nó một dòng chữ bất kỳ (ví dụ: `hello`).
   - Mở trình duyệt web và dán đường link sau (thay `<TOKEN>` bằng Token của bạn):
     `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - Trong đống chữ loằng ngoằng hiện ra, tìm đoạn `"chat":{"id": ` -> Dãy số ngay phía sau chính là Chat ID của bạn.

   *Copy dãy số Chat ID đó để dùng cho bước tiếp theo.*

### Bước 3: Thiết lập môi trường
Tạo file `.env` (bạn có thể copy từ `.env.example`):
```text
TELEGRAM_BOT_TOKEN=Điền_Bot_Token_Vào_Đây
TELEGRAM_CHAT_ID=Điền_Chat_ID_Vào_Đây
TOPICS=AI agents,RAG,multi-agent systems,LLM reasoning
EXCLUDE_KEYWORDS=quantum,bioinformatics,hardware,protein
MAX_RESULTS=30
DAYS_BACK=7
TOP_K=5
SCHEDULE_TIME=11:17
OLLAMA_MODEL=qwen3.5:4b
```

### Bước 4: Cài đặt và Tải Model Ollama
Hệ thống sử dụng Ollama để chạy mô hình AI trực tiếp trên máy tính của bạn nhằm bảo mật dữ liệu và hoàn toàn miễn phí.
1. Truy cập trang chủ [Ollama.com](https://ollama.com/download) để tải và cài đặt phần mềm Ollama cho máy tính của bạn (hỗ trợ Windows, Mac, Linux).
2. Sau khi cài đặt xong, bật phần mềm Ollama lên.
3. Mở Terminal và chạy 2 lệnh sau để tải mô hình Ngôn ngữ (`qwen3.5:4b`) và mô hình Nhúng (`nomic-embed-text`):
```powershell
ollama pull qwen3.5:4b
ollama pull nomic-embed-text
```

### Bước 5: Chạy Bot
```powershell
python -m app.main
```
Hệ thống sẽ chạy ngầm và lắng nghe tin nhắn Telegram của bạn!

## 📱 Các lệnh trên Telegram
- `/start`: Bắt đầu và nhận danh sách 5 bài báo mới ngay lập tức.
- `/fetch`: Cập nhật lại danh sách bài báo.
- `/paper1` đến `/paper5`: Bắt đầu phiên Hỏi-Đáp với bài báo tương ứng.
- `/up`: Chuyển Bot sang chế độ chờ nhận file PDF do bạn upload.
- `/exit`: Kết thúc phiên thảo luận hiện tại.
- `/help`: Xem trợ giúp.
