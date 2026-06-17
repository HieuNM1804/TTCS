import time
import shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
import logging

from app.core.config import OLLAMA_BASE_URL
from app.core.rag import PaperRAG
from app.services.telegram_utils import query_ollama

log = logging.getLogger(__name__)

app = FastAPI(title="Daily Paper Web RAG")

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
def get_index():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<html><body><h1>Index file not found</h1></body></html>"

@app.post("/upload")
def upload_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    file_id = f"custom_web_{int(time.time())}"
    dest_path = Path("data/papers") / f"{file_id}.pdf"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        log.info(f"File saved to {dest_path}. Building index...")
        rag = PaperRAG(file_id, OLLAMA_BASE_URL, "nomic-embed-text")
        rag.build()
        log.info(f"Index built for {file_id}")
        
        return {"session_id": file_id, "filename": file.filename, "message": "Indexed successfully"}
    except Exception as e:
        log.error(f"Error processing upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ChatRequest(BaseModel):
    session_id: str
    question: str
    history: List[dict] = []

@app.post("/chat")
def chat(request: ChatRequest):
    try:
        rag = PaperRAG(request.session_id, OLLAMA_BASE_URL, "nomic-embed-text")
        context = rag.retrieve(request.question, k=4)
        
        # format memory
        memory_text = ""
        if request.history:
            memory_text = "\n[Lịch sử hỏi đáp gần đây trong phiên]\n"
            for item in request.history:
                memory_text += f"Người dùng: {item['q']}\nTrả lời: {item['a']}\n\n"
                
        prompt = f"""Bạn là trợ lý AI chuyên phân tích tài liệu PDF. Trả lời câu hỏi dựa trên thông tin trích xuất bên dưới.

[Trích xuất từ PDF]
{context[:3000]}
{memory_text}
[Câu hỏi]
"{request.question}"

[Yêu cầu]
- Trả lời đi thẳng vào trọng tâm, chỉ liệt kê ý chính.
- Định dạng bằng Markdown (có thể dùng in đậm, danh sách).
- KHÔNG dùng tiếng Trung. Giữ nguyên thuật ngữ tiếng Anh gốc nếu không dịch được.
"""
        answer = query_ollama(prompt, num_predict=2048, temperature=0.1)
        
        return {"answer": answer}
    except Exception as e:
        log.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Configure root logger to output to stdout
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=8000)
