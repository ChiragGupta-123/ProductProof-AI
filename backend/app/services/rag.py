"""MongoDB Atlas Vector Search RAG.

Trusted documents are chunked with LangChain and embedded with Gemini. Vectors
are stored in MongoDB Atlas and retrieved with the $vectorSearch aggregation
stage. If Atlas/vector search is not configured during local development, the
module falls back to a small keyword retrieval over the local knowledge files.
"""
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from app.core.config import settings
from app.models.db import get_db

log = logging.getLogger("productproof.rag")

MAX_FALLBACK_CHARS = 1200
STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "has", "have", "not", "but", "you", "your", "its", "into", "than", "then",
}


@lru_cache
def _embeddings():
    api_key = settings().google_api_key
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not configured")
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(
        model=settings().gemini_embedding_model,
        google_api_key=api_key,
    )


def _embed(text):
    return _embeddings().embed_query(text)


def _knowledge_dir() -> Path:
    configured = os.getenv("KNOWLEDGE_DIR")
    return settings().resolve_path(configured) if configured else settings().knowledge_dir


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in STOPWORDS
    }


@lru_cache(maxsize=32)
def _read_local_documents() -> tuple[tuple[str, str], ...]:
    documents = []
    base = _knowledge_dir()
    if not base.exists():
        log.warning("Knowledge directory %s does not exist", base)
        return tuple()
    for path in sorted(base.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        documents.append((path.name, text))
    return tuple(documents)


def _keyword_fallback(query, k=6):
    query_tokens = _tokens(query)
    docs = []
    for source, text in _read_local_documents():
        overlap = len(query_tokens & _tokens(text))
        if overlap:
            docs.append({
                "source": source,
                "text": text[:MAX_FALLBACK_CHARS],
                "relevance": round(min(0.99, overlap / max(len(query_tokens), 1) * 0.5), 3),
            })
    docs.sort(key=lambda item: item["relevance"], reverse=True)
    return docs[:k]


def retrieve(query, k=6):
    try:
        db = get_db()
        collection = db[settings().mongodb_rag_collection]
        vector = _embed(query)
        pipeline = [
            {"$vectorSearch": {
                "index": settings().mongodb_vector_index,
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": max(50, k * 10),
                "limit": k,
            }},
            {"$project": {
                "_id": 0, "source": 1, "text": 1, "metadata": 1,
                "relevance": {"$meta": "vectorSearchScore"},
            }},
        ]
        return list(collection.aggregate(pipeline))
    except Exception as exc:  # noqa: BLE001 - local fallback keeps the pipeline usable
        log.info("Atlas vector retrieval unavailable; using local fallback: %s", exc)
        return _keyword_fallback(query, k)


def ingest_documents():
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    db = get_db()
    collection = db[settings().mongodb_rag_collection]
    documents = []
    for source, text in _read_local_documents():
        documents.append(Document(page_content=text, metadata={"source": source}))
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=900, chunk_overlap=150
    ).split_documents(documents)
    for index, chunk in enumerate(chunks):
        collection.update_one(
            {"source": chunk.metadata.get("source"), "chunk_id": index},
            {"$set": {
                "source": chunk.metadata.get("source"),
                "chunk_id": index,
                "text": chunk.page_content,
                "metadata": chunk.metadata,
                "embedding": _embed(chunk.page_content),
            }},
            upsert=True,
        )
    return len(chunks)
