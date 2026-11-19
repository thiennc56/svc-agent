"""Chương 3: so sánh với ChatGPT, Claude và các nhà cung cấp MCP phổ biến."""
from docx_helpers import Doc


def build(doc: Doc) -> None:
    doc.h("3. So sánh với ChatGPT, Claude và các nhà cung cấp MCP", 1)
    doc.p("Cách DNS tích hợp phân hệ **giống cách các nền tảng AI lớn tích hợp ứng dụng bên thứ ba**: mỗi ứng dụng tự "
          "vận hành MCP server; nền tảng AI chỉ là client chuẩn.")
    doc.table(["Nền tảng / bên cung cấp", "Cách làm", "Xác thực người dùng"], [
        ["ChatGPT / OpenAI API", "Connectors & Apps; Responses API có tool `mcp` (`server_url`, `allowed_tools`, `require_approval`).",
         "OAuth 2.1 – người dùng bấm *Kết nối*; token gửi qua `authorization`, OpenAI không lưu."],
        ["Claude (Anthropic)", "Mục *Connectors* (remote MCP), Claude Desktop/Code; danh mục connector cho doanh nghiệp.",
         "OAuth 2.1 + PKCE, Dynamic Client Registration; admin Enterprise bật/tắt connector."],
        ["Grok (xAI), Gemini, Copilot", "Hỗ trợ remote MCP tool tương tự (URL server + danh sách công cụ cho phép).",
         "Bearer/OAuth theo server."],
        ["Notion, GitHub, Atlassian, Stripe, Linear, Slack…", "Tự vận hành MCP server từ xa (vd. `https://mcp.notion.com/mcp`), công cụ đọc/ghi.",
         "OAuth của chính ứng dụng; token cấp riêng cho MCP server."],
        ["Zapier MCP, Composio, Pipedream", "Cổng chuyển hàng nghìn REST API thành công cụ MCP bằng cấu hình.",
         "Họ giữ token OAuth của từng ứng dụng thay người dùng."],
        ["**DNS (tài liệu này)**", "Mỗi phân hệ tự xây `POST /mcp`; svc-agent là client; quản trị nền tảng đăng ký nguồn.",
         "**SSO SOPBase dùng chung** – không cần màn đồng ý; JWT người hỏi + `X-Agent-Token` riêng mỗi nguồn."],
    ], [4.0, 7.0, 6.0], 9)
    doc.h("3.1 Khác biệt chính & lý do", 2)
    doc.table(["Chuẩn MCP công khai", "Profile DNS", "Lý do"], [
        ["OAuth 2.1, RFC 9728/8414/7591, token riêng mỗi server (RFC 8707)", "JWT SOPBase của người hỏi + `X-Agent-Token`",
         "Mọi phân hệ cùng 1 IdP và nằm trong cụm nội bộ; không có màn đồng ý. Khi SOPBase hỗ trợ token exchange sẽ chuyển sang token riêng (§4.6)."],
        ["Công cụ đọc & ghi", "Chỉ đọc (v1.0)", "Giảm rủi ro; ghi dữ liệu cần xác nhận người dùng + duyệt – lộ trình sau."],
        ["Metadata chuẩn: `annotations`", "Thêm `x-dns`", "Quyền, nhóm, từ khoá định tuyến cho model nhỏ, câu gợi ý, link mở màn hình."],
        ["Streamable HTTP, có thể SSE", "Chỉ JSON, `GET /mcp` → 405", "Đơn giản, dễ vận hành sau ingress/proxy."],
    ], [5.2, 4.3, 7.5], 9)
    doc.h("3.2 Bài học áp dụng từ các nền tảng", 2)
    doc.bullets([
        "**Công cụ ít mà chất** – Notion/GitHub công bố 10–30 công cụ, mỗi công cụ một việc rõ ràng; tên + mô tả viết cho AI đọc.",
        "**Allowlist công cụ** – OpenAI `allowed_tools`, Claude Enterprise bật/tắt connector ⇔ DNS: node `tool.mcp` → `include`.",
        "**Đánh dấu chỉ đọc** – `annotations.readOnlyHint`; công cụ ghi luôn cần xác nhận (`require_approval`).",
        "**Không lưu/không log token** – OpenAI không lưu giá trị `authorization`; DNS cũng vậy ở mọi tầng.",
        "**Kết quả gọn, có cấu trúc** – trả `structuredContent` + giới hạn kích thước để không làm tràn ngữ cảnh model.",
    ])
    doc.box("Server viết đúng tài liệu này vẫn là **MCP server chuẩn**: sau này có thể mở cho Claude Desktop, ChatGPT "
            "hoặc agent khác dùng lại (khi bổ sung luồng OAuth chuẩn), không phải viết lại.", "ok", "Lợi ích")
