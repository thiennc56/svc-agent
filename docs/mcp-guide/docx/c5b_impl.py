"""Chương 7 (phần 2): khai báo công cụ, Node.js, ngôn ngữ khác."""
from docx_helpers import Doc


def build_more(doc: Doc) -> None:
    doc.h("7.3 Python – khai báo công cụ & tools/call", 2)
    doc.code("""
Tool("crm_my_opportunities", "Cơ hội bán hàng",
     "Danh sách cơ hội bán hàng (của tôi; quản lý thấy toàn công ty) và tổng giá trị, lọc theo giai đoạn.",
     ("crm:opportunities:read:own", "crm:opportunities:read:all"),       # giống REST GET /opportunities
     crm_my_opportunities,
     {"type": "object", "additionalProperties": False,
      "properties": {"stage": {"type": "string", "enum": ["lead", "proposal", "won", "lost"], "description": "Giai đoạn"}}},
     {"group": "Bán hàng", "keywords": [r"\\bco hoi\\b", r"\\bdoanh so\\b"], "priority": 40,
      "suggestion": "Tôi đang có bao nhiêu cơ hội bán hàng?"})

def crm_my_opportunities(ctx, args):
    rows = _scope(ctx, OPPORTUNITIES, "crm:opportunities:read:all")     # tenant + own/all ở tầng truy vấn
    ...
    return {"total": len(rows), "total_value": ..., "items": items[:20],
            "link": {"web": "/crm/opportunities", "mobile": "/crm/opportunities", "label": "Mở danh sách cơ hội"}}

def call_tool(ctx, name, args):
    tool = TOOL_BY_NAME.get(name)
    if tool is None or tool not in allowed_tools(ctx):    # kiểm quyền LẦN 2
        return {"error": "not_permitted_or_unknown_tool"}
    try:
        clean = validate_args(tool.input_schema, args)     # không tin tham số do AI sinh
    except ValueError as exc:
        return {"error": "invalid_arguments", "message": str(exc)}
    try:
        return tool.handler(ctx, clean)
    except Exception:
        logger.exception("tool failed: %s", name)         # log nội bộ, không trả stacktrace
        return {"error": "internal_error", "message": "Công cụ tạm thời lỗi"}
""", "samples/python-fastapi/crm_tools.py + mcp_server.py")
    doc.h("7.4 Node.js / Express – xác thực bằng `jose`", 2)
    doc.code("""
import { createRemoteJWKSet, jwtVerify } from 'jose';
const JWKS = createRemoteJWKSet(new URL(process.env.OIDC_JWKS_URL));    // tự cache + tải lại khi kid lạ

app.post('/mcp', async (req, res) => {
  if (!safeEqual(AGENT_TOKEN, req.get('X-Agent-Token'))) return deny(res, 401, 'invalid_agent_token', '...');
  const { payload: claims } = await jwtVerify(token, JWKS, {
    issuer: process.env.OIDC_ISSUER,
    audience: AUDIENCES,             // client web/mobile HRM – KHÁC client của phân hệ
    algorithms: ['RS256'], clockTolerance: 30, requiredClaims: ['sub', 'exp'],
  });
  const member = MEMBERS.get(`${tenant}|${email}`);   // thực tế: truy vấn RBAC phân hệ
  ...
});
""", "samples/node-express/server.mjs (rút gọn)")
    doc.h("7.5 Ngôn ngữ khác", 2)
    doc.table(["Nền tảng", "Thư viện verify JWT gợi ý", "Ghi chú"], [
        ["Java / Spring Boot", "`spring-boot-starter-oauth2-resource-server` (`jwk-set-uri`, validator `aud`)", "`@PostMapping(\"/mcp\")` nhận `JsonNode`."],
        [".NET", "`Microsoft.AspNetCore.Authentication.JwtBearer` (`Authority`, `ValidAudiences`)", "Minimal API `app.MapPost(\"/mcp\", …)`."],
        ["Go", "`MicahParks/keyfunc` + `golang-jwt/jwt/v5`", "`WithAudience`, `WithIssuer`, `WithValidMethods([\"RS256\"])`."],
        ["PHP / Laravel", "`firebase/php-jwt` + `JWK::parseKeySet`", "Middleware riêng cho route `/mcp`."],
    ], [3.2, 8.6, 5.2], 9)
    doc.box("Có thể dùng SDK MCP chính thức (`mcp` Python, `@modelcontextprotocol/sdk` TypeScript) ở chế độ Streamable HTTP "
            "**stateless + JSON response**; vẫn phải tự thêm 2 lớp xác thực, lọc quyền và `x-dns` như trên. Mẫu trong tài "
            "liệu không dùng SDK để dễ đọc, ít phụ thuộc.", "info", "SDK chính thức")
