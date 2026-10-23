"""Single source of truth for backend configuration.

Two things this module fixes:

1. `.env` is resolved relative to the backend directory, not the process
   working directory. Previously `Settings(env_file=".env")` silently did
   nothing when uvicorn or a script was started from the repository root.
2. Placeholder values copied from `.env.example` (``<user>``, ``mongodb+srv://
   <cluster>``, empty strings) are treated as "not configured". Otherwise the
   app repeatedly attempts to reach a literal host named ``<cluster>``.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]

_PLACEHOLDER_TOKENS = ("<", ">", "your_", "changeme", "replace_me", "example.com")


def clean_credential(value) -> str:
    """Return a usable credential or '' when the value is a template placeholder."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    lowered = text.lower()
    if any(token in lowered for token in _PLACEHOLDER_TOKENS):
        return ""
    return text


class Settings(BaseSettings):
    app_name: str = "ProductProof AI"
    api_prefix: str = "/api/v1"
    mongodb_uri: str = ""
    mongodb_db: str = "productproof"
    mongodb_rag_collection: str = "knowledge_chunks"
    mongodb_image_collection: str = "image_signatures"
    mongodb_audit_collection: str = "verification_records"
    mongodb_vector_index: str = "knowledge_vector_index"
    google_api_key: str = ""
    groq_api_key: str = ""
    gemini_vlm_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "models/text-embedding-004"
    groq_reasoning_model: str = "llama-3.3-70b-versatile"
    vision_embedding_model: str = "openai/clip-vit-base-patch32"
    ultralytics_model: str = "yolo11n.pt"
    ocr_languages: str = "en"
    ocr_use_gpu: bool = False
    ocr_max_dim: int = 1000
    max_images: int = 8
    max_image_mb: int = 10
    approve_threshold: float = 80
    review_threshold: float = 55
    min_auto_confidence: float = 0.78
    use_xgboost_fusion: bool = True
    fusion_model_path: str = "./data/models/fusion_model.json"
    min_training_samples: int = 100
    upload_dir: str = "./data/uploads"
    groq_timeout_seconds: int = 60
    gemini_timeout_seconds: int = 45

    @field_validator("mongodb_uri", "google_api_key", "groq_api_key", mode="before")
    @classmethod
    def _blank_placeholders(cls, value):
        return clean_credential(value)

    @property
    def knowledge_dir(self) -> Path:
        return BACKEND_DIR / "data" / "knowledge"

    def resolve_path(self, value: str) -> Path:
        """Resolve a configured filesystem path against the backend root.

        Absolute paths are kept as-is; relative ones are anchored to the
        backend directory so scripts and uvicorn behave the same regardless
        of the current working directory.
        """
        path = Path(value).expanduser()
        return path if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def upload_path(self) -> Path:
        return self.resolve_path(self.upload_dir)

    @property
    def fusion_model_file(self) -> Path:
        return self.resolve_path(self.fusion_model_path)

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests after changing environment variables."""
    settings.cache_clear()
