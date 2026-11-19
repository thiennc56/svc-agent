"""Chương 7: Hướng dẫn triển khai từng bước + code mẫu (phần 1: các bước, Python)."""
from docx_helpers import Doc

from c5b_impl import build_more


def build(doc: Doc) -> None:
    doc.h("7. Hướng dẫn triển khai từng bước", 1)
    doc.p("Mã nguồn mẫu chạy được (kèm test) nằm tại `svc-agent/docs/mcp-guide/samples/` – **python-fastapi** (CRM) và "
          "**node-express** (Kho). Thời gian ước tính cho một phân hệ đã có REST API: **2–4 ngày công**.")
    doc.table(["Bước", "Việc cần làm", "Kết quả"], [
        ["1", "Chọn 5–20 câu hỏi người dùng hay hỏi → thiết kế công cụ (Phụ lục C).", "Danh sách công cụ + quyền tương ứng"],
        ["2", "Thêm cấu hình: `MCP_AGENT_TOKEN`, `OIDC_ISSUER`, `OIDC_JWKS_URL`, `OIDC_ACCEPTED_AUDIENCES`.", "Secret/ConfigMap"],
        ["3", "Middleware xác thực: X-Agent-Token → JWT → thành viên tenant → nạp quyền.", "`Ctx` người hỏi"],
        ["4", "Khai báo công cụ (name, mô tả, inputSchema, quyền, `x-dns`) + handler gọi service hiện có.", "Registry công cụ"],
        ["5", "Router JSON-RPC: initialize, ping, tools/list, tools/call, batch, notification.", "`POST /mcp`"],
        ["6", "Test tự động (Phụ lục B) + chạy `mcp_check.py`.", "0 lỗi bắt buộc"],
        ["7", "Gửi phiếu đăng ký nguồn cho đội nền tảng (§9).", "Nguồn xuất hiện trong editor"],
    ], [1.2, 11.0, 4.8], 9)
    doc.h("7.1 Biến môi trường", 2)
    doc.code("""
MCP_AGENT_TOKEN=<token riêng do đội nền tảng cấp, 48 ký tự>          # k8s Secret
OIDC_ISSUER=https://sopbase.digigov.vn/auth
OIDC_JWKS_URL=https://sopbase.digigov.vn/auth/jwks
OIDC_ACCEPTED_AUDIENCES=<client_id web HRM>,<client_id mobile HRM>   # đội nền tảng cung cấp – KHÁC client của phân hệ
""", "svc-crm – .env / ConfigMap")
    doc.h("7.2 Python / FastAPI – xác thực người hỏi", 2)
    doc.code("""
from authlib.jose import JsonWebKey, JsonWebToken
_jwt = JsonWebToken(["RS256"])                       # chỉ RS256 – chặn alg=none / HS256

async def verify_user_jwt(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("missing_bearer")
    if not settings.audiences:
        raise AuthError("audience_not_configured")    # fail-closed
    options = {"iss": {"essential": True, "value": settings.issuer},
               "exp": {"essential": True}, "sub": {"essential": True},
               "aud": {"essential": True, "values": settings.audiences}}
    for attempt in (0, 1):
        try:
            claims = _jwt.decode(authorization[7:].strip(), await _key_set(force=attempt == 1),
                                 claims_options=options)
            claims.validate(leeway=30)
            return dict(claims)
        except JoseError as exc:                        # chữ ký sai, hết hạn, sai iss/aud
            raise AuthError(type(exc).__name__) from exc
        except ValueError as exc:                       # kid lạ (SOPBase xoay khoá) → nạp lại JWKS 1 lần
            if attempt == 1:
                raise AuthError("invalid_token") from exc
""", "samples/python-fastapi/mcp_server.py (rút gọn)")
    doc.code("""
@app.post("/mcp")
async def mcp_endpoint(request: Request):
    if not settings.agent_token:
        return _http_error(503, "mcp_disabled", "MCP chưa bật")
    if not hmac.compare_digest(settings.agent_token.encode(), (request.headers.get("X-Agent-Token") or "").encode()):
        return _http_error(401, "invalid_agent_token", "X-Agent-Token không hợp lệ")
    try:
        claims = await verify_user_jwt(request.headers.get("Authorization"))
    except AuthError:
        return _http_error(401, "invalid_token", "Token người dùng không hợp lệ hoặc hết hạn")
    ctx = load_context(claims, request.headers.get("tenant-id", "").strip())  # thành viên tenant + quyền phân hệ
    if ctx is None:
        return _http_error(403, "forbidden", "Người dùng không thuộc tenant này")
    payload = json.loads(await request.body())           # + giới hạn 64 KB, batch ≤ 20, Parse error
    res = handle(ctx, payload)
    return Response(status_code=202) if res is None else JSONResponse(res)
""", "Endpoint – thứ tự kiểm tra bắt buộc")
    build_more(doc)
