import logging
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.util import find_spec
from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.models.db import audit_collection, image_collection, init_db, now
from app.schemas import HumanReview
from app.services.ocr import extract_text
from app.services.preprocess import image_metrics, is_decodable, preprocess_image
from app.services.verification import verify
from app.services.vlm import analyze

log = logging.getLogger("productproof.routes")
router = APIRouter()

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
MAX_SIDE_NOTE = "JPG, PNG or WebP"


def _storage_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=(
            "Review storage is not configured. Set a real MONGODB_URI in "
            "backend/.env to persist and review verification records."
        ),
    )


def _object_id(review_id: str) -> ObjectId:
    try:
        return ObjectId(review_id)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid review id")


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text[:limit] if text else None


def _store_upload(image: UploadFile, directory: Path, max_bytes: int) -> str:
    """Persist one uploaded image, enforcing type/size limits as it streams."""
    name = image.filename or "image"
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"'{name}' is not supported. Upload {MAX_SIDE_NOTE} images.",
        )
    max_mb = round(max_bytes / (1024 * 1024), 1)
    target = directory / f"{uuid.uuid4().hex}{suffix}"
    total = 0
    try:
        with open(target, "wb") as out:
            while chunk := image.file.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"'{name}' exceeds the {max_mb} MB per-image limit.",
                    )
                out.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    if total == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"'{name}' is empty.")
    if not is_decodable(str(target)):
        target.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"'{name}' could not be decoded as an image.",
        )
    return str(target)


def _process_one(idx, raw, listing):
    started = time.perf_counter()
    processed = preprocess_image(raw)
    t1 = time.perf_counter()
    ocr = extract_text(processed)
    t2 = time.perf_counter()
    vision = analyze(processed, listing)
    t3 = time.perf_counter()
    metrics = image_metrics(raw)
    t4 = time.perf_counter()
    log.info(
        "image[%d] preprocess=%.2fs ocr=%.2fs vision=%.2fs metrics=%.2fs total=%.2fs",
        idx, t1 - started, t2 - t1, t3 - t2, t4 - t3, t4 - started,
    )
    return idx, processed, ocr, vision, metrics


@router.get("/health")
def health():
    try:
        init_db()
        storage = "connected"
    except Exception as exc:  # noqa: BLE001 - health must answer even when storage is down
        storage = f"unavailable: {exc}"
    return {
        "status": "ok" if storage == "connected" else "degraded",
        "mongodb": storage,
        "version": "2.1.0",
    }


@router.post("/verify")
async def verify_listing(
    title: str = Form(..., min_length=1, max_length=200),
    description: str = Form("", max_length=5000),
    brand: str = Form("", max_length=120),
    category: str = Form("", max_length=120),
    color: str = Form("", max_length=120),
    model: str = Form("", max_length=120),
    sku: str = Form("", max_length=120),
    images: list[UploadFile] = File(...),
):
    cfg = settings()
    if not title.strip():
        raise HTTPException(status_code=400, detail="A listing title is required.")
    if not images:
        raise HTTPException(status_code=400, detail="At least one image is required.")
    if len(images) > cfg.max_images:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {cfg.max_images} images per verification.",
        )

    listing = {
        "title": title.strip(),
        "description": description.strip(),
        "brand": _clean(brand, 120),
        "category": _clean(category, 120),
        "color": _clean(color, 120),
        "model": _clean(model, 120),
        "sku": _clean(sku, 120),
    }

    session_id = uuid.uuid4().hex
    session_dir = cfg.upload_path / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = cfg.max_image_mb * 1024 * 1024

    try:
        raw = [_store_upload(image, session_dir, max_bytes) for image in images]
        results = [None] * len(raw)
        with ThreadPoolExecutor(max_workers=min(len(raw), 4)) as pool:
            futures = [pool.submit(_process_one, i, p, listing) for i, p in enumerate(raw)]
            for future in as_completed(futures):
                try:
                    idx, processed, ocr, vision, metrics = future.result()
                except Exception as exc:  # noqa: BLE001 - one bad image must not 500 the request
                    log.exception("Image processing failed")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Image processing failed: {exc}",
                    ) from exc
                results[idx] = (processed, ocr, vision, metrics)

        paths = [item[0] for item in results]
        ocr = [item[1] for item in results]
        vision = [item[2] for item in results]
        metrics = [item[3] for item in results]

        result = verify(listing, paths, ocr, vision, metrics, session_id=session_id)
        payload = {
            "listing": listing,
            "decision": result["decision"],
            "correctness_score": result["correctness_score"],
            "confidence": result["confidence"],
            "human_review_required": result["human_review_required"],
            "attributes": result["attributes"],
            "image_analysis": vision,
            "ocr_text": ocr,
            "similarity": result["similarities"],
            "product_evidence": result["product_evidence"],
            "policy_evidence": result["policy_evidence"],
            "mismatches": result["mismatches"],
            "explanation": result["explanation"],
            "text_image_match_pct": result["text_image_match_pct"],
            "image_quality_pct": result["image_quality_pct"],
            "quality_checks": result["quality_checks"],
            "ml_fusion": result["ml_fusion"],
            "authenticity": result["authenticity"],
            "manipulation": result["manipulation"],
            "completeness": result["completeness"],
            "llm_report": result["llm_report"],
        }

        document = {**payload, "session_id": session_id, "created_at": now(),
                    "reviewer_note": "", "review_history": []}
        persisted = False
        try:
            record = audit_collection().insert_one(document)
            review_id = str(record.inserted_id)
            persisted = True
            # Link the image signatures created during this request to the review.
            try:
                image_collection().update_many(
                    {"session_id": session_id}, {"$set": {"review_id": review_id}}
                )
            except Exception:  # noqa: BLE001 - linkage is best-effort
                log.warning("Could not link image signatures to review %s", review_id)
        except Exception:  # noqa: BLE001 - verification is still useful without storage
            log.exception("MongoDB audit insert failed")
            review_id = "local-no-db"

        payload["review_id"] = review_id
        payload["persisted"] = persisted
        return payload
    finally:
        shutil.rmtree(session_dir, ignore_errors=True)


