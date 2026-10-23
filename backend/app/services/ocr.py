"""Text extraction from product images using EasyOCR.

Two things made the old PaddleOCR version slow/broken:
  1. paddleocr was never actually in requirements.txt, so every call raised
     ImportError and silently returned [] - OCR wasn't running at all.
  2. Even if it had been installed, `PaddleOCR(lang="en")` was constructed
     from scratch on every single request. Loading OCR model weights from
     disk takes real time - doing that per-request instead of once at
     startup is a common source of multi-second "mystery" latency.

This version loads the EasyOCR reader exactly once (cached at module level)
and reuses it for every request. It also downsizes the image before running
OCR specifically, since OCR speed scales with pixel count and we don't need
full resolution to read text.
"""
import logging
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger("productproof.ocr")


def _languages() -> list[str]:
    languages = [
        item.strip() for item in settings().ocr_languages.split(",") if item.strip()
    ]
    return languages or ["en"]


def _max_dim() -> int:
    # Guard against a malformed OCR_MAX_DIM taking the process down at import.
    try:
        return max(200, int(settings().ocr_max_dim))
    except (TypeError, ValueError):
        return 1000


@lru_cache
def _reader():
    import easyocr

    cfg = settings()
    languages = _languages()
    logger.info(
        "Loading EasyOCR reader (langs=%s, gpu=%s) - this happens once per process",
        languages, cfg.ocr_use_gpu,
    )
    return easyocr.Reader(languages, gpu=cfg.ocr_use_gpu, verbose=False)


def extract_text(path: str) -> list[str]:
    try:
        import cv2
        img = cv2.imread(path)
        if img is None:
            return []
        h, w = img.shape[:2]
        max_dim = _max_dim()
        scale = min(1.0, max_dim / max(h, w))
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        results = _reader().readtext(
            img,
            detail=0,          # skip boxes/confidences we don't use - faster to assemble
            paragraph=True,    # merge nearby text into fewer, more useful strings
            canvas_size=max_dim,
        )
        return [str(t).strip() for t in results if str(t).strip()]
    except Exception as exc:  # noqa: BLE001
        logger.exception("OCR failed for %s: %s", path, exc)
        return []
