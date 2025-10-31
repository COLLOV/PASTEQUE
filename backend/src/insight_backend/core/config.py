from functools import lru_cache
from typing import List
import logging

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    env: str = Field("development", alias="ENV")
    api_prefix: str = Field("/api", alias="API_PREFIX")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    allowed_origins_raw: str | None = Field(None, alias="ALLOWED_ORIGINS")

    data_root: str = Field("../data", alias="DATA_ROOT")
    vector_store_path: str = Field("../data/vector_store", alias="VECTOR_STORE_PATH")
    tables_dir: str = Field("../data", alias="DATA_TABLES_DIR")
    # Default path fixed: 'dictionary' (not 'dictionnary')
    data_dictionary_dir: str = Field("../data/dictionary", alias="DATA_DICTIONARY_DIR")
    # Cap for injected data dictionary JSON in prompts
    data_dictionary_max_chars: int = Field(6000, alias="DATA_DICTIONARY_MAX_CHARS")

    # LLM configuration
    llm_mode: str = Field("local", alias="LLM_MODE")  # "local" | "api"
    # OpenAI-compatible (API provider Z or others)
    openai_base_url: str | None = Field(None, alias="OPENAI_BASE_URL")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    llm_model: str | None = Field(None, alias="LLM_MODEL")
    openai_timeout_s: int = Field(90, alias="OPENAI_TIMEOUT_S")
    # vLLM local
    vllm_base_url: str | None = Field("http://localhost:8000/v1", alias="VLLM_BASE_URL")
    z_local_model: str | None = Field("GLM-4.5-Air", alias="Z_LOCAL_MODEL")

    # Router gate (applied on every user message)
    router_mode: str = Field("rule", alias="ROUTER_MODE")  # "rule" | "local" | "api" | "false"
    router_model: str | None = Field(None, alias="ROUTER_MODEL")

    @field_validator("router_mode", mode="before")
    @classmethod
    def _validate_router_mode(cls, v: str | None) -> str:
        val = (v or "rule").strip().lower()
        valid = {"rule", "local", "api", "false"}
        if val not in valid:
            raise ValueError(f"ROUTER_MODE must be one of {sorted(valid)}; got: {v!r}")
        return val

    # MCP configuration (declarative)
    mcp_config_path: str | None = Field("../plan/Z/mcp.config.json", alias="MCP_CONFIG_PATH")
    mcp_servers_json: str | None = Field(None, alias="MCP_SERVERS_JSON")

    # MindsDB (HTTP API)
    mindsdb_base_url: str = Field("http://127.0.0.1:47334/api", alias="MINDSDB_BASE_URL")
    mindsdb_token: str | None = Field(None, alias="MINDSDB_TOKEN")

    # Evidence panel / dataset defaults
    evidence_limit_default: int = Field(100, alias="EVIDENCE_LIMIT_DEFAULT")

    # Exclusions / validation caps
    max_excluded_tables: int = Field(1000, alias="MAX_EXCLUDED_TABLES")
    max_table_name_length: int = Field(255, alias="MAX_TABLE_NAME_LENGTH")
    settings_update_min_interval_s: float = Field(2.0, alias="SETTINGS_UPDATE_MIN_INTERVAL_S")

    # Database
    database_url: str = Field(
        "postgresql+psycopg://postgres:postgres@localhost:5432/pasteque",
        alias="DATABASE_URL",
    )

    # Authentication
    jwt_secret_key: str = Field("change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_expiration_minutes: int = Field(240, alias="JWT_EXPIRATION_MINUTES")
    admin_username: str = Field("admin", alias="ADMIN_USERNAME")
    admin_password: str = Field("admin", alias="ADMIN_PASSWORD")

    # NL→SQL generation (optional)
    nl2sql_enabled: bool = Field(False, alias="NL2SQL_ENABLED")
    nl2sql_db_prefix: str = Field("files", alias="NL2SQL_DB_PREFIX")
    nl2sql_include_samples: bool = Field(False, alias="NL2SQL_INCLUDE_SAMPLES")
    nl2sql_rows_per_table: int = Field(3, alias="NL2SQL_ROWS_PER_TABLE")
    nl2sql_value_truncate: int = Field(60, alias="NL2SQL_VALUE_TRUNCATE")
    nl2sql_plan_enabled: bool = Field(False, alias="NL2SQL_PLAN_ENABLED")
    nl2sql_plan_max_steps: int = Field(3, alias="NL2SQL_PLAN_MAX_STEPS")

    # NL→SQL multi‑agent (Explorer + Analyst)
    nl2sql_multiagent_enabled: bool = Field(False, alias="NL2SQL_MULTIAGENT_ENABLED")
    nl2sql_explore_rounds: int = Field(1, alias="NL2SQL_EXPLORE_ROUNDS")
    nl2sql_satisfaction_min_rows: int = Field(1, alias="NL2SQL_SATISFACTION_MIN_ROWS")

    @property
    def allowed_origins(self) -> List[str]:
        if self.allowed_origins_raw:
            return [item.strip() for item in self.allowed_origins_raw.split(",") if item.strip()]
        return ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]


settings = get_settings()


def assert_secure_configuration() -> None:
    """Fail fast in non-development envs when unsafe defaults are detected.

    This preserves developer ergonomics (defaults are allowed in ENV=development)
    while preventing accidental production runs with insecure credentials.
    """
    log = logging.getLogger("insight.core.config")
    env = (settings.env or "").strip().lower()
    if env in {"dev", "development", "local"}:
        # Be noisy but do not block developer workflows
        if settings.jwt_secret_key == "change-me":
            log.warning("Using default JWT secret in development; DO NOT use in production.")
        if settings.admin_password == "admin":
            log.warning("Using default admin password in development; DO NOT use in production.")
        if "postgres:postgres@" in settings.database_url:
            log.warning("Using default Postgres credentials in development; DO NOT use in production.")
        return

    # Harden non-development environments
    problems: list[str] = []
    if settings.jwt_secret_key == "change-me":
        problems.append("JWT_SECRET_KEY must be set to a strong secret")
    if settings.admin_password == "admin":
        problems.append("ADMIN_PASSWORD must not be 'admin'")
    if "postgres:postgres@" in settings.database_url:
        problems.append("DATABASE_URL must not use default 'postgres:postgres' credentials")

    if problems:
        raise RuntimeError(
            "Insecure configuration detected for ENV!='development': " + "; ".join(problems)
        )

def resolve_project_path(p: str) -> str:
    """Resolve ``p`` to an absolute path relative to the repo root when needed.

    - If ``p`` is absolute, return it unchanged.
    - If relative, anchor it at the project root inferred from this file's location.
    """
    from pathlib import Path as _Path  # local import to keep public surface minimal

    raw = _Path(p)
    if raw.is_absolute():
        return str(raw)
    # backend/src/insight_backend/core/config.py → repo root is parents[4]
    base = _Path(__file__).resolve().parents[4]
    return str((base / raw).resolve())
