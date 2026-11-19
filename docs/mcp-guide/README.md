# Bộ hướng dẫn phát triển MCP server cho phân hệ DNS

Tài liệu chính: **`DNS_Huong_dan_phat_trien_MCP_server_v1.1.docx`** (gửi cho đội CRM, Kho, Dự án, Bán hàng…).

Gửi cho đội phân hệ: **nén cả thư mục `mcp-guide/`** (DOCX + `samples/` + `tools/`) – không cần `docx/` (mã sinh tài liệu).
`OIDC_ACCEPTED_AUDIENCES` (production) = `E-yNLIGmd-EIf8yQas81Sg,G75nADuiXfxP_mBs06cRgg` (client_id web + mobile HRM – công khai, đã ghi trong tài liệu §4.2).
Gửi riêng qua kênh an toàn (KHÔNG để trong tài liệu): token `MCP_AGENT_TOKEN` – có sau khi quản trị nền tảng thêm nguồn trên HRM.

| Thư mục | Nội dung |
|---|---|
| `samples/python-fastapi/` | MCP server CRM mẫu (FastAPI + Authlib): xác thực 2 lớp, lọc quyền, `x-dns`, 26 test |
| `samples/node-express/` | MCP server Kho mẫu (Express 5 + jose) |
| `tools/mcp_check.py` | Kiểm tra server đang chạy theo chuẩn DNS (mã thoát 0 = đạt) |
| `tools/demo_tokens.py` | Sinh JWKS + JWT thử cho dev (không dùng production) |
| `docx/` | Mã sinh file DOCX (`build_docx.py`) |

```bash
# Test mẫu Python
cd samples/python-fastapi && pip install -r requirements.txt && pytest -q

# Chạy mẫu + kiểm chuẩn (dev, JWKS giả)
python tools/demo_tokens.py /tmp/mcp-demo && python -m http.server 8399 -d /tmp/mcp-demo &
cd samples/python-fastapi && MCP_AGENT_TOKEN=dev-agent-token OIDC_JWKS_URL=http://127.0.0.1:8399/jwks.json \
  OIDC_ISSUER=https://sopbase.test/auth OIDC_ACCEPTED_AUDIENCES=hrm-web-client uvicorn mcp_server:app --port 8300 &
python tools/mcp_check.py --url http://127.0.0.1:8300/mcp --agent-token dev-agent-token --tenant t1 \
  --token "$(cat /tmp/mcp-demo/token_manager.txt)" --low-token "$(cat /tmp/mcp-demo/token_guest.txt)" \
  --call crm_search_customers='{"query":"an"}' --call crm_get_customer='{"code":"KH001"}'

# Sinh lại DOCX
python -m venv /tmp/docxenv && /tmp/docxenv/bin/pip install python-docx
cd docx && /tmp/docxenv/bin/python build_docx.py
```
