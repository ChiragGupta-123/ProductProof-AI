import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.core.config import reset_settings_cache
from app.main import app

VERIFY_RESULT = {
    "decision": "REVIEW",
    "correctness_score": 61.5,
    "confidence": 0.72,
    "human_review_required": True,
    "attributes": [{
        "attribute": "brand", "expected": "Acme", "detected": None,
        "status": "UNKNOWN", "confidence": 0.45, "evidence": "",
    }],
    "mismatches": [],
    "product_evidence": [{"source": "example_product.md", "text": "Specs", "relevance": 0.8}],
    "policy_evidence": [{"source": "marketplace_policy.md", "text": "No fakes", "relevance": 0.7}],
    "similarities": [{"image_text": 0.2, "image_reference": None, "status": "computed"}],
    "explanation": "Deterministic explanation",
    "text_image_match_pct": 60.0,
    "image_quality_pct": 90.0,
    "quality_checks": [{"label": "Resolution", "passed": True, "detail": "800x800px"}],
    "ml_fusion": None,
    "authenticity": [{"phash": "abc", "duplicate": False, "matches": [], "status": "ok"}],
    "manipulation": [{"ela_score": 1.0, "concern": "low"}],
    "completeness": [{"status": "NOT_APPLICABLE", "claimed": [], "detected": [], "missing": []}],
    "llm_report": None,
}

VISION = {
    "product_type": "smartphone", "brand": None, "model": None, "color": None,
    "visible_text": [], "image_quality": "good", "same_product_likelihood": 0.6,
    "manipulation_concern": "low",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    reset_settings_cache()
    seen = {}

    def fake_verify(listing, paths, ocr, vision, metrics, session_id=None):
        seen.update({
            "listing": listing, "paths": list(paths), "ocr": ocr,
            "vision": vision, "metrics": metrics, "session_id": session_id,
        })
        return VERIFY_RESULT

    monkeypatch.setattr(routes, "is_decodable", lambda path: True)
    monkeypatch.setattr(routes, "preprocess_image", lambda path: path)
    monkeypatch.setattr(routes, "extract_text", lambda path: ["SAMPLE"])
    monkeypatch.setattr(routes, "analyze", lambda path, listing: dict(VISION))
    monkeypatch.setattr(
        routes, "image_metrics",
        lambda path: {"width": 800, "height": 800, "sharpness": 200.0, "fill_ratio": 0.5},
    )
    monkeypatch.setattr(routes, "verify", fake_verify)
    yield TestClient(app), seen, tmp_path / "uploads"
    reset_settings_cache()


def _files(count=2):
    return [
        ("images", (f"photo{i}.jpg", b"fake-image-bytes", "image/jpeg"))
        for i in range(count)
    ]


def test_verify_returns_report_and_cleans_temp_files(client):
    http, seen, upload_dir = client
    response = http.post(
        "/api/v1/verify",
        data={"title": "  Acme Phone  ", "brand": "Acme", "category": "Smartphone"},
        files=_files(2),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "REVIEW"
    assert body["review_id"] == "local-no-db"
    assert body["persisted"] is False
    assert body["listing"]["title"] == "Acme Phone"
    assert len(body["image_analysis"]) == 2
    assert body["review_id"]
    assert seen["session_id"] and len(seen["paths"]) == 2
    assert upload_dir.exists() is False or not any(upload_dir.iterdir())


def test_undecodable_upload_is_rejected_and_cleaned(client, monkeypatch):
    http, _, upload_dir = client
    monkeypatch.setattr(routes, "is_decodable", lambda path: False)
    response = http.post(
        "/api/v1/verify",
        data={"title": "Bad image"},
        files=[("images", ("bad.jpg", b"not-an-image", "image/jpeg"))],
    )
    assert response.status_code == 400
    assert "decode" in response.json()["detail"].lower()
    assert upload_dir.exists() is False or not any(upload_dir.iterdir())


def test_unsupported_image_type_is_rejected(client):
    http, _, _ = client
    response = http.post(
        "/api/v1/verify",
        data={"title": "Wrong type"},
        files=[("images", ("payload.gif", b"GIF89a", "image/gif"))],
    )
    assert response.status_code == 415


def test_oversized_image_is_rejected(client, monkeypatch):
    http, _, upload_dir = client
    monkeypatch.setenv("MAX_IMAGE_MB", "0")
    reset_settings_cache()
    response = http.post(
        "/api/v1/verify",
        data={"title": "Too big"},
        files=[("images", ("big.jpg", b"x" * 2048, "image/jpeg"))],
    )
    assert response.status_code == 413
    assert upload_dir.exists() is False or not any(upload_dir.iterdir())


def test_too_many_images_are_rejected(client):
    http, _, _ = client
    response = http.post(
        "/api/v1/verify",
        data={"title": "Too many"},
        files=_files(9),
    )
    assert response.status_code == 400
    assert "Maximum" in response.json()["detail"]


def test_blank_image_list_is_rejected(client):
    http, _, _ = client
    response = http.post("/api/v1/verify", data={"title": "No images"}, files=[])
    assert response.status_code == 422


def test_whitespace_title_is_rejected(client):
    http, _, _ = client
    response = http.post(
        "/api/v1/verify", data={"title": "   "}, files=_files(1)
    )
    assert response.status_code == 400


def test_review_history_requires_storage(client):
    http, _, _ = client
    response = http.get("/api/v1/reviews")
    assert response.status_code == 503
    assert "MONGODB_URI" in response.json()["detail"]


def test_human_review_validates_review_id(client):
    http, _, _ = client
    response = http.post(
        "/api/v1/reviews/not-an-object-id",
        json={"decision": "APPROVE", "reviewer_note": ""},
    )
    assert response.status_code == 400


def test_system_status_reports_placeholder_credentials_as_unconfigured(client):
    http, _, _ = client
    body = http.get("/api/v1/system-status").json()
    assert body["mongodb_configured"] is False
    assert body["gemini_configured"] is False
    assert body["groq_configured"] is False
    assert body["thresholds"]["approve"] == 80
    assert body["max_images"] == 8


def test_health_reports_degraded_without_storage(client):
    http, _, _ = client
    response = http.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
