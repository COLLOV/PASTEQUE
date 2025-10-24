from functools import lru_cache
from typing import List

from pydantic import Field
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

    # MCP configuration (declarative)
    mcp_config_path: str | None = Field("../plan/Z/mcp.config.json", alias="MCP_CONFIG_PATH")
    mcp_servers_json: str | None = Field(None, alias="MCP_SERVERS_JSON")

    # MindsDB (HTTP API)
    mindsdb_base_url: str = Field("http://127.0.0.1:47334/api", alias="MINDSDB_BASE_URL")
    mindsdb_token: str | None = Field(None, alias="MINDSDB_TOKEN")

    # Neo4j graph configuration
    neo4j_uri: str = Field("bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_username: str = Field("neo4j", alias="NEO4J_USERNAME")
    neo4j_password: str = Field("neo4j", alias="NEO4J_PASSWORD")
    neo4j_database: str | None = Field("neo4j", alias="NEO4J_DATABASE")
    neo4j_result_limit: int = Field(200, alias="NEO4J_RESULT_LIMIT")

    # Evidence panel / dataset defaults
    evidence_limit_default: int = Field(100, alias="EVIDENCE_LIMIT_DEFAULT")

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

    @property
    def allowed_origins(self) -> List[str]:
        if self.allowed_origins_raw:
            return [item.strip() for item in self.allowed_origins_raw.split(",") if item.strip()]
        return ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]


settings = get_settings()
