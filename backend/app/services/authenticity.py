import logging
from pathlib import Path

import imagehash
from PIL import Image

from app.models.db import image_collection, now

log = logging.getLogger("productproof.authenticity")

HAMMING_THRESHOLD = 6
MAX_SIGNATURES_SCANNED = 500


def phash(path):
    return str(imagehash.phash(Image.open(path).convert("RGB")))


def check_duplicates(path, session_id=None):
    """Compare this image against earlier uploads using perceptual hashing.

    Signatures are scoped by `session_id`: photos submitted together in one
    listing naturally resemble each other, and previously they were reported
    as duplicates of their own listing. Only *other* sessions are compared.
    """
    try:
        digest = phash(path)
        query = {} if session_id is None else {"session_id": {"$ne": session_id}}
        docs = list(
            image_collection()
            .find(query, {"phash": 1, "review_id": 1, "_id": 0})
            .sort("created_at", -1)
            .limit(MAX_SIGNATURES_SCANNED)
        )
        current = imagehash.hex_to_hash(digest)
        matches = []
        for doc in docs:
            stored = doc.get("phash")
            if not stored:
                continue
            try:
                distance = current - imagehash.hex_to_hash(stored)
            except Exception:  # noqa: BLE001 - skip corrupt signature rows
                continue
            if distance <= HAMMING_THRESHOLD:
                matches.append({
                    "review_id": doc.get("review_id"),
                    "hamming_distance": int(distance),
                })
        image_collection().insert_one({
            "phash": digest,
            "session_id": session_id,
            "review_id": None,
            "created_at": now(),
        })
        return {
            "phash": digest,
            "duplicate": bool(matches),
            "matches": matches[:10],
            "status": "ok",
        }
    except Exception as exc:  # noqa: BLE001 - storage is optional
        log.warning("pHash check unavailable: %s", exc)
        return {"phash": None, "duplicate": False, "matches": [], "status": "not_configured"}


def manipulation_heuristic(path):
    """Lightweight ELA-style indicator. This is a signal, not proof of forgery."""
    try:
        image = Image.open(path).convert("RGB")
        tmp = Path(path).with_suffix(".ela.jpg")
        image.save(tmp, "JPEG", quality=88)
        recorded = Image.open(tmp).convert("RGB")
        import numpy as np

        original = np.asarray(image, dtype=np.int16)
        recompressed = np.asarray(recorded, dtype=np.int16)
        score = float(np.mean(np.abs(original - recompressed)))
        tmp.unlink(missing_ok=True)
        return {
            "ela_score": round(score, 2),
            "concern": "high" if score > 12 else "medium" if score > 7 else "low",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ela_score": None, "concern": "unknown", "error": str(exc)}
