"""
Central application configuration.

All external-service toggles live here. DEMO_MODE is the single switch that
lets the whole system (agent, MCP tool clients, RAG providers) run with
deterministic mock data when no real API keys are configured — required by
the "must run locally without credentials" constraint.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "PathForge AI API"
    ENVIRONMENT: Literal["local", "test", "staging", "production"] = "local"
    API_V1_PREFIX: str = "/api"
    DEBUG: bool = True

    # --- Demo mode ---
    # When true, MCP tool clients and LLM/RAG providers fall back to
    # deterministic mock providers instead of calling real external APIs.
    DEMO_MODE: bool = True

    # --- Security (Phase 12) ---
    SECRET_KEY: str = Field(default="change-me-in-env", repr=False)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    # Authentication is on by default. False is a local/test-only "trusted caller" mode in which a caller-supplied
    # user_id is believed (the pre-Phase-12 behaviour); staging/production refuse to start with it off.
    AUTH_REQUIRED: bool = True
    ALLOW_REGISTRATION: bool = True
    # Emails (case-insensitive) allowed to ingest into the shared RAG knowledge base.
    ADMIN_EMAILS: list[str] = []
    # Requests declaring a larger Content-Length are refused with 413 before the body is read (resume max is 5 MB).
    MAX_REQUEST_BODY_BYTES: int = 6_000_000
    PASSWORD_MIN_LENGTH: int = 10
    PASSWORD_MAX_LENGTH: int = 128
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_WINDOW_SECONDS: int = 900

    # --- Observability (Phase 12) ---
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["text", "json"] = "text"
    METRICS_ENABLED: bool = True
    # When set, GET /metrics requires "Authorization: Bearer <METRICS_TOKEN>"; production keeps it off without one.
    METRICS_TOKEN: str | None = Field(default=None, repr=False)

    # --- Database ---
    # Defaults to a local SQLite file so `uvicorn app.main:app` works with
    # zero external setup. docker-compose overrides this to Postgres.
    DATABASE_URL: str = "sqlite:///./pathforge.db"

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # --- LLM provider (used starting Phase 4) ---
    LLM_PROVIDER: Literal["anthropic", "openai", "mock"] = "mock"
    LLM_API_KEY: str | None = Field(default=None, repr=False)
    LLM_MODEL: str = "claude-sonnet-4-5"

    # --- Agent execution bounds (Phase 4) ---
    AGENT_MAX_TOOL_CALLS: int = 5
    AGENT_TOOL_TIMEOUT_SECONDS: float = 20.0

    # --- Embedding provider (Phase 5) ---
    EMBEDDING_PROVIDER: Literal["openai", "mock"] = "mock"
    EMBEDDING_API_KEY: str | None = Field(default=None, repr=False)
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    # Shared by demo and real providers so vector store schema stays
    # consistent regardless of which is active (OpenAI's text-embedding-3
    # models support a `dimensions` param to request exactly this size).
    EMBEDDING_DIMENSION: int = 384

    # --- Vector store (Phase 5) ---
    # None (default) -> Qdrant's embedded local-mode client, on-disk at
    # QDRANT_LOCAL_PATH, no server required. Set QDRANT_URL to point at a
    # real Qdrant server (e.g. the docker-compose service) instead.
    QDRANT_URL: str | None = None
    QDRANT_API_KEY: str | None = Field(default=None, repr=False)
    QDRANT_LOCAL_PATH: str = "./qdrant_data"
    QDRANT_COLLECTION_NAME: str = "pathforge_documents"

    # --- RAG pipeline bounds (Phase 5) ---
    RAG_CHUNK_SIZE_CHARS: int = 1200
    RAG_CHUNK_OVERLAP_CHARS: int = 200
    RAG_MIN_CHUNK_SIZE_CHARS: int = 100
    RAG_MAX_DOCUMENT_CHARS: int = 200_000
    RAG_MAX_CHUNKS_PER_DOCUMENT: int = 500
    RAG_MAX_TOP_K: int = 20
    RAG_DEFAULT_TOP_K: int = 5
    RAG_MAX_CONTEXT_CHARS: int = 8000

    # --- Resume analyzer bounds (Phase 6) ---
    RESUME_MAX_UPLOAD_BYTES: int = 5_000_000  # 5MB
    RESUME_MAX_TEXT_CHARS: int = 50_000
    RESUME_MAX_SECTIONS: int = 30
    RESUME_MAX_SKILLS: int = 100
    RESUME_MAX_EXPERIENCES: int = 30
    RESUME_MAX_PROJECTS: int = 30

    # --- Job description analyzer bounds (Phase 7) ---
    JD_MAX_UPLOAD_BYTES: int = 2_000_000
    JD_MAX_TEXT_CHARS: int = 30_000
    JD_MAX_SECTIONS: int = 30
    JD_MAX_SKILLS: int = 100

    # --- Roadmap generation (Phase 8) ---
    ROADMAP_STUDY_DAYS_PER_WEEK: int = 5

    # --- Assessments + mentor (Phase 12) ---
    ASSESSMENT_MAX_ANSWER_CHARS: int = 5_000
    ASSESSMENT_MAX_CODE_CHARS: int = 10_000
    MENTOR_MAX_MESSAGE_CHARS: int = 2_000
    MENTOR_RAG_TOP_K: int = 3
    # Retrieved chunks scoring below this are treated as "no relevant source found" (no citation, no
    # grounded explanation). Cosine score from the vector store.
    MENTOR_RAG_MIN_SCORE: float = 0.15

    # --- MCP servers (populated in Phase 3) ---
    MCP_GITHUB_SERVER_URL: str | None = None
    MCP_SEARCH_SERVER_URL: str | None = None
    MCP_LEARNING_SERVER_URL: str | None = None
    # Vector DB config lives in the "Vector store (Phase 5)" block above —
    # pgvector was considered but dropped per Phase 5's explicit
    # requirement to keep vectors out of PostgreSQL entirely; Qdrant only.


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — import and call this, never instantiate
    Settings() directly, so the whole app shares one parsed config."""
    return Settings()
