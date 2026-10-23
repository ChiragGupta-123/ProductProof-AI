"""XGBoost evidence-fusion layer (advisory until validated).

WHY THIS IS OFF BY DEFAULT
---------------------------
XGBoost is a genuinely good fit for this problem - fusing a handful of
mixed, often-missing numeric/categorical signals (attribute matches, CLIP
similarity, VLM confidence, image-quality metrics) into a decision is
exactly the kind of tabular problem gradient-boosted trees are built for,
and XGBoost handles missing values natively, which matters here since half
these features can be None.

But it only helps if it's trained on real labels. Right now the only labels
this app can produce come from a human confirming or overriding a decision
via the review endpoint. Training on a handful of self-generated examples
would just make the model memorize (or worse, overfit noise in) the existing
rule-based logic in verification.py - no accuracy gain, plus a black-box
model and a new dependency. So:

  - This module refuses to train until MIN_TRAINING_SAMPLES reviewed records
    exist (see train_fusion_model.py).
  - Even once trained, verify() in verification.py treats its output as
    advisory only (returned in the response for visibility) and does NOT let
    it override the deterministic rule-based decision, the same way the LLM
    reasoning step is treated as advisory rather than authoritative. This
    can be revisited once the model has been validated against a real held-
    out test set - don't flip it to decision-affecting before that.
"""
import logging
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger("productproof.fusion")

LABELS = ["REJECT", "REVIEW", "APPROVE"]  # fixed class order used everywhere below

FEATURE_NAMES = [
    "mismatch_count",
    "match_count",
    "unknown_attribute_count",
    "text_image_match_pct",
    "image_quality_pct",
    "avg_same_product_likelihood",
    "manipulation_score",       # none=0, low=1, medium=2, high=3
    "avg_sharpness",
    "min_resolution_px",
    "avg_fill_ratio",
    "ocr_text_found",           # 0/1
    "num_images",
]

_MANIPULATION_SCORE = {"none": 0, "low": 1, "medium": 2, "high": 3, "unknown": 0}


def extract_features(listing, attributes, vision, quality_checks, similarities, ocr, image_metrics_list=None) -> dict:
    """Pulls a flat, fixed-order feature dict out of everything verify() has
    already computed. Every value here is something the pipeline genuinely
    measured - nothing here is invented for the model's benefit."""
    mismatch_count = sum(1 for a in attributes if a["status"] == "MISMATCH")
    match_count = sum(1 for a in attributes if a["status"] == "MATCH")
    unknown_count = sum(1 for a in attributes if a["status"] == "UNKNOWN")

    likelihoods = [v.get("same_product_likelihood") for v in vision if isinstance(v.get("same_product_likelihood"), (int, float))]
    avg_likelihood = sum(likelihoods) / len(likelihoods) if likelihoods else None

    concerns = [_MANIPULATION_SCORE.get(v.get("manipulation_concern", "unknown"), 0) for v in vision]
    manipulation_score = max(concerns) if concerns else 0

    text_match = None
    known_sims = [s["image_text"] for s in similarities if s.get("image_text") is not None]
    if known_sims:
        text_match = sum(known_sims) / len(known_sims)

    metrics_list = image_metrics_list or []
    sharp_vals = [m["sharpness"] for m in metrics_list if m.get("sharpness") is not None]
    avg_sharpness = sum(sharp_vals) / len(sharp_vals) if sharp_vals else None

    res_vals = [min(m["width"], m["height"]) for m in metrics_list if m.get("width") and m.get("height")]
    min_resolution_px = min(res_vals) if res_vals else None

    fill_vals = [m["fill_ratio"] for m in metrics_list if m.get("fill_ratio") is not None]
    avg_fill_ratio = sum(fill_vals) / len(fill_vals) if fill_vals else None

    image_quality_pct = None  # filled in by caller, which already computed this in verify()

    return {
        "mismatch_count": mismatch_count,
        "match_count": match_count,
        "unknown_attribute_count": unknown_count,
        "text_image_match_pct": text_match,
        "image_quality_pct": image_quality_pct,
        "avg_same_product_likelihood": avg_likelihood,
        "manipulation_score": manipulation_score,
        "avg_sharpness": avg_sharpness,
        "min_resolution_px": min_resolution_px,
        "avg_fill_ratio": avg_fill_ratio,
        "ocr_text_found": 1 if any(ocr) else 0,
        "num_images": len(vision),
    }


@lru_cache
def _model():
    path = settings().fusion_model_file
    if not path.exists():
        return None
    try:
        import xgboost as xgb
        model = xgb.XGBClassifier()
        model.load_model(str(path))
        return model
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load fusion model at %s: %s", path, exc)
        return None


def predict(features: dict):
    """Returns {label, probabilities} or None if no trained model is
    available yet. Caller must NOT treat this as authoritative - see the
    module docstring."""
    model = _model()
    if model is None:
        return None
    try:
        import pandas as pd
        row = {k: features.get(k) for k in FEATURE_NAMES}
        df = pd.DataFrame([row])
        proba = model.predict_proba(df)[0]
        pred_idx = int(proba.argmax())
        return {
            "label": LABELS[pred_idx],
            "probabilities": {LABELS[i]: round(float(p), 4) for i, p in enumerate(proba)},
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fusion model prediction failed: %s", exc)
        return None
