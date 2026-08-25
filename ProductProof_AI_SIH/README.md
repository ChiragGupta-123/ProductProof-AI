# ProductProof AI — Marketplace Image Correctiveness

SIH-ready full-stack prototype:

Next.js → FastAPI → OpenCV → OCR + Gemini Vision → CLIP → RAG/Chroma → LangChain (Gemini) verification → score → approve/review/reject → human review.

## Features
- Product listing + multiple image upload (drag & drop, previews)
- OpenCV preprocessing
- PaddleOCR adapter
- **Google Gemini** multimodal vision analysis (structured JSON output — no more flaky "unknown" results)
- CLIP image-text similarity adapter (runs locally, no API key needed)
- Chroma RAG over trusted product catalogs/specifications/policies, embedded with Gemini
- LangChain verification layer (Gemini) with structured output
- Deterministic safety checks so the LLM does not invent the final decision
- Correctness score (trust ring) and confidence
- Attribute mismatch evidence, collapsible evidence drawers
- Human review queue and audit records in SQLite
- Dockerfiles and docker-compose

## What changed in this version
- **Gemini instead of OpenAI** everywhere (vision analysis, reasoning, embeddings). Get a free key at https://aistudio.google.com/app/apikey.
- **Fixed the "UNKNOWN for every category" bug.** The old code compared the listing's `category` field against a `category` key that the vision model never actually returned (it returns `product_type`) — so category was hardcoded to UNKNOWN no matter what. It's now mapped correctly.
- **Structured output** (`response_schema`) is used for the Gemini calls, which removes the other common cause of "unknown": the model wrapping its answer in prose/markdown that failed to parse as JSON.
- Failures are now logged on the backend instead of being silently swallowed, and the frontend shows a banner if `GOOGLE_API_KEY` isn't set, instead of quietly returning a wall of unknowns.
- Verification scoring now actually uses the VLM's `same_product_likelihood` and `manipulation_concern` signals (previously computed but unused) and weighs confidence by image quality — should give more consistently correct decisions.
- Redesigned UI: case-file/verification-stamp visual language, drag-and-drop uploads with thumbnails, a circular trust-score gauge, a decision stamp, and collapsible evidence panels.

## Run locally

### Backend
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Put GOOGLE_API_KEY in .env (free key: https://aistudio.google.com/app/apikey)
uvicorn app.main:app --reload --port 8000
```

### Seed RAG (optional, adds the sample policy/catalog docs to Chroma)
```bash
cd backend
python scripts/seed_demo.py
```

### Frontend
```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```
Open http://localhost:3000

API docs: http://localhost:8000/docs

## Demo listing
Title: `ExampleTech X1 Smartphone - Black - 128GB`
Brand: `ExampleTech`
Category: `Smartphone`
Model: `X1`
Color: `Black`

Use a product image that is deliberately inconsistent (e.g. a different color device) to see a REVIEW/REJECT decision with mismatch evidence.

## Production notes
Use verified manufacturer data as authoritative RAG context. Calibrate scoring on a labeled dataset, version models/prompts, use object storage, authentication/RBAC, rate limits, async queues, and human review for uncertain cases. Rotate `GOOGLE_API_KEY` and never commit `.env`.
