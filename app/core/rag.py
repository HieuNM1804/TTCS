"""RAG — PDF extraction, section-aware chunking, FAISS retrieval."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import requests
import pymupdf4llm
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

log = logging.getLogger(__name__)

_index_cache: dict[str, tuple] = {}

EXCLUDE_KEYWORDS = [
    "reference", "bibliography", "bibliograph",
    "acknowledgment", "acknowledgement",
    "appendix", "supplementary", "supplement",
    "ablation",
]


class PaperRAG:

    def __init__(self, arxiv_id: str, base_url: str = "http://localhost:11434",
                 model: str = "nomic-embed-text") -> None:
        self.arxiv_id = arxiv_id
        self.pdf_path = Path("data/papers") / f"{arxiv_id}.pdf"
        self.index_path = Path("data/indices_v2") / arxiv_id
        self.pdf_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.embeddings = OllamaEmbeddings(base_url=base_url, model=model)

    def download(self) -> None:
        if self.pdf_path.exists():
            return
        url = f"https://arxiv.org/pdf/{self.arxiv_id}.pdf"
        log.info("Downloading PDF: %s", url)
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(self.pdf_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=8192):
                fh.write(chunk)

    @staticmethod
    def _normalize_headings(md_text: str) -> str:
        """Convert bold-only lines to ## headings (strict rules)."""
        def _is_heading(match: re.Match) -> str:
            text = match.group(1).strip()
            if len(text) > 60:
                return match.group(0)
            if text.endswith('.') or '. ' in text:
                return match.group(0)
            if any(c in text for c in ('@', '{', ',', '**')):
                return match.group(0)
            if text[0].islower():
                return match.group(0)
            return f'## {text}'

        return re.sub(
            r'^\s*\*\*(.{3,100}?)\*\*\s*$',
            _is_heading, md_text, flags=re.MULTILINE,
        )

    @staticmethod
    def _protect_tables(md_text: str) -> str:
        """Join table rows so the splitter won't cut mid-table."""
        MARKER = "\x00"
        lines = md_text.split("\n")
        result = []
        in_table = False
        for line in lines:
            stripped = line.strip()
            is_table = stripped.startswith("|") or stripped.startswith("|-")
            if is_table:
                if in_table:
                    result.append(MARKER + line)
                else:
                    in_table = True
                    result.append(line)
            else:
                in_table = False
                result.append(line)
        return "\n".join(result)

    def _extract_sections(self) -> list[Document]:
        try:
            md_text = pymupdf4llm.to_markdown(str(self.pdf_path))
        except Exception as exc:
            log.warning("pymupdf4llm failed (%s), falling back to standard pymupdf", exc)
            import pymupdf
            doc = pymupdf.open(str(self.pdf_path))
            md_text = "\n\n".join(page.get_text() for page in doc)
            doc.close()
        md_text = self._normalize_headings(md_text)
        md_text = self._protect_tables(md_text)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=3500, chunk_overlap=700,
            separators=["\n## ", "\n### ", "\n#### ", "\n\n", "\n", ". ", " "],
        )
        all_docs = splitter.create_documents(
            [md_text], metadatas=[{"arxiv_id": self.arxiv_id}],
        )

        # Restore tables + propagate section headings to continuation chunks
        last_heading = ""
        for doc in all_docs:
            doc.page_content = doc.page_content.replace("\x00", "\n")
            heading_match = re.match(r'^(#{1,6}\s+.+)', doc.page_content)
            if heading_match and '**' not in heading_match.group(1):
                last_heading = heading_match.group(1)
            elif last_heading:
                doc.page_content = last_heading + "\n\n" + doc.page_content

        # Filter noise
        chunks = []
        for doc in all_docs:
            if len(doc.page_content.strip()) < 50:
                continue
            lower = doc.page_content[:300].lower()
            if any(kw in lower for kw in EXCLUDE_KEYWORDS):
                continue
            chunks.append(doc)

        log.info("Chunking: %d chars → %d chunks (filtered from %d)",
                 len(md_text), len(chunks), len(all_docs))
        return chunks

    def build(self) -> None:
        self.download()
        if self._index_exists():
            log.info("Index already exists: %s", self.index_path)
            return
        log.info("Building index for %s …", self.arxiv_id)
        chunks = self._extract_sections()
        if not chunks:
            raise ValueError(f"No chunks extracted from {self.pdf_path}")
        vectorstore = FAISS.from_documents(chunks, self.embeddings)
        vectorstore.save_local(str(self.index_path))
        log.info("Index built — %d chunks", len(chunks))

    def _index_exists(self) -> bool:
        return (self.index_path / "index.faiss").exists() and \
               (self.index_path / "index.pkl").exists()

    def _load_index(self) -> tuple:
        if self.arxiv_id in _index_cache:
            return _index_cache[self.arxiv_id]
        log.info("Loading index from disk: %s", self.index_path)
        vectorstore = FAISS.load_local(
            str(self.index_path), self.embeddings,
            allow_dangerous_deserialization=True,
        )
        chunks = list(vectorstore.docstore._dict.values())
        _index_cache[self.arxiv_id] = (vectorstore, chunks)
        return vectorstore, chunks

    def retrieve(self, query: str, k: int = 4) -> str:
        self.build()
        vectorstore, _ = self._load_index()
        retriever = vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": 20, "lambda_mult": 0.5},
        )
        results = retriever.invoke(query)
        return "\n\n".join(doc.page_content for doc in results[:k])

    def retrieve_docs(self, query: str, k: int = 4) -> list[Document]:
        self.build()
        vectorstore, _ = self._load_index()
        retriever = vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": 20, "lambda_mult": 0.5},
        )
        return retriever.invoke(query)[:k]
