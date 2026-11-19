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
        ["5", "HRM còn cho đăng nhập **tài khoản nội bộ** (token tiền tố `hrm-local.`, HS256, issuer `hrm-local`) – chỉ svc-hrm hiểu.",
         "Phân hệ **không** chấp nhận token này (đúng thiết kế) → trả 401; trợ lý báo nguồn không truy cập được. Người dùng cần "
         "**đăng nhập SSO** để tra cứu dữ liệu phân hệ. Dev: dùng SOPBase thật hoặc JWKS giả (§8). Lộ trình `signed_context` (§4.6) "
         "sẽ hỗ trợ cả tài khoản nội bộ."],
        ["6", "Client của phân hệ có `client_secret` (client_credentials).",
         "**Không** dùng client_credentials để tra dữ liệu thay người dùng trong `/mcp` – sẽ mất phân quyền theo người."],
    ], [0.8, 6.2, 10.0], 9)
    doc.h("Giá trị thực tế (kiểm tra 19/11/2026 bằng đăng nhập SSO thật)", 3)
    doc.table(["Ứng dụng chat", "client_id (= `aud` của access token)", "Dùng ở"], [
        ["Web HRM production (hrm.digigov.vn)", "`E-yNLIGmd-EIf8yQas81Sg`", "Production"],
        ["App mobile HRM (iOS/Android)", "`G75nADuiXfxP_mBs06cRgg`", "Production"],
        ["Web HRM dev (localhost:4200)", "`q-CEmcJOdXDpey8DcnYmlw`", "Chỉ môi trường dev/test"],
    ], [5.5, 6.0, 5.5], 9)
    doc.code("""
# Production
OIDC_ACCEPTED_AUDIENCES=E-yNLIGmd-EIf8yQas81Sg,G75nADuiXfxP_mBs06cRgg
# Dev/test (thêm client localhost)
OIDC_ACCEPTED_AUDIENCES=E-yNLIGmd-EIf8yQas81Sg,G75nADuiXfxP_mBs06cRgg,q-CEmcJOdXDpey8DcnYmlw
""", "Cấu hình cho /mcp của phân hệ")
    doc.bullets([
        "Access token SOPBase: `alg=RS256`, có `kid`; claim `aud` là **mảng** (`[\"<client_id>\"]`), có thêm `client_id`; **không có** `azp`.",
        "Claim có sẵn: `sub`, `email`, `iss`, `exp`, `iat`, `jti`, `scope`, `permissions`, `roles`, `app_namespace`. `subject_types=public` "
        "→ cùng người dùng có **cùng `sub`** trên mọi client.",
        "Thời hạn access token **15 phút** – svc-agent luôn chuyển tiếp token mới nhất của người hỏi; phân hệ không cần refresh.",
        "client_id là định danh công khai (client PKCE), không phải bí mật – có thể ghi trong ConfigMap.",
    ])
    doc.box("Không dán token production lên website giải mã trực tuyến; nếu cần xem claim, giải mã phần payload (base64url) trên máy.",
            "info", "Lưu ý")

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
        "Mỗi nguồn MCP có **token riêng** – phân hệ A không thể dùng token của mình gọi phân hệ B.",
        "Token sinh tự động khi quản trị nền tảng thêm nguồn trên HRM (tab **Nguồn MCP**), hiển thị **một lần**, bàn giao qua "
        "kênh an toàn; phân hệ lưu trong k8s Secret (`MCP_AGENT_TOKEN`), không commit, không log.",
        "Thiếu cấu hình token → `/mcp` trả **503** (fail-closed), không được mặc định cho qua.",
        "Xoay token: phân hệ chấp nhận tạm 2 giá trị (cũ + mới) trong thời gian chuyển đổi.",
    ])
    doc.h("4.5 Không chuyển tiếp token xuống dịch vụ khác", 2)
    doc.p("Chuẩn MCP cấm *token passthrough*. Phân hệ **không** gửi JWT nhận được từ `/mcp` sang API bên thứ ba hay "
          "dịch vụ khác. Nếu cần gọi dịch vụ nội bộ khác, dùng tài khoản dịch vụ của phân hệ **sau khi** đã lọc phạm vi theo người hỏi.")
    doc.h("4.6 signed_context – X-Agent-Context (khuyến nghị từ v1.2)", 2)
    doc.p("Mỗi lời gọi `/mcp`, svc-agent gửi kèm header **`X-Agent-Context`**: JWT RS256 do svc-agent ký, sống **120 giây**, "
          "`aud` = **mã nguồn của chính phân hệ** (vd. `crm`). Phân hệ verify bằng JWKS công khai của svc-agent. Ưu điểm so với JWT SOPBase:")
    doc.bullets([
        "Token **chỉ dùng được cho đúng phân hệ** (aud riêng) – không thể đem token gửi CRM sang gọi Kho.",
        "Có cả **bot tự động** (`act = service`): workflow chạy theo lịch không có người đăng nhập, không có JWT SOPBase.",
        "Có cả người đăng nhập **tài khoản nội bộ** HRM (không qua SSO) – v1.1 không hỗ trợ.",
        "Đúng chuẩn MCP (không chuyển tiếp token của người dùng – *no token passthrough*).",
    ])
    doc.table(["Claim", "Ý nghĩa"], [
        ["`iss`", "`https://hrmapi.digigov.vn/agent` (production)"],
        ["`aud`", "`[\"<mã nguồn>\"]` – phải bằng `MCP_SOURCE_KEY` của phân hệ"],
        ["`sub`, `email`, `name`", "Người hỏi (người dùng) hoặc tài khoản bot. Ánh xạ người dùng theo `email` (chuẩn hoá lower)"],
        ["`tenant`", "UUID doanh nghiệp – **phải trùng header `tenant-id`**, khác → 403"],
        ["`act`", "`user` = người dùng chat · `service` = bot tự động (workflow)"],
        ["`permissions`", "Quyền `mcp:<nguồn>:*` HRM đã cấp cho người hỏi (chỉ của nguồn này) – thông tin bổ sung; phân hệ **vẫn tự kiểm RBAC**"],
        ["`iat`, `nbf`, `exp`, `jti`", "Thời hạn 120 s, mã duy nhất (có thể dùng chống phát lại)"],
    ], [4.0, 13.0], 9)
    doc.code("""
AGENT_ISSUER=https://hrmapi.digigov.vn/agent
AGENT_JWKS_URL=http://svc-agent.hrm-platform.svc.cluster.local:8000/.well-known/jwks.json   # trong cụm (hoặc https://hrmapi.digigov.vn/agent/.well-known/jwks.json)
MCP_SOURCE_KEY=crm                                                                           # = mã nguồn trên tab Nguồn MCP
""", "Cấu hình phân hệ (mẫu: samples/python-fastapi/agent_context.py)")
    doc.bullets([
        "Cấu hình đủ 3 biến trên → mẫu tự chuyển sang verify `X-Agent-Context`; chưa cấu hình → dùng JWT SOPBase như v1.1 (không phá vỡ).",
        "Khi phân hệ đã verify `X-Agent-Context`, báo quản trị nền tảng **tắt “Gửi kèm JWT SOPBase”** của nguồn trên tab Nguồn MCP – "
        "bắt buộc để **Bot tự động** đọc được dữ liệu phân hệ.",
        "Bot: phân hệ tạo tài khoản dịch vụ (vd. `bot-bao-cao@hrm.bot`) với quyền **tối thiểu**, ghi rõ trong nhật ký là bot.",
        "Khi SOPBase hỗ trợ token exchange (RFC 8693): có thể chuyển sang token SOPBase riêng `aud` = phân hệ; giao thức `/mcp` không đổi.",
    ])
    doc.h("4.7 Quyền mcp:* trong HRM (lớp 1) + RBAC phân hệ (lớp 2)", 2)
    doc.p("Nguồn bật **“Yêu cầu cấp quyền trong HRM”** (mặc định khi thêm nguồn): admin doanh nghiệp vào *Phân quyền vai trò* → nhóm "
          "**“Trợ lý AI · <tên nguồn>”** → tích từng công cụ (`mcp:crm:crm_search_customers`) hoặc **Tất cả công cụ** (`mcp:crm:*`) cho từng vai trò. "
          "svc-agent chỉ đưa cho AI các công cụ người hỏi được cấp và **kiểm lại khi gọi**; phân hệ vẫn kiểm RBAC của mình (2 lớp). "
          "Mọi lần gọi được ghi **Nhật ký** (Cấu hình Chatbot → Nhật ký): ai/bot, công cụ, kết quả, thời gian – không lưu dữ liệu.")
