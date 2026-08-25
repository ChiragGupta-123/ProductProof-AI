import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.models.db import init_db

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("productproof")

os.makedirs("./data", exist_ok=True)
os.makedirs("./data/uploads", exist_ok=True)
os.makedirs("./data/chroma", exist_ok=True)
init_db()

if not os.getenv("GOOGLE_API_KEY"):
    logger.warning(
        "GOOGLE_API_KEY is not set. Vision analysis and LLM reasoning will be "
        "skipped and every attribute will come back UNKNOWN. Set GOOGLE_API_KEY "
        "in backend/.env (see backend/.env.example)."
    )

app = FastAPI(
    title="ProductProof AI",
    description="Marketplace image correctness verification",
    version="1.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")


@app.get("/api/v1/system-status")
def system_status():
    """Lets the frontend show a clear banner instead of a wall of UNKNOWNs
    when the backend isn't configured yet."""
    return {
        "gemini_configured": bool(os.getenv("GOOGLE_API_KEY")),
        "vlm_model": os.getenv("GEMINI_VLM_MODEL", "gemini-2.0-flash"),
    }
