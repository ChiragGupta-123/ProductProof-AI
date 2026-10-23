"""Seed trusted knowledge into MongoDB Atlas Vector Search.

Run from the backend directory:  python scripts/seed_demo.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from app.core.config import settings  # noqa: E402


def main() -> int:
    cfg = settings()
    if not cfg.mongodb_uri:
        print("MONGODB_URI is not configured in backend/.env - nothing to seed.")
        return 1
    if not cfg.google_api_key:
        print("GOOGLE_API_KEY is required to create Gemini embeddings.")
        return 1

    from app.services.rag import ingest_documents

    count = ingest_documents()
    print(f"Ingested {count} knowledge chunks into MongoDB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
