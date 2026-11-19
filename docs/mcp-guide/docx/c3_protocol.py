"""Chương 5: Đặc tả giao thức /mcp (profile DNS)."""
from docx_helpers import Doc


def build(doc: Doc) -> None:
    doc.h("5. Đặc tả giao thức `POST /mcp`", 1)
    doc.h("5.1 Transport", 2)
    doc.table(["Mục", "Yêu cầu"], [
        ["Endpoint", "`POST /mcp` (đường dẫn có thể khác, khai báo khi đăng ký). `GET /mcp` → **405** (không mở SSE)."],
        ["Định dạng", "JSON-RPC 2.0, UTF-8, `Content-Type: application/json`. Hỗ trợ **batch** (mảng, tối đa 20 phần tử)."],
        ["Notification", "Message không có `id` (vd. `notifications/initialized`) → không trả lời; nếu cả request chỉ có notification → **202** rỗng."],
        ["Kích thước", "Body request ≤ 64 KB (413 nếu vượt). Kết quả một công cụ ≤ 32 KB (khuyến nghị ≤ 8 KB)."],
        ["Thời gian", "svc-agent timeout 20 s (`MCP_TIMEOUT_SECONDS`), kết nối 5 s. Mục tiêu p95 `tools/list` < 300 ms, `tools/call` < 2 s."],
        ["Mạng", "Chỉ trong cụm (ClusterIP), **không** mở ingress public cho `/mcp`. Không redirect."],
    ], [3.0, 14.0], 9)
    doc.h("5.2 Header svc-agent gửi", 2)
    doc.table(["Header", "Ví dụ", "Ghi chú"], [
        ["`Authorization`", "`Bearer eyJhbGciOiJSUzI1NiIs…`", "JWT SOPBase của người hỏi – bắt buộc verify."],
        ["`tenant-id`", "`00000000-0000-0000-0000-000000000010`", "UUID tenant."],
        ["`X-Agent-Token`", "`k3J…(48 ký tự)`", "Token riêng của nguồn."],
        ["`X-Agent-App`", "`hrm`", "Ứng dụng chat đang gọi (thông tin, ghi log)."],
        ["`MCP-Protocol-Version`", "`2025-06-18`", "Phiên bản giao thức."],
        ["`Accept`", "`application/json, text/event-stream`", "Server trả `application/json`."],
    ], [3.8, 5.6, 7.6], 9)
    doc.h("5.3 Các method", 2)
    doc.table(["method", "params", "result"], [
        ["`initialize`", "`{protocolVersion, capabilities, clientInfo}`",
         "`{protocolVersion, capabilities: {tools: {listChanged: false}}, serverInfo: {name, title, version}, instructions}`"],
        ["`ping`", "`{}`", "`{}`"],
        ["`tools/list`", "`{}` (không phân trang ở v1.0)", "`{tools: [Tool…]}` – **đã lọc theo quyền người hỏi**"],
        ["`tools/call`", "`{name, arguments}`", "`{content: [{type: \"text\", text}], structuredContent: {...}, isError}`"],
        ["khác", "–", "error `-32601` Method not found"],
    ], [2.6, 5.0, 9.4], 9)
    doc.code("""
POST /mcp
{"jsonrpc":"2.0","id":1,"method":"initialize",
 "params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"svc-agent","version":"1.0.0"}}}

200 OK
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18",
  "capabilities":{"tools":{"listChanged":false}},
  "serverInfo":{"name":"svc-crm","title":"CRM – Khách hàng","version":"1.0.0"},
  "instructions":"Dữ liệu CRM: khách hàng, cơ hội bán hàng. Chỉ đọc; đã lọc theo quyền người hỏi."}}
""", "Ví dụ 5.1 – initialize")
    doc.code("""
{"jsonrpc":"2.0","id":2,"result":{"tools":[{
  "name":"crm_search_customers",
  "title":"Tìm khách hàng",
  "description":"Tìm khách hàng theo tên hoặc mã (KH…). Trả mã, tên, SĐT, hạng, người phụ trách. Nhân viên kinh doanh chỉ thấy khách hàng mình phụ trách.",
  "inputSchema":{"type":"object","additionalProperties":false,"required":["query"],
    "properties":{"query":{"type":"string","minLength":1,"maxLength":80,"description":"Tên hoặc mã khách hàng"},
                  "limit":{"type":"integer","minimum":1,"maximum":20,"default":10,"description":"Số kết quả tối đa"}}},
  "annotations":{"title":"Tìm khách hàng","readOnlyHint":true,"destructiveHint":false,"idempotentHint":true,"openWorldHint":false},
  "x-dns":{"title":"Tìm khách hàng","module":"crm","group":"Khách hàng","readOnly":true,
    "permissions":["crm:customers:read:own","crm:customers:read:all"],"permissionMode":"any","roles":[],
    "keywords":["\\\\bkhach hang\\\\b","\\\\bkh\\\\d{3,}\\\\b"],"priority":20,"queryArg":"query",
    "suggestion":"Tìm khách hàng An Phát","sensitive":false}}]}}
""", "Ví dụ 5.2 – kết quả tools/list")
    doc.code("""
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"crm_search_customers","arguments":{"query":"an"}}}

{"jsonrpc":"2.0","id":3,"result":{
  "content":[{"type":"text","text":"{\\"total\\": 2, \\"items\\": [...]}"}],
  "structuredContent":{"total":2,"truncated":false,"items":[
     {"code":"KH001","name":"Công ty An Phát","phone":"0901000001","tier":"gold","owner":"sale1@test.com",
      "link":{"web":"/crm/customers/KH001","mobile":"/crm/customer/KH001","label":"Công ty An Phát"}}, ...]},
  "isError":false}}
""", "Ví dụ 5.3 – tools/call thành công")
    doc.h("5.4 Mã lỗi", 2)
    doc.table(["Tình huống", "Phản hồi"], [
        ["Thiếu/sai `X-Agent-Token`", "HTTP 401 `{\"error\":\"invalid_agent_token\"}`"],
        ["Chưa cấu hình token phía phân hệ", "HTTP 503 `{\"error\":\"mcp_disabled\"}`"],
        ["JWT thiếu/sai/hết hạn/sai `aud`", "HTTP 401 + `WWW-Authenticate: Bearer error=\"invalid_token\"`"],
        ["Không thuộc tenant / thiếu tenant", "HTTP 403 / 400"],
        ["JSON hỏng · request sai cấu trúc", "JSON-RPC `-32700` Parse error · `-32600` Invalid Request"],
        ["Method không hỗ trợ · params sai kiểu", "`-32601` · `-32602`"],
        ["Công cụ không tồn tại / không có quyền", "result `isError: true`, `structuredContent: {\"error\":\"not_permitted_or_unknown_tool\"}`"],
        ["Tham số không hợp lệ", "result `isError: true`, `{\"error\":\"invalid_arguments\",\"message\":\"…\"}`"],
        ["Không tìm thấy / không thuộc phạm vi", "result `isError: true`, `{\"error\":\"not_found\",\"message\":\"…\"}` (không phân biệt 2 trường hợp)"],
        ["Lỗi nội bộ", "result `isError: true`, `{\"error\":\"internal_error\"}` – không trả stacktrace/SQL"],
    ], [6.0, 11.0], 9)
    doc.box("Lỗi nghiệp vụ trả trong `result` với `isError: true` (để AI đọc và giải thích cho người dùng); lỗi giao thức "
            "dùng `error` JSON-RPC; lỗi xác thực dùng HTTP status.", "info", "Quy ước")
