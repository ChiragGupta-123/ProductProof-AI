import logging
import os
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, MongoClient

from app.core.config import settings

log = logging.getLogger("productproof.db")

_client = None
_db = None
_indexes_ready = False


def get_db():
    """Return the MongoDB database handle.

    Raises RuntimeError with an actionable message when MongoDB is not
    configured. The connection is validated once with a ping and cached, so a
    missing/unreachable Atlas cluster does not add latency to every request.
    """
    global _client, _db
    if _db is not None:
        return _db
    cfg = settings()
    uri = cfg.mongodb_uri
    if not uri:
        raise RuntimeError(
            "MONGODB_URI is not configured. Add a real MongoDB Atlas connection "
            "string to backend/.env and restart."
        )
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        appname="productproof",
    )
    try:
        client.admin.command("ping")
    except Exception:
        client.close()
        raise
    _client = client
    _db = client[cfg.mongodb_db]
    return _db


def close_db() -> None:
    global _client, _db, _indexes_ready
    if _client is not None:
        _client.close()
    _client = None
    _db = None
    _indexes_ready = False


def audit_collection():
    return get_db()[settings().mongodb_audit_collection]


def image_collection():
    return get_db()[settings().mongodb_image_collection]


def init_db():
    """Create operational indexes once per process.

    The Atlas vector index itself is created separately by
    scripts/create_vector_index.py because it needs an Atlas search-index
    definition.
    """
    global _indexes_ready
    db = get_db()
    if _indexes_ready:
        return db
    audit = db[settings().mongodb_audit_collection]
    audit.create_index([("created_at", DESCENDING)])
    audit.create_index([("decision", ASCENDING)])
    audit.create_index([("human_review_required", ASCENDING)])
    images = db[settings().mongodb_image_collection]
    images.create_index([("phash", ASCENDING)])
    images.create_index([("created_at", DESCENDING)])
    db[settings().mongodb_rag_collection].create_index([("source", ASCENDING)])
    _indexes_ready = True
    return db


def storage_available() -> bool:
    try:
        get_db()
        return True
    except Exception:
        return False


def now():
    return datetime.now(timezone.utc)
