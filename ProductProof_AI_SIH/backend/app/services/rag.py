"""Retrieval-augmented context from the trusted knowledge base (policy +
product catalog docs), embedded with Gemini instead of OpenAI."""
import logging
import os
from pathlib import Path

logger = logging.getLogger("productproof.rag")


def _embeddings():
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")
    return GoogleGenerativeAIEmbeddings(
        model=os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004"),
        google_api_key=api_key,
    )


def store():
    from langchain_chroma import Chroma
    return Chroma(
        collection_name="productproof_knowledge",
        embedding_function=_embeddings(),
        persist_directory=os.getenv("CHROMA_DIR", "./data/chroma"),
    )


def retrieve(query, k=6):
    try:
        docs = store().similarity_search_with_relevance_scores(query, k=k)
        return [
            {"source": d.metadata.get("source", "knowledge-base"), "text": d.page_content, "relevance": float(score)}
            for d, score in docs
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG retrieval unavailable: %s", exc)
        return []


def ingest_documents():
    from langchain_chroma import Chroma
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_core.documents import Document

    docs = []
    for p in Path("./data/knowledge").rglob("*"):
        if p.suffix.lower() in {".md", ".txt"}:
            docs.append(Document(page_content=p.read_text(encoding="utf-8"), metadata={"source": p.name}))
    if not docs:
        return 0
    chunks = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150).split_documents(docs)
    Chroma.from_documents(
        chunks, _embeddings(),
        collection_name="productproof_knowledge",
        persist_directory=os.getenv("CHROMA_DIR", "./data/chroma"),
    )
    return len(chunks)
