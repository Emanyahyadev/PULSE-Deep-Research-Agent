"""Application settings and the hard bounds that keep autonomy inside limits.

Autonomy without bounds = runaway cost; bounds without autonomy = a fixed script.
Every cap here is enforced by the orchestrator, not by the LLM.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the project root (research-agent/.env), regardless of the
# directory uvicorn is launched from. Real environment variables still win.
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    # --- Credentials ---
    openai_api_key: str
    tavily_api_key: str = ""
    exa_api_key: str = ""

    # --- Search provider: "tavily" | "exa" ---
    search_provider: str = "tavily"

    # --- OpenAI-compatible endpoints (NVIDIA NIM by default) ---
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    embeddings_base_url: str = "https://integrate.api.nvidia.com/v1"

    # --- Postgres (port must match docker-compose.yml: 5434) ---
    database_url: str = "postgresql+psycopg://research:research@localhost:5434/research"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "research_chunks"

    # --- Models ---
    planner_model: str = "meta/llama-3.3-70b-instruct"
    writer_model: str = "meta/llama-3.3-70b-instruct"
    embedding_model: str = "nvidia/nv-embedqa-e5-v5"
    embedding_dim: int = 1024

    # --- Bounds: autonomy lives inside these caps ---
    max_queries: int = 5
    max_sources: int = 10
    max_rounds: int = 2
    max_total_seconds: float = 240.0
    top_k: int = 12

    # --- Per-stage LLM timeouts (a hung LLM call must fail fast into the
    # deterministic fallbacks, not eat the whole wall-clock budget) ---
    planner_timeout: float = 45.0
    writer_timeout: float = 120.0

    # --- Chunking ---
    chunk_size: int = 800
    chunk_overlap: int = 120

    # --- Search ---
    tavily_results_per_query: int = 5
    exa_results_per_query: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
