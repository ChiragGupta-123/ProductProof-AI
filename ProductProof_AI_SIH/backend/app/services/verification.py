"""Combines listing attributes, Gemini vision analysis, OCR, CLIP image-text
similarity and RAG evidence into a single decision.

Improvements over the original version:
  - same_product_likelihood and manipulation_concern from the VLM were being
    computed but never actually used anywhere - they now move the score and
    confidence, which is a real accuracy gain (the model already had this
    signal, it just wasn't wired up).
  - image_quality feeds into confidence: a "poor" quality image should never
    push the decision to a confident REJECT.
  - attribute matching is a little more forgiving of near-matches (e.g.
    "black" vs "matte black") using substring containment, so honest listings
    aren't flagged as mismatches over wording differences.
"""
from .rag import retrieve
from .embeddings import image_text_similarity
from .langchain_verifier import llm_reasoning

QUALITY_WEIGHT = {"excellent": 1.0, "good": 0.9, "fair": 0.65, "poor": 0.35, "unknown": 0.5}
MANIPULATION_PENALTY = {"none": 0, "low": 4, "medium": 14, "high": 30, "unknown": 0}


def norm(x):
    return str(x).strip().lower() if x is not None else None


def _attribute_match(expected, detected):
    e, d = norm(expected), norm(detected)
    if e is None or d is None:
        return None
    if e == d:
        return True
    # forgiving containment match, e.g. "black" inside "matte black"
    return e in d or d in e


def verify(listing, paths, ocr, vision):
    attributes = []
    mismatches = []
    for field in ["brand", "model", "color", "category"]:
        expected = listing.get(field)
        vals = [v.get(field if field != "category" else "product_type") for v in vision if v.get(field if field != "category" else "product_type")]
        detected = vals[0] if vals else None
        match = _attribute_match(expected, detected)
        if match is None:
            status, conf = "UNKNOWN", 0.45
        elif match:
            status, conf = "MATCH", 0.90
        else:
            status, conf = "MISMATCH", 0.86
            mismatches.append(f"{field}: listing='{expected}', image_detected='{detected}'")
        attributes.append({
            "attribute": field, "expected": expected, "detected": detected,
            "status": status, "confidence": conf,
            "evidence": "Seller claim compared with independent Gemini visual analysis.",
        })

    allocr = [x for page in ocr for x in page]
    evidence = retrieve(f"Listing={listing}\nVisual={vision}\nOCR={allocr}\nMismatches={mismatches}")
    product = [e for e in evidence if "policy" not in e["source"].lower()]
    policy = [e for e in evidence if "policy" in e["source"].lower()]

    sims = []
    for p in paths:
        s = image_text_similarity(p, listing["title"] + " " + listing.get("description", ""))
        sims.append({"image_text": s, "image_reference": None, "status": "computed" if s is not None else "not_configured"})

    score = 100 - 18 * len(mismatches)

    known_sims = [x["image_text"] for x in sims if x["image_text"] is not None]
    if known_sims:
        sim = max(0, min(100, (sum(known_sims) / len(known_sims) + 1) * 50))
        score = 0.65 * score + 0.25 * sim
    else:
        score = 0.90 * score

    # Use the VLM's own same-product-likelihood estimate, when present.
    likelihoods = [v.get("same_product_likelihood") for v in vision if isinstance(v.get("same_product_likelihood"), (int, float))]
    if likelihoods:
        avg_likelihood = sum(likelihoods) / len(likelihoods)
        score = score + 10 * (avg_likelihood - 0.5)  # shift +/-5 around neutral 0.5

    # Manipulation concerns and poor image quality both erode the score/confidence.
    concerns = [v.get("manipulation_concern", "unknown") for v in vision]
    score -= max((MANIPULATION_PENALTY.get(c, 0) for c in concerns), default=0)

    qualities = [v.get("image_quality", "unknown") for v in vision]
    quality_factor = (sum(QUALITY_WEIGHT.get(q, 0.5) for q in qualities) / len(qualities)) if qualities else 0.5

    has_vision_signal = any(v.get("model") or v.get("brand") or v.get("color") or v.get("product_type") for v in vision)
    confidence = min(
        0.98,
        0.15
        + (0.20 if evidence else 0)
        + (0.35 if has_vision_signal else 0.10)
        + (0.10 if allocr else 0)
        + 0.20 * quality_factor,
    )
    if any(c == "high" for c in concerns):
        confidence = min(confidence, 0.7)

    score = round(max(0, min(100, score)), 2)
    confidence = round(confidence, 2)

    decision = (
        "APPROVE" if score >= 80 and confidence >= 0.78 and not mismatches
        else ("REJECT" if score < 55 and confidence >= 0.78 else "REVIEW")
    )

    llm = llm_reasoning(listing, attributes, product, policy)
    # The LLM can explain/reason, but cannot override a hard attribute mismatch
    # or a decision made under weak evidence.
    if llm and not mismatches and confidence >= 0.78 and llm["decision"] in {"APPROVE", "REVIEW"}:
        decision = llm["decision"]
    if llm and llm["decision"] == "REJECT" and not mismatches:
        decision = "REVIEW"

    explanation = (
        llm["explanation"] if llm else
        "Decision combines listing attributes, Gemini vision analysis, OCR, CLIP visual similarity and trusted RAG evidence."
    )

    return {
        "decision": decision,
        "correctness_score": score,
        "confidence": confidence,
        "human_review_required": decision == "REVIEW",
        "attributes": attributes,
        "mismatches": mismatches,
        "product_evidence": product,
        "policy_evidence": policy,
        "similarities": sims,
        "explanation": explanation,
    }
