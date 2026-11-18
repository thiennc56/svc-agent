import logging

from fastapi import APIRouter, FastAPI
from sqlalchemy import text

from app.api import chat, flows
from app.core.config import VERSION, settings
from app.core.db import engine

logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# PATH_PREFIX (vd. /agent): chia chung domain với svc-hrm qua ingress path Prefix, không cần rewrite.
PREFIX = settings.prefix

app = FastAPI(
    title="svc-agent",
    version=VERSION,
    description="AI agent platform dùng chung: chạy flow (dns.agent-flow/v1), gọi LLM (Groq/Ollama), "
                "tra cứu dữ liệu các phân hệ qua MCP. Chỉ nhận lời gọi service-to-service (X-Service-Token).",
    root_path=settings.root_path,
    docs_url=f"{PREFIX}/docs",
    redoc_url=None,
    openapi_url=f"{PREFIX}/openapi.json",
)
app.include_router(chat.router, prefix=PREFIX)
app.include_router(flows.router, prefix=PREFIX)

health = APIRouter(tags=["Health"])


@health.get("/health")
def health_check():
    return {"status": "ok", "service": "svc-agent", "version": VERSION}


@health.get("/health/ready")
def ready():
    checks = {}
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
    checks["mcpServers"] = sorted(settings.mcp_servers)
    checks["apps"] = sorted(settings.service_tokens)
    ok = checks["database"] == "ok"
    return {"status": "ok" if ok else "degraded", "checks": checks}


# Health ở gốc (probe k8s gọi thẳng pod) và dưới prefix (kiểm tra qua ingress)
app.include_router(health)
if PREFIX:
    app.include_router(health, prefix=PREFIX)
