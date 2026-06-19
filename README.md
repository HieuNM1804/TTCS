# DocMind Web RAG

Web UI để upload PDF, tạo chỉ mục FAISS, rồi hỏi đáp trên nội dung tài liệu bằng Ollama chạy local.

## Tính năng

- Upload PDF trực tiếp trên trình duyệt.
- Tự động trích xuất nội dung PDF bằng PyMuPDF/PyMuPDF4LLM.
- Chia chunk theo cấu trúc tài liệu, embedding bằng `nomic-embed-text`, lưu FAISS tại `data/indices_v2`.
- Hỏi đáp với context truy xuất từ PDF.
- Rerank context bằng `BAAI/bge-reranker-base`.

## Công nghệ

- **Backend**: FastAPI.
- **Frontend**: HTML/CSS/JS tĩnh tại `app/static/index.html`.
- **LLM local**: Ollama.
- **RAG**: LangChain, FAISS, PyMuPDF4LLM, sentence-transformers.

## Cài đặt

Yêu cầu: Python 3.10+ và Ollama.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Tạo file `.env` từ `.env.example`:

```text
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3.5:4b
```

Tải model Ollama:

```powershell
ollama pull qwen3.5:4b
ollama pull nomic-embed-text
```

## Chạy Web UI

```powershell
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

Mở trình duyệt tại:

```text
http://localhost:8000
```

## Cách dùng

1. Upload một file PDF.
2. Chờ hệ thống tạo index.
3. Đặt câu hỏi trong khung chat.

PDF được lưu tại `data/papers`. Index được lưu tại `data/indices_v2`.
