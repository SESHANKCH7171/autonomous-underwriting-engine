import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


class Settings(BaseSettings):
    # Server Environment
    ENVIRONMENT: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # Groq Low-Latency Inference
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_TEMPERATURE: float = 0.0
    GROQ_MAX_TOKENS: int = 400

    # Telemetry & Observability
    LOGFIRE_TOKEN: Optional[str] = None
    LOGFIRE_PROJECT_NAME: str = "autonomous-underwriting-engine"

    # LangSmith
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "autonomous-underwriting-engine"

    # Redis Cache
    REDIS_URL: str = "redis://localhost:6379/0"
    USE_REDIS: bool = False

    # Mesh API (System 1 Jev Evaluation via typesafe/jev-1.13)
    MESH_API_KEY: Optional[str] = None
    MESH_BASE_URL: str = "https://api.meshapi.ai/v1"
    JEV_MODEL: str = "typesafe/jev-1.13"

    # Latency Budget SLA (ms)
    MAX_SLA_LATENCY_MS: float = 180.0

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

if settings.LANGSMITH_TRACING:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    if settings.LANGSMITH_PROJECT:
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
