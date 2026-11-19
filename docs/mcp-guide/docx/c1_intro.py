"""Chương 1–2: giới thiệu, kiến trúc."""
from docx_helpers import Doc


def build(doc: Doc) -> None:
    doc.h("1. Giới thiệu", 1)
    doc.p("Tài liệu hướng dẫn đội phát triển các phân hệ (CRM, Kho, Dự án, Bán hàng, Kế toán…) xây dựng **MCP server** "
          "để Trợ lý AI của nền tảng DNS tra cứu dữ liệu của phân hệ – **đúng quyền của người hỏi**, không cần đội "
          "nền tảng viết tích hợp riêng cho từng phân hệ.")
    doc.h("1.1 Đối tượng & phạm vi", 2)
    doc.bullets([
        "**Đối tượng:** lập trình viên backend, kiến trúc sư, kỹ sư bảo mật/DevOps của phân hệ.",
        "**Phạm vi phiên bản 1.0:** công cụ **chỉ đọc** (tra cứu, báo cáo, tìm kiếm). Công cụ ghi dữ liệu chưa được hỗ trợ.",
        "**Xác thực:** dùng chung SSO **SOPBase** – phân hệ verify JWT của người dùng, tự kiểm quyền bằng RBAC của mình.",
        "**Chuẩn:** Model Context Protocol (MCP) bản **2025-06-18**, transport Streamable HTTP + profile DNS (`x-dns`).",
    ])
    doc.h("1.2 Thuật ngữ", 2)
    doc.table(["Thuật ngữ", "Ý nghĩa"], [
        ["MCP", "Model Context Protocol – chuẩn mở (Anthropic khởi xướng; OpenAI, Google, Microsoft… hỗ trợ) để AI gọi công cụ/dữ liệu bên ngoài."],
        ["MCP server", "Dịch vụ của phân hệ cung cấp công cụ, endpoint `POST /mcp` (JSON-RPC 2.0)."],
        ["MCP client", "**svc-agent** – dịch vụ AI agent dùng chung của DNS: gọi LLM, chọn công cụ, gọi MCP server."],
        ["Công cụ (tool)", "Một hàm tra cứu có tên, mô tả, `inputSchema`; AI quyết định gọi khi cần."],
        ["`x-dns`", "Metadata mở rộng của DNS cho mỗi công cụ: quyền, nhóm, từ khoá định tuyến, câu gợi ý…"],
        ["SOPBase", "Máy chủ SSO/OIDC dùng chung (`https://sopbase.digigov.vn/auth`), cấp JWT RS256."],
        ["Client (OIDC)", "Ứng dụng đăng ký với SOPBase (web HRM, mobile HRM, web CRM…). Mỗi client có `client_id` riêng."],
        ["Tenant", "Doanh nghiệp khách hàng; header `tenant-id` (UUID)."],
    ], [3.5, 13.5])

    doc.h("2. Kiến trúc tổng quan", 1)
    doc.code("""
 Người dùng (web HRM / mobile / ô "Thử trợ lý")
        │  câu hỏi + JWT SOPBase của người dùng
        ▼
 svc-hrm  /assistant/chat ──► svc-agent (MCP client, LLM Groq/Ollama, flow kéo thả)
                                  │  POST /mcp  (JSON-RPC 2.0)
                                  │  Authorization: Bearer <JWT người hỏi>
                                  │  tenant-id, X-Agent-Token (token riêng của nguồn)
           ┌──────────────────────┼──────────────────────┬────────────────────┐
           ▼                      ▼                      ▼                    ▼
   svc-hrm /mcp           svc-crm /mcp            svc-kho /mcp       svc-project /mcp
   (đã có)                (phân hệ tự xây)        (phân hệ tự xây)   (phân hệ tự xây)
   RBAC HRM               RBAC CRM                RBAC Kho           RBAC Dự án
""", "Hình 1 – Vị trí MCP server của phân hệ")
    doc.h("2.1 Luồng xử lý một câu hỏi", 2)
    doc.bullets([
        "Người dùng hỏi: *“Khách hàng An Phát do ai phụ trách?”*.",
        "svc-agent gọi `tools/list` tới các nguồn được bật trong flow (cache 60 s theo người dùng) → mỗi phân hệ "
        "**chỉ trả công cụ người đó có quyền**.",
        "LLM chọn công cụ `crm_search_customers` với `{\"query\": \"An Phát\"}` (hoặc svc-agent định tuyến theo `x-dns.keywords`).",
        "svc-agent gọi `tools/call` → phân hệ verify JWT, **kiểm quyền lần 2**, lọc dữ liệu theo phạm vi người hỏi, trả kết quả gọn.",
        "LLM tổng hợp câu trả lời tiếng Việt; trường `link` trong kết quả thành nút *Mở chi tiết* trên web/mobile.",
    ], numbered=True)
    doc.box("Phân hệ là nơi **duy nhất** quyết định người hỏi được xem gì. svc-agent và LLM không bao giờ được coi là "
            "lớp bảo mật: flow chỉ có thể **thu hẹp** công cụ, không thể mở rộng quyền.", "warn", "Nguyên tắc cốt lõi")
