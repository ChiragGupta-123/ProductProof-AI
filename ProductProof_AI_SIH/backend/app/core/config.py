from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Google Gemini is used for all LLM/VLM calls in this project.
    # Get a free key at https://aistudio.google.com/app/apikey
    google_api_key: str = ""
    gemini_vlm_model: str = "gemini-2.0-flash"
    gemini_verifier_model: str = "gemini-2.0-flash"
    gemini_embedding_model: str = "models/text-embedding-004"
    # Local, no API key required - used only for image<->text similarity scoring.
    vision_embedding_model: str = "openai/clip-vit-base-patch32"
    database_url: str = "sqlite:///./data/productproof.db"
    chroma_dir: str = "./data/chroma"
    upload_dir: str = "./data/uploads"
    approve_threshold: float = 80
    review_threshold: float = 55
    min_auto_confidence: float = .78
    frontend_origin: str = "http://localhost:3000"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def settings():
    return Settings()
