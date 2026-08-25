from functools import lru_cache
import numpy as np

@lru_cache
def model():
    from transformers import CLIPModel,CLIPProcessor
    import os
    name=os.getenv("VISION_EMBEDDING_MODEL","openai/clip-vit-base-patch32")
    return CLIPModel.from_pretrained(name),CLIPProcessor.from_pretrained(name)

def image_text_similarity(path:str,text:str):
    try:
        from PIL import Image
        m,p=model(); x=p(text=[text],images=Image.open(path).convert("RGB"),return_tensors="pt",padding=True)
        o=m(**x); a=o.image_embeds.detach().numpy(); b=o.text_embeds.detach().numpy(); a/=np.linalg.norm(a,axis=1,keepdims=True); b/=np.linalg.norm(b,axis=1,keepdims=True)
        return float((a@b.T)[0,0])
    except Exception: return None
