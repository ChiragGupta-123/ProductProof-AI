# ProductProof AI — SIH Final Version

This version applies the changes shown in the supplied **"Differences from the PDF"** table and uses a current patched Next.js maintenance release.

## Implemented PDF changes

| PDF requirement | Final project |
|---|---|
| EasyOCR | EasyOCR is cached and preloaded once per backend process |
| Groq + Gemini | Gemini for vision/embeddings, Groq via LangChain for final reasoning/report |
| MongoDB primary DB/logging | MongoDB Atlas is the primary operational DB, audit store and review queue |
| MongoDB Atlas Vector Search | RAG vectors live in MongoDB Atlas; no Chroma dependency |
| React + Node + Express | Next.js/React UI + separate Node/Express API gateway + FastAPI ML service |
| XGBoost evidence fusion | XGBoost fusion module + training script; advisory until trained/validated on real labels |
| pHash + manipulation detection | pHash duplicate detection + ELA heuristic + Gemini manipulation concern |
| Completeness check | YOLO object detection + claimed-item mapping |
| Admin Panel | Dashboard, Review Queue, Archive, human override and analytics APIs |
| Seller/Vendor Portal | Separate `seller-portal/` React/Vite client |
| Mobile capture | Seller portal uses `capture="environment"` on image input and responsive UI |
| Voice support | Seller portal includes browser speech synthesis for report narration and browser Speech Recognition for voice-to-description input (subject to browser permissions/support) |

## AI output

The report now separates measured signals from interpretation:
- Text ↔ image similarity
- Image quality
- Visual product attributes
- OCR
- Duplicate/authenticity signals
- Object completeness
- Trusted product knowledge retrieved through RAG
- Marketplace policy evidence
- Groq/LangChain natural-language explanation
- Final recommendation

The model does not invent similarity percentages or quality numbers; CLIP/OpenCV provide the measured signals and Groq explains them.

## Local run

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
```

Set `GOOGLE_API_KEY`, `GROQ_API_KEY` and `MONGODB_URI` in `.env`.

All three are optional for a local demo. The app degrades explicitly instead of
faking results:

- Without `GOOGLE_API_KEY`, visual attributes are `UNKNOWN` and the decision falls
  back to `REVIEW` (CLIP/OpenCV signals still run).
- Without `GROQ_API_KEY`, reports use the deterministic explanation rather than the
  AI narrative.
- Without `MONGODB_URI`, verification still returns a report, but review history,
  the queue and manual overrides are disabled (`persisted: false`).

Placeholder values copied from `.env.example` (for example `<cluster>`) are treated
as unset, so the API fails fast instead of retrying an unreachable host.

Create the Atlas vector index:

```bash
python scripts/create_vector_index.py
```

Seed trusted knowledge:

```bash
python scripts/seed_demo.py
```

Start FastAPI:

```bash
uvicorn app.main:app --reload --port 8000
```

### 2. Express gateway

Open another terminal:

```bash
cd gateway
npm install
npm run dev
```

Gateway: `http://localhost:4000`

### 3. Admin web app

```bash
cd frontend
npm install
npm run dev
```

Admin UI: `http://localhost:3000`

### 4. Seller portal

```bash
cd seller-portal
npm install
npm run dev
```

Seller portal: `http://localhost:5173`

### 5. Tests

```bash
cd backend && pytest -q
cd gateway && npm test
cd frontend && npm run build
cd seller-portal && npm run build
```

The backend tests run offline (no Gemini/Groq/Mongo/CLIP calls). Gateway tests
start a fake upstream and assert multipart forwarding, input limits and origin
checks.

## Deployment with Docker Compose

The repo ships a production `docker-compose.yml`. Use a VM with Docker and at
least 4 GB of RAM (8 GB recommended): OCR, CLIP and YOLO load together on the
first request, and roughly 800 MB of model weights download on first boot.

```bash
git clone https://github.com/ChiragGupta-123/ProductProof-AI.git
cd ProductProof-AI
cp backend/.env.example backend/.env   # MONGODB_URI, GOOGLE_API_KEY, GROQ_API_KEY
cp .env.example .env                   # origins and hostnames - no secrets
docker compose up -d --build
```

