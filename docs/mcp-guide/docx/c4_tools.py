"""Chương 6: Thiết kế công cụ & metadata x-dns."""
from docx_helpers import Doc


def build(doc: Doc) -> None:
    doc.h("6. Thiết kế công cụ & metadata `x-dns`", 1)
    doc.h("6.1 Quy tắc đặt tên & mô tả", 2)
    doc.table(["Thành phần", "Quy tắc", "Ví dụ tốt / chưa tốt"], [
        ["`name`", "snake_case, 3–64 ký tự, **tiền tố phân hệ**, động từ/đối tượng rõ; không đổi sau khi phát hành.",
         "✔ `kho_ton_kho`, `crm_search_customers`\n✘ `search`, `getData`, `tool1`"],
        ["`title`", "Tiếng Việt ngắn, hiển thị trên màn *Quy tắc* và bảng chọn công cụ.", "✔ Tồn kho theo mặt hàng"],
        ["`description`", "20–1024 ký tự, viết **cho AI đọc**: làm gì, khi nào dùng, trả gì, giới hạn phạm vi.",
         "✔ “Tra số lượng tồn theo tên hoặc mã hàng, lọc theo kho. Chỉ trả kho người hỏi được phân quyền.”\n✘ “API tồn kho”"],
        ["Tham số", "`additionalProperties: false`, có `description`; chuỗi có `maxLength`/`pattern`/`enum`; số có `minimum`/`maximum`.",
         "✔ `limit` 1–20, mặc định 10"],
    ], [2.6, 7.4, 7.0], 9)
    doc.h("6.2 Số lượng & độ chi tiết", 2)
    doc.bullets([
        "Mỗi phân hệ **5–20 công cụ**; mỗi công cụ trả lời một nhóm câu hỏi thực tế (xem danh sách gợi ý ở Phụ lục C).",
        "Ưu tiên công cụ **theo nghiệp vụ** (`du_an_tre_han`) hơn công cụ CRUD chung (`list_table`).",
        "Không tạo công cụ “chạy SQL tuỳ ý”, “gọi URL tuỳ ý”, “xuất toàn bộ dữ liệu”.",
        "Công cụ “của tôi” (`*_my_*`) không nhận tham số xác định người – luôn lấy người từ JWT.",
    ])
    doc.h("6.3 Kết quả trả về", 2)
    doc.bullets([
        "Trả object JSON trong `structuredContent` **và** chuỗi JSON tương ứng trong `content[0].text`.",
        "Chỉ chọn trường cần thiết; tối đa 20 bản ghi + `total` + `truncated`; số tiền là số (không định dạng), ngày ISO `YYYY-MM-DD`.",
        "Không trả: mật khẩu, token, khoá, số CCCD/tài khoản ngân hàng đầy đủ, dữ liệu của tenant khác, trường nội bộ (id DB nếu không cần).",
        "Có thể kèm `link: {web, mobile, label}` (đường dẫn **tương đối** trong ứng dụng) → nút *Mở chi tiết* (tối đa 8 nút/câu trả lời).",
        "Nội dung văn bản người dùng nhập (ghi chú, mô tả) có thể chứa *prompt injection* – cắt ngắn, không đặt vào `description` công cụ.",
    ])
    doc.h("6.4 Metadata `x-dns`", 2)
    doc.table(["Trường", "Kiểu", "Bắt buộc", "Ý nghĩa"], [
        ["`title`", "string", "✔", "Tên hiển thị."],
        ["`module`", "string", "✔", "Key phân hệ (`crm`, `kho`…), trùng key nguồn khi đăng ký."],
        ["`group`", "string", "✔", "Nhóm hiển thị (Khách hàng, Bán hàng…)."],
        ["`readOnly`", "bool", "✔", "Luôn `true` ở v1.0."],
        ["`permissions`", "string[]", "✔", "Quyền yêu cầu (giống REST endpoint) – chỉ để hiển thị/kiểm tra; phân hệ vẫn tự kiểm."],
        ["`permissionMode`", "`any`", "", "Có một trong các quyền là đủ."],
        ["`roles`", "string[]", "", "Nhóm vai trò bổ sung: `director`, `manager`, `hr`."],
        ["`keywords`", "regex[]", "", "Regex trên câu hỏi **đã bỏ dấu, chữ thường** (vd. `\\bton kho\\b`) – định tuyến khi model nhỏ không tự gọi công cụ."],
        ["`priority`", "int", "", "Nhỏ hơn = ưu tiên khi nhiều công cụ khớp từ khoá (mặc định 100)."],
        ["`queryArg`", "string", "", "Tên tham số nhận phần từ khoá trích từ câu hỏi (phải có trong `inputSchema`)."],
        ["`suggestion`", "string", "", "Câu hỏi gợi ý hiển thị cho người dùng có quyền."],
        ["`sensitive`", "bool", "", "Dữ liệu nhạy cảm (lương, công nợ cá nhân) – chỉ trả dữ liệu của chính người hỏi."],
    ], [2.8, 1.8, 1.6, 10.8], 9)
    doc.box("Regex `keywords` viết **không dấu** (`khach hang`, không phải `khách hàng`) vì svc-agent so khớp trên câu "
            "đã bỏ dấu. Dùng `\\b` để tránh khớp nhầm giữa từ. Kiểm bằng `mcp_check.py`.", "warn", "Lưu ý")
    doc.h("6.5 Phân quyền dữ liệu trong công cụ", 2)
    doc.bullets([
        "`tools/list`: chỉ trả công cụ người hỏi có quyền (AI không thấy công cụ ngoài quyền).",
        "`tools/call`: **kiểm lại** quyền – không giả định `tools/list` đã lọc (cache 60 s, quyền có thể vừa bị thu hồi).",
        "Lọc phạm vi dữ liệu ở **tầng truy vấn** (WHERE tenant_id = … AND (owner = me OR có quyền all)), không lọc sau khi tải hết.",
        "Dùng lại service/repository của REST API để đảm bảo quy tắc phân quyền **giống hệt** màn hình của phân hệ.",
        "Tham số không bao giờ mở rộng phạm vi: bỏ qua/ từ chối `tenant_id`, `user_id`, `owner` do AI truyền vào.",
    ])
