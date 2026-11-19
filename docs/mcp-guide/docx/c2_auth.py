"""Chương 4: Xác thực & danh tính – SOPBase dùng chung, lưu ý khác client."""
from docx_helpers import Doc


def build(doc: Doc) -> None:
    doc.h("4. Xác thực & danh tính (SOPBase dùng chung)", 1)
    doc.p("Mỗi request tới `/mcp` phải qua **hai lớp** độc lập – thiếu một lớp là từ chối:")
    doc.table(["Lớp", "Header", "Chứng minh điều gì", "Kiểm thế nào"], [
        ["1. Dịch vụ", "`X-Agent-Token`", "Request đến từ svc-agent (không phải người dùng gọi thẳng, không phải dịch vụ khác).",
         "So sánh **hằng thời gian** (`hmac.compare_digest` / `crypto.timingSafeEqual`) với token riêng của nguồn."],
        ["2. Người hỏi", "`Authorization: Bearer <JWT>`", "Ai đang hỏi (sub, email) – do SOPBase ký.",
         "Verify chữ ký RS256 qua JWKS, `iss`, `exp`, `aud` (allowlist), `sub` bắt buộc."],
        ["3. Ngữ cảnh", "`tenant-id`", "Doanh nghiệp đang làm việc.",
         "Người dùng **phải là thành viên** tenant trong CSDL phân hệ – không tin header một mình."],
    ], [2.2, 3.4, 5.4, 6.0], 9)
    doc.h("4.1 Thông số SOPBase", 2)
    doc.table(["Mục", "Giá trị"], [
        ["Discovery", "`https://sopbase.digigov.vn/auth/.well-known/openid-configuration`"],
        ["Issuer (`iss`)", "`https://sopbase.digigov.vn/auth`"],
        ["JWKS", "`https://sopbase.digigov.vn/auth/jwks` (RSA, `alg` RS256, có `kid` – sẽ xoay khoá)"],
        ["Grant hỗ trợ", "`authorization_code` (+ PKCE S256), `client_credentials`, `refresh_token`"],
        ["Khác", "`introspection_endpoint` `/auth/introspect`; **chưa** hỗ trợ token exchange (RFC 8693)"],
        ["Claims có thể có", "`sub`, `iss`, `aud`, `exp`, `iat`, `jti`, `email`, `name`, `scope`, `permissions`, `roles`, `app_namespace`"],
    ], [3.5, 13.5], 9)

    doc.h("4.2 Lưu ý quan trọng: KHÁC CLIENT", 2)
    doc.p("Mỗi ứng dụng đăng ký **client riêng** với SOPBase (web HRM, mobile HRM, web CRM, web Kho…). Token mà phân hệ "
          "nhận qua `/mcp` là token người dùng đăng nhập vào **ứng dụng đang chat** (hiện là HRM web/mobile) – "
          "**không phải** token của client phân hệ. Hệ quả:")
    doc.table(["#", "Vấn đề", "Cách xử lý đúng"], [
        ["1", "`aud`/`azp` của token = client HRM (web hoặc mobile), không phải client CRM/Kho.",
         "Cấu hình `OIDC_ACCEPTED_AUDIENCES` = danh sách client của **các ứng dụng chat** do đội nền tảng cung cấp "
         "(web HRM, mobile HRM…). Chỉ áp dụng danh sách này cho `/mcp`; REST API của phân hệ giữ nguyên `aud` của mình."],
        ["2", "Claims `permissions`, `roles`, `app_namespace` trong token là quyền của **ứng dụng HRM**.",
         "**Không** dùng các claim này để phân quyền phân hệ. Tra RBAC của phân hệ theo `sub`/`email` + `tenant-id`."],
        ["3", "Cùng người dùng nhưng `sub` có thể khác giữa đăng nhập SSO và tài khoản nội bộ.",
         "Ánh xạ người dùng theo `sub` (ưu tiên) **hoặc** `email` đã xác minh, chuẩn hoá `lower()`; ghi rõ quy tắc."],
        ["4", "`tenant-id` là UUID tenant của nền tảng.", "Phân hệ dùng cùng UUID tenant, hoặc bảng ánh xạ; không thấy → 403."],
        ["5", "Token dev/local (issuer `hrm-local`) chỉ svc-hrm hiểu.", "Phân hệ **không** chấp nhận issuer khác SOPBase ở production; dev dùng SOPBase thật hoặc JWKS giả (§7)."],
        ["6", "Client của phân hệ có `client_secret` (client_credentials).",
         "**Không** dùng client_credentials để tra dữ liệu thay người dùng trong `/mcp` – sẽ mất phân quyền theo người."],
    ], [0.8, 6.2, 10.0], 9)
    doc.box("Muốn biết `aud` thực tế: lấy access token từ trình duyệt (DevTools → request `/assistant/chat` → header "
            "Authorization), giải mã phần payload (base64url) – **không dán token production lên website giải mã trực tuyến**.",
            "info", "Mẹo")

    doc.h("4.3 Verify JWT – yêu cầu tối thiểu", 2)
    doc.bullets([
        "Chỉ chấp nhận `alg = RS256`; từ chối `none`, `HS256` (chống giả mạo bằng khoá công khai).",
        "Lấy khoá theo `kid` từ JWKS; cache ≤ 1 giờ; gặp `kid` lạ → tải lại JWKS **một lần** rồi mới từ chối.",
        "Bắt buộc `iss` đúng, `exp` còn hạn (lệch giờ ≤ 30 s), `aud` thuộc allowlist, có `sub`.",
        "Lỗi → HTTP **401** + `WWW-Authenticate: Bearer error=\"invalid_token\"`; **không** log token / lý do chi tiết ra client.",
        "Không gọi `/userinfo` hay `/introspect` cho mỗi request (chậm, tạo phụ thuộc); dùng khi cần thu hồi tức thì.",
    ])
    doc.h("4.4 X-Agent-Token", 2)
    doc.bullets([
        "Mỗi nguồn MCP có **token riêng** (biến `MCP_TOKENS` của svc-agent) – phân hệ A không thể dùng token của mình gọi phân hệ B.",
        "Đội nền tảng sinh token (48 ký tự ngẫu nhiên) và bàn giao qua kênh an toàn; phân hệ lưu trong k8s Secret (`MCP_AGENT_TOKEN`).",
        "Thiếu cấu hình token → `/mcp` trả **503** (fail-closed), không được mặc định cho qua.",
        "Xoay token: phân hệ chấp nhận tạm 2 giá trị (cũ + mới) trong thời gian chuyển đổi.",
    ])
    doc.h("4.5 Không chuyển tiếp token xuống dịch vụ khác", 2)
    doc.p("Chuẩn MCP cấm *token passthrough*. Phân hệ **không** gửi JWT nhận được từ `/mcp` sang API bên thứ ba hay "
          "dịch vụ khác. Nếu cần gọi dịch vụ nội bộ khác, dùng tài khoản dịch vụ của phân hệ **sau khi** đã lọc phạm vi theo người hỏi.")
    doc.h("4.6 Lộ trình nâng cấp danh tính", 2)
    doc.table(["Giai đoạn", "Cơ chế", "Phân hệ cần làm"], [
        ["Hiện tại (v1.0)", "JWT SOPBase của người hỏi + `X-Agent-Token`", "Theo tài liệu này."],
        ["Tiếp theo", "`signed_context`: svc-agent ký JWT 120 s (`aud` = key nguồn, có `sub`, `email`, `tenant`), JWKS "
         "`https://hrmapi.digigov.vn/agent/.well-known/jwks.json`", "Thêm issuer/JWKS thứ 2 vào verify; logic phân quyền giữ nguyên."],
        ["Khi SOPBase hỗ trợ RFC 8693", "Token exchange → token riêng `aud` = phân hệ", "Bỏ allowlist client chat; `aud` = client phân hệ như REST API."],
    ], [3.2, 7.8, 6.0], 9)
