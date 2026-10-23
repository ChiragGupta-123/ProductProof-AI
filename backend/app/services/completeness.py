import logging
import os
import re
from functools import lru_cache
from threading import Lock

log = logging.getLogger("productproof.completeness")

CATEGORY_MAP = {
    "phone": ["cell phone"], "smartphone": ["cell phone"], "mobile": ["cell phone"],
    "laptop": ["laptop"], "computer": ["laptop"], "backpack": ["backpack"],
    "handbag": ["handbag"], "bottle": ["bottle"], "cup": ["cup"],
    "keyboard": ["keyboard"], "mouse": ["mouse"], "tv": ["tv"], "television": ["tv"],
    "camera": ["camera"], "watch": ["watch"], "book": ["book"], "bicycle": ["bicycle"],
}

# Ultralytics models are not guaranteed to be thread-safe; verification fans
# out across images, so serialize inference rather than risk corruption.
_lock = Lock()


def _claims(title, category):
    text = f"{title} {category or ''}".lower()
    out = []
    for key, values in CATEGORY_MAP.items():
        if re.search(rf"\b{re.escape(key)}s?\b", text):
            out.extend(values)
    return sorted(set(out))


@lru_cache(maxsize=1)
def _model():
    from ultralytics import YOLO

    return YOLO(os.getenv("ULTRALYTICS_MODEL", "yolo11n.pt"))


def detect(path):
    """Return detected objects, or None when the detector itself is unavailable.

    None is deliberately distinct from [] so a missing YOLO installation does
    not look like "the product is absent from the photo".
    """
    try:
        with _lock:
            result = _model()(path, verbose=False)[0]
        names = result.names
        labels = []
        if result.boxes is not None:
            for cls, conf in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist()):
                labels.append({"label": names[int(cls)], "confidence": round(float(conf), 3)})
        return labels
    except Exception as exc:  # noqa: BLE001 - optional local model
        log.warning("YOLO completeness check unavailable: %s", exc)
        return None


def check(path, title, category):
    claimed = _claims(title, category)
    # Skip the detector entirely when the listing claims no object we can map.
    # Previously this loaded/downloaded YOLO weights on every request even when
    # the result was immediately NOT_APPLICABLE.
    if not claimed:
        return {"status": "NOT_APPLICABLE", "claimed": [], "detected": [], "missing": []}
    detected = detect(path)
    if detected is None:
        return {
            "status": "NOT_AVAILABLE",
            "claimed": claimed,
            "detected": [],
            "missing": [],
            "detail": "Object detector unavailable; completeness was not scored.",
        }
    labels = {d["label"] for d in detected if d["confidence"] >= 0.35}
    missing = [item for item in claimed if item not in labels]
    return {
        "status": "PASS" if not missing else "REVIEW",
        "claimed": claimed,
        "detected": detected,
        "missing": missing,
    }
