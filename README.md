# svc-agent

Dịch vụ **AI agent dùng chung** cho các dự án DNS (HRM, ERP…): chạy flow `dns.agent-flow/v1`, gọi LLM (Groq / Ollama, model dự phòng),
tra cứu dữ liệu các phân hệ qua **MCP** với JWT của người hỏi (phân hệ tự kiểm quyền). Chỉ nhận lời gọi service-to-service.

Tài liệu kiến trúc + nghiệp vụ đầy đủ: `web-hrm/docs/chatbot.md`.

## Cấu trúc
```
app/
  core/      config (env), db, security (X-Service-Token, ngữ cảnh người dùng)
  flows/     catalog (loại node), schema (Pydantic), compiler (validate → Plan), defaults (luồng mặc định), service (version)
  runtime/   llm.py (Ollama), llm_groq.py, mcp_client.py, routing.py (từ khoá x-dns), agent.py (tool calling), resolve.py
  api/       chat.py (/v1/apps/{app}/chat SSE), flows.py (catalog, registry, flow CRUD, version, ping)
alembic/     migration (bảng agent_flow_versions, version table svc_agent_alembic_version)
tests/       pytest (không cần mạng: MCP + LLM giả lập)
```

## Chạy local
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt psycopg2-binary $(grep -v psycopg2 requirements.txt)
cp .env.example .env.local          # SERVICE_TOKENS, MCP_SERVERS
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --port 8100
.venv/bin/python -m pytest
```
svc-hrm local trỏ tới: `AGENT_URL=http://127.0.0.1:8100 AGENT_SERVICE_TOKEN=<token trong SERVICE_TOKENS.hrm>`.

## Biến môi trường
| Biến | Ý nghĩa |
|---|---|
| `DB_URL` | Postgres `agent_db` (dev: sqlite) |
| `SERVICE_TOKENS` | `{"hrm": "<token>"}` – app được gọi; token cũng gửi kèm khi gọi MCP của app (`X-Agent-Token`) |
| `MCP_SERVERS` | Allowlist `{"key": {"url", "title", "apps", "icon", "color", "description"}}` |
| `LLM_TIMEOUT_SECONDS` / `MCP_TIMEOUT_SECONDS` / `TOOLS_CACHE_SECONDS` | Timeout / cache tools/list theo người dùng |

## Docker / k8s
`Dockerfile` (python 3.12-slim, non-root, gunicorn+uvicorn). Manifest + script: `DNS/k8s/k8s-svc-agent/` (`deploy.sh secret|apply|hrm-config|status`).
