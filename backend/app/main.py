import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env *before* importing anything that snapshots environment variables at
# import time (OCR languages, ULTRALYTICS_MODEL, thresholds). Previously this
# ran after the service imports, so those values were ignored.
BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.api.routes import router  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.db import init_db  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("productproof")


def _cors_origins() -> list[str]:
    origins: list[str] = []
    for key, fallback in (
        ("FRONTEND_ORIGIN", "http://localhost:3000"),
        ("EXPRESS_ORIGIN", "http://localhost:4000"),
        ("SELLER_ORIGIN", "http://localhost:5173"),
    ):
        raw = os.getenv(key, fallback)
        for item in raw.split(","):
            origin = item.strip().rstrip("/")
            if origin and origin not in origins:
                origins.append(origin)
    return origins


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        init_db()
        log.info("MongoDB connected")
    except Exception as exc:  # noqa: BLE001 - the API must boot without storage
        log.warning("MongoDB unavailable at startup: %s", exc)
    yield


cfg = settings()
app = FastAPI(
    title=cfg.app_name,
    description="Marketplace image correctness verification",
    version="2.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=cfg.api_prefix)


@app.get("/")
def root():
    return {"service": cfg.app_name, "version": "2.1.0", "docs": "/docs"}
