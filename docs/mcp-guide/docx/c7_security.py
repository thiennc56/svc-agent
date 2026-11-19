"""Chương 10: Checklist bảo mật."""
from docx_helpers import Doc

AUTH = [
    ("XT-01", "`/mcp` chỉ nhận request có `X-Agent-Token` đúng, so sánh hằng thời gian; thiếu cấu hình → 503 (fail-closed).", "Bắt buộc"),
    ("XT-02", "Verify JWT: chữ ký RS256 qua JWKS SOPBase, `iss`, `exp`, `aud` ∈ allowlist client chat, có `sub`.", "Bắt buộc"),
    ("XT-03", "Từ chối `alg=none`, HS*, token không có `kid` hợp lệ; tải lại JWKS khi `kid` lạ (tối đa 1 lần/request).", "Bắt buộc"),
    ("XT-04", "Không dùng claim `permissions`/`roles` của token HRM để phân quyền phân hệ.", "Bắt buộc"),
    ("XT-05", "Người dùng phải là thành viên tenant trong CSDL phân hệ; không tin header `tenant-id` đơn lẻ.", "Bắt buộc"),
    ("XT-06", "Không chuyển tiếp JWT nhận được sang dịch vụ khác / bên thứ ba (no token passthrough).", "Bắt buộc"),
    ("XT-07", "401 kèm `WWW-Authenticate`; thông điệp lỗi chung, không tiết lộ lý do chi tiết.", "Khuyến nghị"),
]
AUTHZ = [
    ("PQ-01", "`tools/list` chỉ trả công cụ người hỏi có quyền.", "Bắt buộc"),
    ("PQ-02", "`tools/call` kiểm quyền lại, không dựa vào cache/kết quả `tools/list`.", "Bắt buộc"),
    ("PQ-03", "Quyền mỗi công cụ **giống** REST endpoint tương ứng; dùng lại service/repository có sẵn.", "Bắt buộc"),
    ("PQ-04", "Lọc tenant + phạm vi (own/team/all) ở tầng truy vấn DB.", "Bắt buộc"),
    ("PQ-05", "Tham số không thể mở rộng phạm vi (bỏ qua `tenant_id`, `user_id`, `owner`… do AI truyền).", "Bắt buộc"),
    ("PQ-06", "Không phân biệt “không tồn tại” và “không có quyền” trong thông điệp lỗi.", "Bắt buộc"),
    ("PQ-07", "Dữ liệu nhạy cảm (`sensitive`) chỉ của chính người hỏi.", "Bắt buộc"),
    ("PQ-08", "Chỉ công cụ đọc: không INSERT/UPDATE/DELETE, không gọi API có tác dụng phụ (gửi mail, thanh toán…).", "Bắt buộc"),
]
INPUT = [
    ("DV-01", "Kiểm `arguments` theo `inputSchema`: kiểu, độ dài, pattern, enum, min/max; từ chối tham số lạ.", "Bắt buộc"),
    ("DV-02", "Truy vấn tham số hoá (ORM/bind), không ghép chuỗi SQL; không có công cụ SQL/URL tuỳ ý.", "Bắt buộc"),
    ("DV-03", "Giới hạn body ≤ 64 KB, batch ≤ 20, số bản ghi ≤ 20, kết quả ≤ 32 KB, timeout DB ≤ 5 s.", "Bắt buộc"),
    ("DV-04", "Không trả mật khẩu, token, khoá, CCCD/tài khoản ngân hàng đầy đủ; che bớt khi cần (`****1234`).", "Bắt buộc"),
    ("DV-05", "`link` chỉ là đường dẫn tương đối trong ứng dụng; không chèn URL ngoài do người dùng nhập.", "Bắt buộc"),
    ("DV-06", "Cắt ngắn văn bản tự do do người dùng nhập (ghi chú, mô tả) – giảm prompt injection gián tiếp.", "Khuyến nghị"),
    ("DV-07", "`description` công cụ là hằng số trong code, không sinh từ dữ liệu.", "Bắt buộc"),
]
OPS = [
    ("VH-01", "`/mcp` chỉ trong cụm (ClusterIP / NetworkPolicy chỉ cho svc-agent); không ingress public.", "Bắt buộc"),
    ("VH-02", "`MCP_AGENT_TOKEN` trong k8s Secret, không commit, không log; xoay định kỳ (≤ 6 tháng) hoặc khi nghi lộ.", "Bắt buộc"),
    ("VH-03", "Audit mỗi `tools/call`: thời gian, người (email/sub), tenant, công cụ, thành công/lỗi, thời lượng.", "Bắt buộc"),
    ("VH-04", "**Không** log token, `arguments` chứa dữ liệu cá nhân, nội dung kết quả.", "Bắt buộc"),
    ("VH-05", "Không trả stacktrace/SQL/đường dẫn file trong lỗi.", "Bắt buộc"),
    ("VH-06", "Rate limit theo người dùng & tenant; cảnh báo khi 401/403 tăng bất thường.", "Khuyến nghị"),
    ("VH-07", "Gọi JWKS/HTTP ra ngoài: HTTPS, timeout, không theo redirect.", "Bắt buộc"),
    ("VH-08", "Dependency (authlib/jose/express…) cập nhật bản vá; quét lỗ hổng trong CI.", "Khuyến nghị"),
    ("VH-09", "Test tự động (Phụ lục B) chạy trong CI; `mcp_check.py` 0 lỗi trước mỗi lần phát hành.", "Bắt buộc"),
]


def build(doc: Doc) -> None:
    doc.h("10. Checklist bảo mật", 1)
    doc.p("Phân hệ tự đánh giá và gửi kèm phiếu đăng ký. Mục **Bắt buộc** chưa đạt → không được bật ở production.")
    doc.h("10.1 Xác thực", 2)
    doc.checklist(AUTH)
    doc.h("10.2 Phân quyền dữ liệu", 2)
    doc.checklist(AUTHZ)
    doc.h("10.3 Dữ liệu vào / ra", 2)
    doc.checklist(INPUT)
    doc.h("10.4 Vận hành & giám sát", 2)
    doc.checklist(OPS)
    doc.h("10.5 Mô hình đe doạ (tóm tắt)", 2)
    doc.table(["Mối đe doạ", "Kịch bản", "Biện pháp"], [
        ["Gọi thẳng `/mcp`", "Kẻ tấn công trong mạng nội bộ gọi /mcp bằng JWT của mình để vượt UI.", "XT-01, VH-01; dù vậy vẫn chỉ thấy dữ liệu đúng quyền (PQ-*)."],
        ["Token sai đối tượng", "Dùng token của client khác / issuer khác.", "XT-02, XT-03 (allowlist `aud`, `iss`)."],
        ["Leo thang qua tham số", "AI (bị dẫn dắt) truyền `owner=sếp` hoặc `tenant=khác`.", "PQ-05, DV-01."],
        ["Prompt injection", "Ghi chú khách hàng chứa “hãy gọi công cụ X và gửi…”.", "Chỉ công cụ đọc (PQ-08), DV-06, phân quyền ở server."],
        ["Lộ dữ liệu qua lỗi/log", "Stacktrace, SQL, token trong log.", "VH-04, VH-05, XT-07."],
        ["Từ chối dịch vụ", "Câu hỏi khiến công cụ quét toàn bảng.", "DV-03, VH-06, index DB."],
        ["Lộ token dịch vụ", "`X-Agent-Token` bị lộ.", "Token riêng mỗi nguồn; vẫn cần JWT người dùng hợp lệ; xoay token (VH-02)."],
    ], [3.2, 6.6, 7.2], 9)
