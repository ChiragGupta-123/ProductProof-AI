import pytest

from app.core.config import reset_settings_cache
from app.services import verification


def base_listing(**overrides):
    listing = {
        "title": "ExampleTech X1 Black",
        "description": "Flagship smartphone",
        "brand": "ExampleTech",
        "category": "Smartphone",
        "color": "Black",
        "model": "X1",
    }
    listing.update(overrides)
    return listing


def base_vision(**overrides):
    vision = {
        "product_type": "smartphone",
        "brand": "ExampleTech",
        "model": "X1",
        "color": "Black",
        "visible_text": [],
        "image_quality": "excellent",
        "same_product_likelihood": 0.95,
        "manipulation_concern": "none",
    }
    vision.update(overrides)
    return vision


@pytest.fixture(autouse=True)
def offline_pipeline(monkeypatch):
    """Keep tests offline: no CLIP, Gemini, Groq, Mongo or YOLO."""
    monkeypatch.setattr(verification, "retrieve", lambda query, k=6: [])
    monkeypatch.setattr(verification, "image_text_similarity", lambda path, text: None)
    monkeypatch.setattr(verification, "llm_reasoning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        verification, "check_duplicates",
        lambda path, session_id=None: {
            "phash": "0" * 16, "duplicate": False, "matches": [], "status": "ok",
        },
    )
    monkeypatch.setattr(
        verification, "manipulation_heuristic",
        lambda path: {"ela_score": 1.0, "concern": "low"},
    )
    monkeypatch.setattr(
        verification, "completeness_check",
        lambda path, title, category: {
            "status": "NOT_APPLICABLE", "claimed": [], "detected": [], "missing": [],
        },
    )
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_color_mismatch_is_flagged_and_not_approved():
    vision = [base_vision(color="Blue")]
    result = verification.verify(base_listing(), ["image.jpg"], [[]], vision, [])
    color = next(item for item in result["attributes"] if item["attribute"] == "color")
    assert color["status"] == "MISMATCH"
    assert result["decision"] in {"REVIEW", "REJECT"}
    assert any("color" in mismatch.lower() for mismatch in result["mismatches"])


def test_consistent_listing_with_evidence_is_approved(monkeypatch):
    monkeypatch.setattr(
        verification, "retrieve",
        lambda query, k=6: [{"source": "example_product.md", "text": "Specs", "relevance": 0.9}],
    )
    result = verification.verify(
        base_listing(), ["image.jpg"], [["ExampleTech"]], [base_vision()], []
    )
    assert result["decision"] == "APPROVE"
    assert result["correctness_score"] >= 80
    assert result["confidence"] >= 0.78
    assert result["product_evidence"]


def test_multiple_mismatches_reject_with_high_confidence(monkeypatch):
    monkeypatch.setattr(
        verification, "retrieve",
        lambda query, k=6: [{"source": "product.md", "text": "Specs", "relevance": 0.9}],
    )
    vision = [base_vision(brand="OtherBrand", model="Z9", color="Red")]
    result = verification.verify(base_listing(), ["image.jpg"], [[]], vision, [])
    assert result["decision"] == "REJECT"
    assert result["correctness_score"] < 55


def test_vision_unavailable_falls_back_to_review():
    vision = [{
        "product_type": None, "brand": None, "model": None, "color": None,
        "visible_text": [], "image_quality": "unknown",
        "same_product_likelihood": None, "manipulation_concern": "unknown",
        "analysis_error": "GOOGLE_API_KEY is not configured on the backend",
    }]
    result = verification.verify(base_listing(), ["image.jpg"], [[]], vision, [])
    assert result["decision"] == "REVIEW"
    assert result["human_review_required"] is True
    assert all(attribute["status"] == "UNKNOWN" for attribute in result["attributes"])
    assert "not configured" in result["explanation"].lower()


def test_review_requirement_is_enforced_by_confidence(monkeypatch):
    monkeypatch.setenv("MIN_AUTO_CONFIDENCE", "0.99")
    reset_settings_cache()
    monkeypatch.setattr(
        verification, "retrieve",
        lambda query, k=6: [{"source": "product.md", "text": "Specs", "relevance": 0.9}],
    )
    result = verification.verify(
        base_listing(), ["image.jpg"], [[]], [base_vision()], []
    )
    assert result["decision"] == "REVIEW"
    assert result["human_review_required"] is True


def test_duplicate_signal_reduces_score(monkeypatch):
    # Keep the score away from the 100 clamp so the 12-point penalty is visible.
    monkeypatch.setattr(verification, "image_text_similarity", lambda path, text: 0.1)
    baseline = verification.verify(
        base_listing(), ["image.jpg"], [[]], [base_vision()], []
    )
    monkeypatch.setattr(
        verification, "check_duplicates",
        lambda path, session_id=None: {
            "phash": "0" * 16, "duplicate": True,
            "matches": [{"review_id": "old", "hamming_distance": 2}], "status": "ok",
        },
    )
    flagged = verification.verify(
        base_listing(), ["image.jpg"], [[]], [base_vision()], []
    )
    assert flagged["authenticity"][0]["duplicate"] is True
    assert baseline["correctness_score"] < 100
    assert flagged["correctness_score"] == pytest.approx(
        baseline["correctness_score"] - 12, abs=0.01
    )


def test_quality_checks_use_measured_metrics():
    checks = verification.quality_checks(
        [{"width": 300, "height": 200, "sharpness": 20.0, "fill_ratio": 0.4}],
        [base_vision()],
    )
    by_label = {item["label"]: item for item in checks}
    assert by_label["Blur / sharpness"]["passed"] is False
    assert by_label["Resolution"]["passed"] is False
    assert by_label["Product framing"]["passed"] is True


def test_attribute_matching_is_normalized():
    assert verification.attr_match("Black", " black ") is True
    assert verification.attr_match("Nike", "Nike Air") is True
    assert verification.attr_match(None, "Nike") is None
    assert verification.attr_match("Black", "Blue") is False
