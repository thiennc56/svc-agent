#!/usr/bin/env python3
"""Sinh tài liệu DOCX: Hướng dẫn phát triển nguồn dữ liệu MCP cho Trợ lý AI DNS.

  python -m venv /tmp/docxenv && /tmp/docxenv/bin/pip install python-docx
  /tmp/docxenv/bin/python build_docx.py [đường_dẫn_ra.docx]
"""
import sys
from pathlib import Path

import c1_intro
import c1b_compare
import c2_auth
import c3_protocol
import c4_tools
import c5_impl
import c6_test_register
import c7_security
import c8_appendix
from docx_helpers import Doc

VERSION = "1.1"
DATE = "19/11/2026"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / f"DNS_Huong_dan_phat_trien_MCP_server_v{VERSION}.docx"
CHANGELOG = [
    ("1.1", "19/11/2026", "Đăng ký nguồn trên HRM (tab Nguồn MCP): token tự sinh, hiển thị 1 lần, Test kết nối, Kiểm tra chuẩn, "
                          "hiệu lực ngay – thay quy trình sửa ConfigMap. URL nội bộ theo danh sách host cho phép. "
                          "Làm rõ tài khoản đăng nhập nội bộ (hrm-local) không dùng được với phân hệ. "
                          "Ghi giá trị OIDC_ACCEPTED_AUDIENCES thực tế (kiểm bằng đăng nhập SSO thật)."),
    ("1.0", "19/11/2026", "Bản đầu tiên."),
]


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    doc = Doc()
    doc.cover("Hướng dẫn phát triển nguồn dữ liệu MCP",
              "Tích hợp phân hệ (CRM, Kho, Dự án, Bán hàng…) với Trợ lý AI nền tảng DNS",
              [("Phiên bản", f"{VERSION} – {DATE}"),
               ("Chuẩn", "Model Context Protocol 2025-06-18 · Streamable HTTP · JSON-RPC 2.0 · profile DNS (`x-dns`)"),
               ("Xác thực", "SSO SOPBase (OIDC, JWT RS256) + `X-Agent-Token` riêng mỗi nguồn"),
               ("Phạm vi", "Công cụ chỉ đọc (GET), lọc theo quyền người hỏi"),
               ("Đối tượng", "Lập trình viên backend, kiến trúc sư, bảo mật/DevOps các phân hệ"),
               ("Đơn vị ban hành", "Đội nền tảng DNS (svc-agent / HRM)"),
               ("Mã nguồn mẫu", "`svc-agent/docs/mcp-guide/` (Python FastAPI, Node Express, mcp_check)")])
    doc.d.add_heading("Lịch sử thay đổi", 2)
    doc.table(["Phiên bản", "Ngày", "Nội dung"], [list(r) for r in CHANGELOG], [2.2, 2.6, 12.2], 9)
    doc.d.add_heading("Mục lục", 1)
    doc.toc()
    doc.h("Tóm tắt cho người đọc nhanh", 1)
    doc.bullets([
        "Phân hệ dựng **`POST /mcp`** (JSON-RPC 2.0) với 4 method: `initialize`, `ping`, `tools/list`, `tools/call`.",
        "Mỗi request kiểm **2 lớp**: `X-Agent-Token` (chỉ svc-agent) + **JWT SOPBase của người hỏi** (RS256, `iss`, `exp`, `aud`).",
        "**Khác client:** token là của ứng dụng chat (web/mobile HRM) → `aud` cấu hình riêng cho `/mcp`; quyền lấy từ **RBAC của phân hệ**, không lấy từ claim token.",
        "Công cụ **chỉ đọc**, kết quả gọn (≤ 20 bản ghi, ≤ 32 KB), có `x-dns` (quyền, nhóm, từ khoá, câu gợi ý) và `link` mở màn hình.",
        "`tools/list` lọc theo quyền; `tools/call` **kiểm lại quyền** + kiểm tham số theo `inputSchema`.",
        "Trước khi đăng ký: test tự động + `mcp_check.py` 0 lỗi + checklist bảo mật §10 đạt mục **Bắt buộc**.",
        "Đăng ký: quản trị nền tảng thêm nguồn trên HRM (*Cấu hình Chatbot → Nguồn MCP*) → nhận token 1 lần → **Kiểm tra chuẩn** phải ĐẠT (§9).",
    ])
    for chapter in (c1_intro, c1b_compare, c2_auth, c3_protocol, c4_tools, c5_impl, c6_test_register, c7_security, c8_appendix):
        chapter.build(doc)
    doc.footer(f"DNS – Hướng dẫn phát triển MCP server v{VERSION}")
    doc.save(str(out))
    print(f"Đã tạo {out}")


if __name__ == "__main__":
    main()
