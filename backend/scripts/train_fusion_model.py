"""Train XGBoost evidence fusion from real human-reviewed MongoDB records.

The training script deliberately refuses to train on too little or too
imbalanced data. Labels come from the final reviewer decision stored in
MongoDB Atlas (`decision` is updated when a human overrides a review).

Run from the backend directory:  python scripts/train_fusion_model.py
"""
import sys
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from app.core.config import settings  # noqa: E402
from app.models.db import audit_collection  # noqa: E402
from app.services.fusion import FEATURE_NAMES, LABELS, extract_features  # noqa: E402

PROJECTION = {
    "decision": 1,
    "listing": 1,
    "attributes": 1,
    "image_analysis": 1,
    "quality_checks": 1,
    "similarity": 1,
    "ocr_text": 1,
    "image_quality_pct": 1,
    "result_json": 1,
}


def load_rows():
    return list(audit_collection().find({}, PROJECTION))


def _payload(record: dict) -> dict | None:
    """Reviews are stored flattened; older records may nest everything under
    `result_json`. Support both instead of silently producing an empty dataset.
    """
    nested = record.get("result_json")
    if isinstance(nested, str):
        import json

        try:
            nested = json.loads(nested)
        except Exception:  # noqa: BLE001
            nested = None
    if isinstance(nested, dict):
        return nested
    if record.get("attributes") or record.get("listing"):
        return record
    return None


def build_dataset(records):
    import pandas as pd

    rows, labels = [], []
    for record in records:
        payload = _payload(record)
        if not payload:
            continue
        features = extract_features(
            payload.get("listing", {}),
            payload.get("attributes", []),
            payload.get("image_analysis", []),
            payload.get("quality_checks", []),
            payload.get("similarity", []),
            payload.get("ocr_text", []),
            [],
        )
        features["image_quality_pct"] = payload.get("image_quality_pct")
        decision = record.get("decision", "REVIEW")
        if decision not in LABELS:
            decision = "REVIEW"
        rows.append({name: features.get(name) for name in FEATURE_NAMES})
        labels.append(decision)
    return pd.DataFrame(rows, columns=FEATURE_NAMES), labels


def main() -> int:
    cfg = settings()
    if not cfg.mongodb_uri:
        print("MONGODB_URI is not configured in backend/.env.")
        return 1

    records = load_rows()
    if len(records) < cfg.min_training_samples:
        print(
            f"Only {len(records)} records found; need {cfg.min_training_samples}. "
            "Refusing to train on too little data."
        )
        return 1

    distribution = Counter(record.get("decision", "REVIEW") for record in records)
    print(f"Decision distribution: {dict(distribution)}")
    if any(count < 2 for count in distribution.values()) or len(distribution) < 2:
        print(
            "Each decision class needs at least 2 reviewed examples to train and "
            "validate. Collect more human-reviewed outcomes first."
        )
        return 1

    import xgboost as xgb
    from sklearn.model_selection import train_test_split

    features, labels = build_dataset(records)
    if features.empty:
        print("No usable feature rows could be built from the stored records.")
        return 1
    y = [LABELS.index(label) for label in labels]
    x_train, x_test, y_train, y_test = train_test_split(
        features, y, test_size=0.2, random_state=42, stratify=y
    )
    model = xgb.XGBClassifier(
        n_estimators=240,
        max_depth=4,
        learning_rate=0.04,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="multi:softprob",
        num_class=len(LABELS),
        eval_metric="mlogloss",
    )
    model.fit(x_train, y_train)
    accuracy = model.score(x_test, y_test)
    print(f"Held-out accuracy: {accuracy:.3f} on {len(x_test)} records")
    print(
        "This model is advisory only: verification.py does not let it override "
        "the deterministic decision until it is validated on real held-out data."
    )
    path = cfg.fusion_model_file
    path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(path))
    print(f"Saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
