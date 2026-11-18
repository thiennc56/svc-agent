"""Cấu hình svc-agent (biến môi trường / .env / .env.local)."""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]

VERSION = "1.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_ROOT / ".env"), str(_ROOT / ".env.local")),
        extra="ignore",
    )

    project_name: str = "svc-agent"
    app_env: str = Field(default="dev", validation_alias="APP_ENV")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    root_path: str = Field(default="", validation_alias="ROOT_PATH")

    # Postgres: postgresql+psycopg2://user:pass@postgres:5432/agent_db ; dev/test: sqlite
    db_url: str = Field(default="sqlite:///./agent.db", validation_alias="DB_URL")

    # Ứng dụng được phép gọi svc-agent: {"hrm": "<token>", "erp": "<token>"} (JSON, đặt trong k8s Secret).
    # Token của app X cũng được gửi kèm (X-Agent-Token) khi svc-agent gọi MCP server của app X.
    service_tokens: dict[str, str] = Field(default_factory=dict, validation_alias="SERVICE_TOKENS")

    # Danh sách MCP server ĐƯỢC PHÉP gọi (allowlist – flow chỉ tham chiếu theo key, không nhập URL tuỳ ý):
    # {"hrm": {"url": "http://svc-hrm:8000/mcp", "title": "HRM – Nhân sự", "apps": ["hrm"], "icon": "pi pi-users"}}
    mcp_servers: dict[str, dict] = Field(default_factory=dict, validation_alias="MCP_SERVERS")

    llm_timeout_seconds: float = Field(default=120.0, ge=1, validation_alias="LLM_TIMEOUT_SECONDS")
    mcp_timeout_seconds: float = Field(default=20.0, ge=1, validation_alias="MCP_TIMEOUT_SECONDS")
    # Cache danh sách công cụ theo (server, tenant, người dùng) – tools/list đã lọc theo quyền người hỏi
    tools_cache_seconds: int = Field(default=60, ge=0, le=3600, validation_alias="TOOLS_CACHE_SECONDS")
    ollama_keep_alive: str = Field(default="-1", validation_alias="OLLAMA_KEEP_ALIVE")

    @property
    def is_dev(self) -> bool:
        return self.app_env.strip().lower() in {"dev", "development", "local", "test"}


settings = Settings()
