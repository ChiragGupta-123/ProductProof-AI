"""Evidence fusion for marketplace image correctness.

Pipeline:
- attribute agreement across all images
- CLIP semantic similarity
- image-quality measurements
- Gemini visual likelihood/manipulation
- OCR
- pHash duplicate check + ELA signal
- YOLO completeness check
- MongoDB Atlas Vector Search RAG
- Groq/LangChain natural-language report
- XGBoost advisory fusion when a trained model exists
"""
from collections import Counter

from app.core.config import settings

from . import fusion
from .authenticity import check_duplicates, manipulation_heuristic
from .completeness import check as completeness_check
from .embeddings import image_text_similarity
from .langchain_verifier import llm_reasoning
from .rag import retrieve

QUALITY_WEIGHT = {"excellent": 1.0, "good": 0.9, "fair": 0.65, "poor": 0.35, "unknown": 0.5}
MANIPULATION_PENALTY = {"none": 0, "low": 3, "medium": 12, "high": 28, "unknown": 0}
ATTRIBUTE_FIELDS = ("brand", "model", "color", "category")


def norm(value):
    return str(value).strip().lower() if value is not None else None


def attr_match(expected, detected):
    expected, detected = norm(expected), norm(detected)
    if expected is None or detected is None:
        return None
    return expected == detected or expected in detected or detected in expected


def aggregate(field, vision):
    values = [item.get(field) for item in vision if item.get(field)]
    if not values:
        return None, False
    counts = Counter(norm(value) for value in values)
    top, count = counts.most_common(1)[0]
    original = next(value for value in values if norm(value) == top)
    return original, len(counts) > 1 and count < len(values)


def quality_checks(metrics, vision):
    checks = []
    sharpness = [m["sharpness"] for m in metrics if m.get("sharpness") is not None]
    if sharpness:
        average = sum(sharpness) / len(sharpness)
        checks.append({
            "label": "Blur / sharpness",
            "passed": average >= 60,
            "detail": (
                f"Laplacian variance {average:.0f} "
                f"({'sharp' if average >= 150 else 'soft' if average >= 60 else 'blurry'})"
            ),
        })
    resolutions = [(m["width"], m["height"]) for m in metrics if m.get("width") and m.get("height")]
    if resolutions:
        min_side = min(min(w, h) for w, h in resolutions)
        best = max(resolutions, key=lambda item: item[0] * item[1])
        checks.append({
            "label": "Resolution",
            "passed": min_side >= 600,
            "detail": f"{best[0]}x{best[1]}px (smallest side {min_side}px)",
        })
    fill = [m["fill_ratio"] for m in metrics if m.get("fill_ratio") is not None]
    if fill:
        average = sum(fill) / len(fill)
        checks.append({
            "label": "Product framing",
            "passed": 0.15 <= average <= 0.95,
            "detail": f"Estimated frame occupancy {average * 100:.0f}%",
        })
    # Only report a manipulation check when Gemini actually assessed it. With no
    # vision model every image is "unknown", and counting that as a passed check
    # inflated the score card while telling the reviewer nothing.
    concerns = [v.get("manipulation_concern", "unknown") for v in vision]
    known = [concern for concern in concerns if concern != "unknown"]
    if known:
        worst = max(known, key=lambda item: MANIPULATION_PENALTY.get(item, 0))
        checks.append({
            "label": "Visual manipulation concern",
            "passed": worst in {"none", "low"},
            "detail": f"Gemini concern: {worst}",
        })
    return checks


def _fallback_explanation(listing, text_pct, quality_pct, mismatches, product, policy,
                          vision, authenticity):
    """Deterministic explanation used when Groq is not configured or fails."""
    parts = []
    if text_pct is None:
        parts.append(
            "Text-to-image similarity was not computed locally, so the score relies on "
            "attribute agreement, image quality and duplicate signals."
        )
    else:
        parts.append(
            f"The submitted image set has an estimated text-image match of {text_pct}% "
            f"and measured image quality of {quality_pct}%."
        )
    if mismatches:
        parts.append(f"{len(mismatches)} attribute mismatch(es) were detected: "
                     + "; ".join(mismatches) + ".")
    elif vision and all(v.get("analysis_error") for v in vision):
        parts.append(
            "Visual attribute analysis was unavailable ("
            + str(vision[0].get("analysis_error"))
            + "), so attributes could not be independently confirmed."
        )
    else:
        parts.append("No confirmed attribute conflicts were found in the submitted images.")
    if any(item.get("duplicate") for item in authenticity):
        parts.append("A perceptual-hash match indicates these photos resemble an earlier upload.")
    parts.append(
        f"Trusted knowledge retrieval returned {len(product)} product and "
        f"{len(policy)} marketplace-policy evidence items."
    )
    return " ".join(parts)


