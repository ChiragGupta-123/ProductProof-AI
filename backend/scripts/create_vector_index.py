"""Create the Atlas Vector Search index used by RAG retrieval.

Run from the backend directory:  python scripts/create_vector_index.py

The index must exist (and finish building) before /verify can retrieve trusted
knowledge through $vectorSearch. Until then the service falls back to local
keyword retrieval.
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from pymongo import MongoClient  # noqa: E402
from pymongo.operations import SearchIndexModel  # noqa: E402

from app.core.config import settings  # noqa: E402


def main() -> int:
    cfg = settings()
    if not cfg.mongodb_uri:
        print("MONGODB_URI is not configured in backend/.env.")
        return 1
    try:
        dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
    except ValueError:
        print("EMBEDDING_DIMENSIONS must be an integer (default 768 for Gemini text-embedding-004).")
        return 1

    client = MongoClient(cfg.mongodb_uri, serverSelectionTimeoutMS=10000)
    collection = client[cfg.mongodb_db][cfg.mongodb_rag_collection]
    model = SearchIndexModel(
        definition={
            "fields": [{
                "type": "vector",
                "numDimensions": dimensions,
                "path": "embedding",
                "similarity": "cosine",
            }]
        },
        name=cfg.mongodb_vector_index,
        type="vectorSearch",
    )
    try:
        print(collection.create_search_index(model=model))
        print(
            "Vector Search index requested. Wait for Atlas to finish building it, "
            "then run scripts/seed_demo.py."
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Could not create the vector index: {exc}")
        print("Vector Search indexes are only available on MongoDB Atlas (not local MongoDB).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
