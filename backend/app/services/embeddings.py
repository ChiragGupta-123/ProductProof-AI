import logging
import os
from functools import lru_cache

import numpy as np

log = logging.getLogger("productproof.embeddings")

_warned = False


@lru_cache
def model():
    # A first run downloads ~600 MB of weights. Bound the hub timeout so a
    # blocked network fails with a clear log line instead of hanging a request.
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "20")
    from transformers import CLIPModel, CLIPProcessor

    name = os.getenv("VISION_EMBEDDING_MODEL", "openai/clip-vit-base-patch32")
    log.info("Loading CLIP model %s (cached after first use)", name)
    return CLIPModel.from_pretrained(name), CLIPProcessor.from_pretrained(name)


def image_text_similarity(path: str, text: str):
    """Cosine similarity between an image and its listing text, or None.

    None means "not computed" (model unavailable, download blocked, corrupt
    image) and is reported as such — never as a zero similarity.
    """
    global _warned
    try:
        from PIL import Image
        import torch

        clip_model, processor = model()
        inputs = processor(
            text=[text[:1000] or "product"],
            images=Image.open(path).convert("RGB"),
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        with torch.no_grad():
            output = clip_model(**inputs)
        image_embeds = output.image_embeds.detach().numpy()
        text_embeds = output.text_embeds.detach().numpy()
        image_embeds /= np.linalg.norm(image_embeds, axis=1, keepdims=True)
        text_embeds /= np.linalg.norm(text_embeds, axis=1, keepdims=True)
        return float((image_embeds @ text_embeds.T)[0, 0])
    except Exception as exc:  # noqa: BLE001 - optional local model
        if not _warned:
            _warned = True
            log.warning("CLIP similarity unavailable (%s); continuing without it", exc)
        return None