def verify(listing, paths, ocr, vision, metrics=None, session_id=None):
    metrics = metrics or []
    cfg = settings()
    attrs: list[dict] = []
    mismatches: list[str] = []

    for field in ATTRIBUTE_FIELDS:
        key = "product_type" if field == "category" else field
        expected = listing.get(field)
        detected, disagree = aggregate(key, vision)
        matched = attr_match(expected, detected)
        if matched is None:
            status, confidence = "UNKNOWN", 0.45
        elif matched:
            status, confidence = "MATCH", 0.92
        else:
            status, confidence = "MISMATCH", 0.9
            mismatches.append(f"{field}: listing='{expected}', image_detected='{detected}'")
        if disagree:
            confidence *= 0.8
            mismatches.append(f"{field}: submitted images disagree with each other")
        attrs.append({
            "attribute": field,
            "expected": expected,
            "detected": detected,
            "status": status,
            "confidence": round(confidence, 2),
            "evidence": "Seller claim compared with independent visual analysis.",
        })

    ocr_all = [text for page in ocr for text in page]
    query = f"Listing={listing}\nVisual={vision}\nOCR={ocr_all}\nMismatch={mismatches}"
    evidence = retrieve(query, k=6)
    product = [item for item in evidence if "policy" not in item.get("source", "").lower()]
    policy = [item for item in evidence if "policy" in item.get("source", "").lower()]

    similarities = []
    for path in paths:
        score = image_text_similarity(
            path, listing["title"] + " " + (listing.get("description") or "")
        )
        similarities.append({
            "image_text": score,
            "image_reference": None,
            "status": "computed" if score is not None else "not_configured",
        })
    text_values = [item["image_text"] for item in similarities if item["image_text"] is not None]
    text_pct = (
        round(max(0, min(100, (sum(text_values) / len(text_values) + 1) * 50)), 1)
        if text_values else None
    )

    checks = quality_checks(metrics, vision)
    qualities = [v.get("image_quality", "unknown") for v in vision]
    quality_factor = (
        sum(QUALITY_WEIGHT.get(q, 0.5) for q in qualities) / len(qualities)
        if qualities else 0.5
    )
    quality_pct = round(quality_factor * 100, 1)
    likelihoods = [
        v.get("same_product_likelihood") for v in vision
        if isinstance(v.get("same_product_likelihood"), (int, float))
    ]
    likelihood = sum(likelihoods) / len(likelihoods) if likelihoods else None
    concerns = [v.get("manipulation_concern", "unknown") for v in vision]
    authenticity = [check_duplicates(path, session_id=session_id) for path in paths]
    manipulation = [manipulation_heuristic(path) for path in paths]
    completeness = [
        completeness_check(paths[i], listing.get("title", ""), listing.get("category"))
        for i in range(len(paths))
    ]

    # Transparent baseline score; XGBoost can learn the final fusion after real
    # labels accumulate. Guardrails below stop weak evidence becoming a hard call.
    score = 100.0 - 18 * len(mismatches)
    if text_pct is not None:
        score = 0.70 * score + 0.30 * text_pct
    if likelihood is not None:
        score += 10 * (likelihood - 0.5)
    score -= max([MANIPULATION_PENALTY.get(c, 0) for c in concerns] or [0])
    if any(item.get("duplicate") for item in authenticity):
        score -= 12
    if any(item.get("status") == "REVIEW" for item in completeness):
        score -= 5
    score = max(0, min(100, score))

    signal_strength = (
        0.2
        + (0.25 if evidence else 0)
        + (0.35 if any(v.get("brand") or v.get("model") or v.get("product_type") for v in vision) else 0.1)
        + (0.1 if ocr_all else 0)
        + 0.2 * quality_factor
    )
    confidence = min(0.98, signal_strength)
    if any(concern == "high" for concern in concerns):
        confidence = min(confidence, 0.68)

    if (
        score >= cfg.approve_threshold
        and confidence >= cfg.min_auto_confidence
        and not mismatches
    ):
        decision = "APPROVE"
    elif score < cfg.review_threshold and confidence >= cfg.min_auto_confidence:
        decision = "REJECT"
    else:
        decision = "REVIEW"

    report = llm_reasoning(
        listing, attrs, vision, product, policy, checks, text_pct, quality_pct,
        {"duplicates": authenticity, "manipulation": manipulation}, completeness,
    )
    if report and report.get("final_explanation"):
        explanation = report["final_explanation"]
    else:
        explanation = _fallback_explanation(
            listing, text_pct, quality_pct, mismatches, product, policy, vision, authenticity
        )

    ml = None
    if cfg.use_xgboost_fusion:
        features = fusion.extract_features(listing, attrs, vision, checks, similarities, ocr, metrics)
        features["image_quality_pct"] = quality_pct
        prediction = fusion.predict(features)
        if prediction:
            ml = {"features": features, **prediction}

    return {
        "decision": decision,
        "correctness_score": round(score, 2),
        "confidence": round(confidence, 2),
        "human_review_required": decision == "REVIEW",
        "attributes": attrs,
        "mismatches": mismatches,
        "product_evidence": product,
        "policy_evidence": policy,
        "similarities": similarities,
        "explanation": explanation,
        "text_image_match_pct": text_pct,
        "image_quality_pct": quality_pct,
        "quality_checks": checks,
        "ml_fusion": ml,
        "authenticity": authenticity,
        "manipulation": manipulation,
        "completeness": completeness,
        "llm_report": report,
    }
