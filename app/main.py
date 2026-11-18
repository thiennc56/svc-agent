import logging

from fastapi import FastAPI
from sqlalchemy import text

from app.api import chat, flows
from app.core.config import VERSION, settings
from app.core.db import engine

logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="svc-agent",
    version=VERSION,
    description="AI agent platform dùng chung: chạy flow (dns.agent-flow/v1), gọi LLM (Groq/Ollama), "
                "tra cứu dữ liệu các phân hệ qua MCP. Chỉ nhận lời gọi service-to-service (X-Service-Token).",
    root_path=settings.root_path,
)
app.include_router(chat.router)
app.include_router(flows.router)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "svc-agent", "version": VERSION}


@app.get("/health/ready", tags=["Health"])
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