@router.post("/reviews/{review_id}")
def human_review(review_id: str, review: HumanReview):
    oid = _object_id(review_id)
    try:
        collection = audit_collection()
        result = collection.update_one(
            {"_id": oid},
            {
                "$set": {
                    "decision": review.decision,
                    "reviewer_note": review.reviewer_note,
                    "human_review_required": False,
                    "reviewed_at": now(),
                },
                "$push": {
                    "review_history": {
                        "decision": review.decision,
                        "reviewer_note": review.reviewer_note,
                        "reviewed_at": now(),
                    }
                },
            },
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("Review update failed: %s", exc)
        raise _storage_error() from exc
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"status": "updated", "review_id": review_id, "decision": review.decision}


@router.get("/reviews")
def reviews():
    try:
        rows = audit_collection().find(
            {},
            {
                "listing": 1, "title": 1, "decision": 1, "correctness_score": 1,
                "confidence": 1, "human_review_required": 1, "created_at": 1,
                "reviewer_note": 1,
            },
        ).sort("created_at", -1).limit(200)
        out = []
        for row in rows:
            created = row.get("created_at")
            out.append({
                "id": str(row["_id"]),
                "created_at": created.isoformat() if created else None,
                "title": row.get("title") or row.get("listing", {}).get("title", ""),
                "decision": row.get("decision"),
                "correctness_score": row.get("correctness_score", 0),
                "confidence": row.get("confidence", 0),
                "human_review_required": row.get("human_review_required", False),
                "reviewer_note": row.get("reviewer_note", ""),
            })
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("Review listing failed: %s", exc)
        raise _storage_error() from exc


@router.get("/reviews/{review_id}")
def review_detail(review_id: str):
    oid = _object_id(review_id)
    try:
        row = audit_collection().find_one({"_id": oid})
    except Exception as exc:  # noqa: BLE001
        log.warning("Review lookup failed: %s", exc)
        raise _storage_error() from exc
    if not row:
        raise HTTPException(status_code=404, detail="Review not found")
    row["review_id"] = str(row.pop("_id"))
    row["persisted"] = True
    for key in ("image_paths", "session_id"):
        row.pop(key, None)
    for key in ("created_at", "reviewed_at"):
        value = row.get(key)
        if value is not None and hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    for entry in row.get("review_history") or []:
        value = entry.get("reviewed_at")
        if value is not None and hasattr(value, "isoformat"):
            entry["reviewed_at"] = value.isoformat()
    return row


@router.get("/analytics")
def analytics():
    try:
        docs = list(audit_collection().find(
            {},
            {"decision": 1, "correctness_score": 1, "confidence": 1,
             "human_review_required": 1},
        ))
    except Exception as exc:  # noqa: BLE001
        log.warning("Analytics failed: %s", exc)
        raise _storage_error() from exc
    total = len(docs)
    approved = sum(doc.get("decision") == "APPROVE" for doc in docs)
    rejected = sum(doc.get("decision") == "REJECT" for doc in docs)
    queue = sum(bool(doc.get("human_review_required")) for doc in docs)
    avg = round(sum(doc.get("correctness_score", 0) for doc in docs) / total, 1) if total else None
    avg_conf = round(sum(doc.get("confidence", 0) for doc in docs) / total, 3) if total else None
    return {
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "review_queue": queue,
        "pass_rate": round(100 * approved / total, 1) if total else None,
        "avg_correctness": avg,
        "avg_confidence": avg_conf,
    }


@router.get("/system-status")
def system_status():
    cfg = settings()
    return {
        "version": "2.1.0",
        "gemini_configured": bool(cfg.google_api_key),
        "groq_configured": bool(cfg.groq_api_key),
        "mongodb_configured": bool(cfg.mongodb_uri),
        "clip_available": find_spec("transformers") is not None,
        "ocr_available": find_spec("easyocr") is not None,
        "yolo_available": find_spec("ultralytics") is not None,
        "yolo_model": cfg.ultralytics_model,
        "ocr_languages": [item.strip() for item in cfg.ocr_languages.split(",") if item.strip()],
        "max_images": cfg.max_images,
        "max_image_mb": cfg.max_image_mb,
        "thresholds": {
            "approve": cfg.approve_threshold,
            "review": cfg.review_threshold,
            "min_auto_confidence": cfg.min_auto_confidence,
        },
    }
