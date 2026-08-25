# SIH Architecture

1. React/Next.js receives listing data and up to 8 product images.
2. FastAPI orchestrates the pipeline.
3. OpenCV performs conservative resizing, denoising and contrast normalization.
4. PaddleOCR extracts visible product text.
5. A VLM extracts brand/model/color/type/quality and visual confidence.
6. CLIP/SigLIP calculates semantic image↔listing similarity.
7. Chroma retrieves authoritative manufacturer/catalog/policy evidence.
8. LangChain verifier reasons over the independent evidence and returns structured reasoning when configured.
9. Deterministic rules prevent an LLM from overriding hard contradictions or turning missing evidence into a rejection.
10. Score + confidence produce APPROVE, REVIEW or REJECT.
11. REVIEW cases are stored for human verification and audit.

## RAG sources
Manufacturer catalogs, official specification sheets, product manuals, verified reference metadata and marketplace policies. Seller claims should not be treated as authoritative knowledge.

## Why human review
Poor images, missing catalog data, ambiguous visual attributes and model disagreement should be REVIEW rather than forced rejection.