What that starts:

- `backend` is published on `127.0.0.1:8000` **only**. The gateway is its sole
  caller, and the ML service has no authentication of its own.
- `gateway` (`:4000`), the admin app (`:3000`) and the seller portal (`:5173`)
  are public. The gateway is the browser's API origin, so it must be reachable.
- Model weights and uploads persist in the `backend_data` named volume.
- Every service has a health check and `restart: unless-stopped`.

For a real domain, set the URL variables in `.env` **before building** - the
frontends inline `NEXT_PUBLIC_API_URL` / `VITE_API_URL` into their bundles at
build time, so changing them later means rebuilding:

```bash
NEXT_PUBLIC_API_URL=https://api.example.com/api/v1
VITE_API_URL=https://api.example.com/api/v1
ALLOWED_ORIGINS=https://admin.example.com,https://seller.example.com
ADMIN_DOMAIN=admin.example.com
SELLER_DOMAIN=seller.example.com
API_DOMAIN=api.example.com
docker compose up -d --build
```

TLS is provided by the bundled Caddy service, which is opt-in:

```bash
docker compose --profile https up -d
```

Create the Atlas vector index and seed trusted knowledge once the backend is up:

```bash
docker compose exec backend python scripts/create_vector_index.py
docker compose exec backend python scripts/seed_demo.py
```

Useful checks after a deploy:

```bash
docker compose ps                     # every service should be healthy
curl -s http://localhost:4000/health  # gateway + backend together
curl -s http://localhost:8000/api/v1/system-status
```

The first verification after startup takes about 2 minutes while models load;
subsequent requests are roughly 8 seconds.

## MongoDB Atlas Vector Search index

The included `create_vector_index.py` creates a vectorSearch index over:

```json
{
  "embedding": {"type":"vector","numDimensions":768,"similarity":"cosine"}
}
```

Atlas vector search requires the collection's embedding field to be indexed with a vector search index before `$vectorSearch` retrieval is used. The script reads `EMBEDDING_DIMENSIONS` (default `768`, matching Gemini `text-embedding-004`); change it if you switch embedding models. Until the index exists, RAG falls back to local keyword retrieval over `backend/data/knowledge/`.

## XGBoost training

Do not treat a model trained on fabricated examples as an accuracy benchmark. Collect real human-reviewed outcomes through the admin queue first.

```bash
cd backend
python scripts/train_fusion_model.py
```

The module is advisory until a real held-out validation set shows it improves over the deterministic baseline.

## Deployment architecture

```text
Seller Portal / Admin UI
          ↓
   Node + Express Gateway
          ↓
     FastAPI ML service
          ↓
  ┌───────┼────────┬────────┐
  ↓       ↓        ↓        ↓
 Gemini  EasyOCR  CLIP     YOLO
  │        │       │        │
  └────────┴───────┴────────┘
             ↓
     MongoDB Atlas Vector RAG
             ↓
        Groq + LangChain
             ↓
       Structured AI Report
             ↓
  Approve / Review / Reject
             ↓
       MongoDB audit log
```

## Security

- Never commit `.env` files or API keys. `.dockerignore` files keep them out of images.
- Frontend is pinned to Next.js 15.5.24, a patched maintenance release from the current supported security line.
- The gateway only accepts browser origins listed in `ALLOWED_ORIGINS` and enforces per-image
  (10 MB) and per-request (8 images) upload limits before forwarding, using the patched
  multer 2.x line.
- Uploaded images are validated by decoding and are deleted after each request; only review
  metadata is persisted.
- Use HTTPS in deployment. `docker compose --profile https up -d` terminates TLS
  with the bundled Caddyfile; firewall ports 3000/4000/5173 when it is enabled
  so only 80/443 are reachable.
- The backend is bound to loopback in `docker-compose.yml`; only the gateway can
  reach it.
- **Authentication/RBAC is still not implemented.** Anyone who can reach the gateway can run
  verifications and override review decisions. Put the admin panel behind an authenticated
  proxy or add auth before exposing it publicly.
- Rotate secrets if they are ever exposed.
