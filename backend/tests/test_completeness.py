from app.services import completeness


def test_no_object_claim_skips_the_detector(monkeypatch):
    called = {"value": False}

    def fake_detect(_path):
        called["value"] = True
        return []

    monkeypatch.setattr(completeness, "detect", fake_detect)
    result = completeness.check("image.jpg", "Vintage leather satchel", "")
    assert result["status"] == "NOT_APPLICABLE"
    assert called["value"] is False


def test_claimed_object_missing_is_review(monkeypatch):
    monkeypatch.setattr(
        completeness, "detect",
        lambda _path: [{"label": "backpack", "confidence": 0.9}],
    )
    result = completeness.check("image.jpg", "Leather backpack and laptop", "")
    assert result["status"] == "REVIEW"
    assert "laptop" in result["missing"]


def test_claimed_object_present_passes(monkeypatch):
    monkeypatch.setattr(
        completeness, "detect",
        lambda _path: [{"label": "laptop", "confidence": 0.8}],
    )
    result = completeness.check("image.jpg", "Laptop", "")
    assert result["status"] == "PASS"


def test_detector_unavailable_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(completeness, "detect", lambda _path: None)
    result = completeness.check("image.jpg", "Laptop", "")
    assert result["status"] == "NOT_AVAILABLE"
    assert result["missing"] == []
