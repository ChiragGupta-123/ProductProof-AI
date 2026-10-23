"""Vision-Language analysis of a single product image using Google Gemini.

Failures return a safe fallback object (with `analysis_error`) instead of
pretending the image simply had no attributes, and every failure is logged.
"""
import json
import logging
import mimetypes
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("productproof.vlm")

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "product_type": {"type": "STRING", "nullable": True},
        "brand": {"type": "STRING", "nullable": True},
        "model": {"type": "STRING", "nullable": True},
        "color": {"type": "STRING", "nullable": True},
        "visible_text": {"type": "ARRAY", "items": {"type": "STRING"}},
        "image_quality": {
            "type": "STRING",
            "enum": ["excellent", "good", "fair", "poor"],
        },
        "same_product_likelihood": {"type": "NUMBER"},
        "manipulation_concern": {
            "type": "STRING",
            "enum": ["none", "low", "medium", "high"],
        },
    },
    "required": [
        "product_type", "brand", "model", "color", "visible_text",
        "image_quality", "same_product_likelihood", "manipulation_concern",
    ],
}

_warned_missing_key = False


def _fallback(reason: str) -> dict:
    return {
        "product_type": None, "brand": None, "model": None, "color": None,
        "visible_text": [], "image_quality": "unknown",
        "same_product_likelihood": None, "manipulation_concern": "unknown",
        "analysis_error": reason,
    }


@lru_cache(maxsize=4)
def _model(model_name: str, api_key: str):
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def analyze(path: str, listing: dict) -> dict:
    global _warned_missing_key
    cfg = settings()
    if not cfg.google_api_key:
        if not _warned_missing_key:
            _warned_missing_key = True
            logger.warning("GOOGLE_API_KEY is not set - skipping VLM analysis")
        return _fallback("GOOGLE_API_KEY is not configured on the backend")

    try:
        model = _model(cfg.gemini_vlm_model, cfg.google_api_key)
        image_bytes = Path(path).read_bytes()
        mime_type = mimetypes.guess_type(path)[0] or "image/jpeg"
        prompt = (
            "You are a strict marketplace product-image verification analyst.\n"
            "Seller listing claims:\n" + json.dumps(listing, indent=2) + "\n\n"
            "Look ONLY at the attached image. Report what is visually supported by "
            "the pixels in front of you - do not guess or fill in gaps from the "
            "listing text. If an attribute is not visible or you are not confident, "
            "return null for it rather than copying the seller's claim.\n"
            "same_product_likelihood is a number from 0 to 1 estimating how likely "
            "this image shows the exact product described in the listing.\n"
            "manipulation_concern should reflect signs of digital editing, stock "
            "photos, watermark removal, or mismatched lighting/shadows."
        )
        response = model.generate_content(
            [prompt, {"mime_type": mime_type, "data": image_bytes}],
            generation_config={
                "temperature": 0,
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
            },
            request_options={"timeout": cfg.gemini_timeout_seconds},
        )
        data = json.loads(response.text)
        try:
            if data.get("same_product_likelihood") is not None:
                data["same_product_likelihood"] = max(
                    0.0, min(1.0, float(data["same_product_likelihood"]))
                )
        except (TypeError, ValueError):
            data["same_product_likelihood"] = None
        if not isinstance(data.get("visible_text"), list):
            data["visible_text"] = []
        return data
    except Exception as exc:  # noqa: BLE001 - one bad image must not fail the listing
        logger.exception("Gemini VLM analysis failed for %s: %s", path, exc)
        return _fallback(f"{type(exc).__name__}: {exc}")
