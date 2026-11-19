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
    # Mount toàn bộ API dưới prefix khi chia chung domain với service khác qua ingress (vd. hrmapi.digigov.vn/agent).
    # Health luôn có ở cả /health và {prefix}/health (probe k8s gọi trực tiếp pod).
    path_prefix: str = Field(default="", validation_alias="PATH_PREFIX")

    @property
    def prefix(self) -> str:
        p = (self.path_prefix or "").strip().rstrip("/")
        return p if not p or p.startswith("/") else f"/{p}"

    # Postgres: postgresql+psycopg2://user:pass@postgres:5432/agent_db ; dev/test: sqlite
    db_url: str = Field(default="sqlite:///./agent.db", validation_alias="DB_URL")

    # Ứng dụng được phép gọi svc-agent: {"hrm": "<token>", "erp": "<token>"} (JSON, đặt trong k8s Secret).
    # Token của app X cũng được gửi kèm (X-Agent-Token) khi svc-agent gọi MCP server của app X.
    service_tokens: dict[str, str] = Field(default_factory=dict, validation_alias="SERVICE_TOKENS")

    # Danh sách MCP server ĐƯỢC PHÉP gọi (allowlist – flow chỉ tham chiếu theo key, không nhập URL tuỳ ý):
    # {"hrm": {"url": "http://svc-hrm:8000/mcp", "title": "HRM – Nhân sự", "apps": ["hrm"], "icon": "pi pi-users"}}
    mcp_servers: dict[str, dict] = Field(default_factory=dict, validation_alias="MCP_SERVERS")
    # Token RIÊNG cho từng MCP server (k8s Secret): {"crm": "<token>", "kho": "<token>"} → gửi làm X-Agent-Token.
    # Nguồn không có ở đây dùng token của app gọi (SERVICE_TOKENS[app]) – tương thích svc-hrm hiện tại.
    # Bắt buộc với phân hệ ngoài HRM: không bao giờ để phân hệ A nhận token dùng để gọi phân hệ B.
    mcp_tokens: dict[str, str] = Field(default_factory=dict, validation_alias="MCP_TOKENS")
    # Nguồn MCP động (màn "Nguồn MCP" trong HRM): host URL được phép (fnmatch, chống SSRF). IP link-local/metadata luôn bị chặn.
    mcp_allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "*.svc.cluster.local", "*.svc", "svc-*"],
        validation_alias="MCP_ALLOWED_HOSTS")
    # Khoá mã hoá token nguồn MCP lưu DB (Fernet, dẫn xuất SHA-256). Production BẮT BUỘC (k8s Secret); dev có khoá mặc định.
    credential_key: str = Field(default="", validation_alias="CREDENTIAL_KEY")
    # signed_context (giai đoạn C): khoá RSA ký JWT ngữ cảnh gửi phân hệ (PEM, k8s Secret) + issuer công khai
    agent_signing_key: str = Field(default="", validation_alias="AGENT_SIGNING_KEY")
    agent_issuer: str = Field(default="http://127.0.0.1:8100", validation_alias="AGENT_ISSUER")
    context_ttl_seconds: int = Field(default=120, ge=30, le=600, validation_alias="CONTEXT_TTL_SECONDS")
    # Nhật ký gọi công cụ (audit): giữ N ngày
    audit_retention_days: int = Field(default=90, ge=1, le=3650, validation_alias="AUDIT_RETENTION_DAYS")

    llm_timeout_seconds: float = Field(default=120.0, ge=1, validation_alias="LLM_TIMEOUT_SECONDS")
    mcp_timeout_seconds: float = Field(default=20.0, ge=1, validation_alias="MCP_TIMEOUT_SECONDS")
    # Cache danh sách công cụ theo (server, tenant, người dùng) – tools/list đã lọc theo quyền người hỏi
    tools_cache_seconds: int = Field(default=60, ge=0, le=3600, validation_alias="TOOLS_CACHE_SECONDS")
    ollama_keep_alive: str = Field(default="-1", validation_alias="OLLAMA_KEEP_ALIVE")

    @property
    def is_dev(self) -> bool:
        return self.app_env.strip().lower() in {"dev", "development", "local", "test"}


settings = Settings()
