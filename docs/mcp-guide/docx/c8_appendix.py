"""Phụ lục A–F."""
from docx_helpers import Doc


def build(doc: Doc) -> None:
    doc.h("Phụ lục", 1)
    doc.h("A. Cấu trúc bộ mẫu", 2)
    doc.code("""
svc-agent/docs/mcp-guide/
├── samples/python-fastapi/     MCP server CRM mẫu (FastAPI + Authlib)
│   ├── mcp_server.py           xác thực 2 lớp, JSON-RPC, /mcp
│   ├── crm_tools.py            công cụ + RBAC demo + x-dns
│   ├── schema_check.py         kiểm arguments theo inputSchema
│   ├── test_mcp_server.py      26 ca test (không cần mạng)
│   └── requirements.txt
├── samples/node-express/       MCP server Kho mẫu (Express 5 + jose)
├── tools/mcp_check.py          kiểm tra chuẩn server đang chạy
├── tools/demo_tokens.py        sinh JWKS + JWT thử (chỉ dev)
└── docx/                       mã sinh tài liệu này
""")
    doc.h("B. Ma trận test tối thiểu", 2)
    doc.table(["Mã", "Đầu vào", "Kỳ vọng"], [
        ["T01", "Không `X-Agent-Token`", "401"],
        ["T02", "JWT hết hạn / sai `aud` / sai `iss` / sai chữ ký / `alg=none`", "401 + WWW-Authenticate"],
        ["T03", "Người dùng không thuộc tenant", "403"],
        ["T04", "`initialize`", "protocolVersion, capabilities.tools, serverInfo"],
        ["T05", "Notification", "202, body rỗng"],
        ["T06", "Người không có quyền: `tools/list`", "Danh sách rỗng"],
        ["T07", "Người không có quyền: `tools/call`", "isError, not_permitted_or_unknown_tool"],
        ["T08", "Nhân viên tìm dữ liệu", "Chỉ bản ghi của mình, đúng tenant"],
        ["T09", "Quản lý tìm dữ liệu", "Toàn bộ tenant, không có tenant khác"],
        ["T10", "Truy cập bản ghi người khác", "not_found (không lộ tồn tại)"],
        ["T11", "Tham số thiếu / sai kiểu / vượt giới hạn / tham số lạ", "invalid_arguments"],
        ["T12", "Batch 3 message (1 notification)", "2 kết quả đúng id"],
    ], [1.4, 8.6, 7.0], 9)
    doc.h("C. Gợi ý công cụ theo phân hệ", 2)
    doc.table(["Phân hệ", "Công cụ gợi ý", "Câu hỏi mẫu"], [
        ["CRM", "`crm_search_customers`, `crm_get_customer`, `crm_my_opportunities`, `crm_activities_today`, `crm_customers_no_contact`",
         "Khách hàng An Phát do ai phụ trách? · Hôm nay tôi có lịch hẹn nào?"],
        ["Kho", "`kho_ton_kho`, `kho_sap_het_hang`, `kho_phieu_nhap_xuat`, `kho_hang_cham_luan_chuyen`",
         "Giấy A4 còn bao nhiêu? · Mặt hàng nào sắp hết?"],
        ["Bán hàng", "`sales_don_hang_cua_toi`, `sales_doanh_so_thang`, `sales_cong_no_khach_hang`, `sales_top_san_pham`",
         "Doanh số tháng này của tôi? · Khách nào đang nợ quá hạn?"],
        ["Dự án", "`project_my_tasks`, `project_overdue_tasks`, `project_status`, `project_workload_team`",
         "Tôi còn việc gì quá hạn? · Dự án X đang tiến độ bao nhiêu?"],
        ["Kế toán", "`acc_phieu_chi_cho_duyet`, `acc_so_du_quy`, `acc_cong_no_ncc`",
         "Có bao nhiêu phiếu chi chờ tôi duyệt? · Số dư quỹ hôm nay?"],
    ], [2.2, 8.8, 6.0], 9)
    doc.h("D. Công cụ HRM tham chiếu (đang chạy)", 2)
    doc.p("`svc-hrm/app/modules/mcp/api.py` + `app/modules/assistant/{tools,mcp_meta}.py` – 13 công cụ: "
          "`get_my_profile`, `get_my_leave_summary`, `list_my_leave_requests`, `list_my_payslips` (sensitive), "
          "`get_my_attendance_month`, `list_pending_approvals`, `hr_overview`, `company_hr_report`, `search_employee`, "
          "`get_employee_detail`, `list_leave_requests_org`, `list_attendance_explanations_org`, `team_attendance_today`. "
          "Quyền dùng chung với REST (`app:leave_requests:read`…), kiểm bằng `has_any_permission` như `require_permission`.")
    doc.h("E. Câu hỏi thường gặp", 2)
    doc.table(["Câu hỏi", "Trả lời"], [
        ["Phân hệ chưa dùng SOPBase?", "Phải tích hợp SOPBase trước (OIDC). `/mcp` không nhận tài khoản riêng của phân hệ."],
        ["Có cần SDK của DNS không?", "Không. Chỉ cần HTTP + JSON + thư viện verify JWT. Mẫu Python/Node có thể sao chép."],
        ["Có thể dùng claim `permissions` trong token?", "Không – đó là quyền HRM. Dùng RBAC của phân hệ (§4.2)."],
        ["Muốn thêm công cụ ghi (tạo đơn, duyệt)?", "Chưa hỗ trợ ở v1.0. Lộ trình: xác nhận trong chat + `approval.request` + audit."],
        ["`tools/list` chậm vì phải tính quyền?", "Cache quyền theo (tenant, user) 30–60 s phía phân hệ; svc-agent cũng cache 60 s."],
        ["Đổi tên công cụ được không?", "Không nên – flow đã lưu tham chiếu tên. Thêm công cụ mới, giữ công cụ cũ ≥ 2 tuần."],
        ["Kết quả lớn (báo cáo)?", "Trả tổng hợp + top N + `link` tới màn hình đầy đủ; không trả toàn bộ bảng."],
        ["Server ở ngoài cụm k8s?", "Cần HTTPS + allowlist host phía svc-agent + mTLS/IP allowlist; trao đổi với đội nền tảng."],
    ], [5.6, 11.4], 9)
    doc.h("F. Tài liệu tham khảo", 2)
    doc.bullets([
        "MCP Specification 2025-06-18 – modelcontextprotocol.io/specification/2025-06-18 (Transports, Tools, Authorization).",
        "OpenAI – Remote MCP servers & connectors (Responses API, `allowed_tools`, `require_approval`).",
        "Anthropic – Claude Connectors / Remote MCP.",
        "RFC 7519 (JWT), RFC 7517 (JWK), RFC 8414, RFC 9728, RFC 8707, RFC 8693 (Token Exchange).",
        "OWASP API Security Top 10 (2023) – BOLA, Broken Authentication, Unrestricted Resource Consumption.",
        "Nội bộ: `web-hrm/docs/chatbot.md` (kiến trúc chatbot, flow `dns.agent-flow/v1`), `svc-agent/README.md`.",
    ])
