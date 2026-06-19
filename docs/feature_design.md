# DocMind Web RAG - Feature Design

## Muc tieu

DocMind la Web UI de nguoi dung upload PDF hoc thuat va hoi dap truc tiep tren noi dung tai lieu. Trong tam hien tai la mot workflow don gian: upload, index, chat.

## Luong chinh

```text
User
  -> Web UI
  -> FastAPI
  -> PDF storage: data/papers
  -> PaperRAG
  -> FAISS index: data/indices_v2
  -> Ollama
  -> Answer in Web UI
```

## Chuc nang hien co

- Upload PDF qua endpoint `/upload`.
- Trich xuat PDF bang PyMuPDF4LLM, fallback sang PyMuPDF.
- Chunk tai lieu theo heading/section.
- Tao embedding bang Ollama `nomic-embed-text`.
- Luu va load FAISS index theo `session_id`.
- Retrieve context va rerank bang CrossEncoder.
- Chat qua endpoint `/chat`.
- Ghi nho lich su hoi dap phia frontend va gui kem request.

## API

| Endpoint | Method | Muc dich |
| --- | --- | --- |
| `/` | GET | Tra ve Web UI |
| `/upload` | POST | Upload PDF va build index |
| `/chat` | POST | Hoi dap theo `session_id` |

## Pham vi hien tai

- Chi chay Web UI va FastAPI backend.
- File `.env` chi can cau hinh Ollama.

## Huong phat trien tiep

- Hien thi citation/context da dung cho moi cau tra loi.
- Cho phep quan ly nhieu tai lieu da upload.
- Them nut xoa session/index.
- Stream cau tra loi tu Ollama ve frontend.
