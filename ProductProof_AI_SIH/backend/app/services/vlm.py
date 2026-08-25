"""Vision-Language analysis of a single product image using Google Gemini.

This used to silently return "unknown" for every field whenever anything
went wrong (missing key, network error, the model wrapping its JSON in
markdown fences, etc). That made real failures invisible. This version:
  1. Uses Gemini's native structured-output mode (response_schema) so the
     model is constrained to return valid JSON in the exact shape we need
     - this alone removes most of the old "unknown" results, which were
       usually caused by JSON parsing failing on a chatty response.
  2. Fails loudly to the server logs (but still returns a safe fallback
     object to the caller) so real problems are visible instead of being
     silently swallowed.
"""
import json
import logging
import os
from pathlib import Path

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


def _fallback(reason: str) -> dict:
    return {
        "product_type": None, "brand": None, "model": None, "color": None,
        "visible_text": [], "image_quality": "unknown",
        "same_product_likelihood": None, "manipulation_concern": "unknown",
        "analysis_error": reason,
    }


def analyze(path: str, listing: dict) -> dict:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("GOOGLE_API_KEY is not set - skipping VLM analysis for %s", path)
        return _fallback("GOOGLE_API_KEY is not configured on the backend")

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_VLM_MODEL", "gemini-2.0-flash")
        model = genai.GenerativeModel(model_name)

        image_bytes = Path(path).read_bytes()
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
            [prompt, {"mime_type": "image/jpeg", "data": image_bytes}],
            generation_config={
                "temperature": 0,
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
            },
        )

        data = json.loads(response.text)
        # Defensive normalisation in case the model returns a string for the score.
        try:
            if data.get("same_product_likelihood") is not None:
                data["same_product_likelihood"] = float(data["same_product_likelihood"])
        except (TypeError, ValueError):
            data["same_product_likelihood"] = None
        if not isinstance(data.get("visible_text"), list):
            data["visible_text"] = []
        return data

    except Exception as exc:  # noqa: BLE001 - we want to catch and log everything here
        logger.exception("Gemini VLM analysis failed for %s: %s", path, exc)
        return _fallback(f"{type(exc).__name__}: {exc}")
