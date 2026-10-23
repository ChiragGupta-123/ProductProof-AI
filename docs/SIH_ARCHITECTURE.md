# ProductProof AI — SIH Architecture

The supplied PDF-difference table is implemented as follows:

1. **Seller/Vendor Portal:** a separate React/Vite client with camera capture and report narration.
2. **Admin Panel:** the main React/Next dashboard with analytics, review queue, archive and decision override.
3. **Node/Express:** public API gateway, multipart forwarding and one consistent API origin for browser clients.
4. **FastAPI:** ML orchestration service.
5. **EasyOCR:** text extraction, loaded once and reused.
6. **Gemini:** multimodal visual analysis and trusted-source embeddings.
7. **CLIP:** image↔listing semantic similarity.
8. **YOLO:** object detection for completeness checks.
9. **pHash + ELA:** duplicate and manipulation-risk signals.
10. **MongoDB Atlas:** operational DB, audit logs, image signatures and vector knowledge store.
11. **MongoDB Vector Search:** trusted RAG retrieval via `$vectorSearch`.
12. **LangChain + Groq:** final product analyst report.
13. **XGBoost:** evidence fusion layer, trained only from real human-reviewed labels.
14. **Decision layer:** conservative deterministic guardrails prevent weak evidence from becoming a hard rejection.

## Why this is faster

- OCR model is cached/preloaded.
- CLIP is cached.
- Multiple images are processed in parallel.
- Gemini is used for vision while Groq handles the final text synthesis.
- The browser talks to one Express origin, simplifying deployment and reducing CORS churn.
- RAG is a direct indexed vector lookup instead of rebuilding a local vector store for every request.

## Why this is more accurate

- Independent signals are retained instead of letting the LLM invent scores.
- Attribute comparison uses all submitted images, not only image 1.
- Image quality comes from measured OpenCV metrics.
- Duplicates are checked with perceptual hashing.
- Completeness is backed by object detection.
- Manufacturer/policy knowledge comes through trusted RAG.
- Human decisions become future labels for XGBoost.
