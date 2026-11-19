"""Công cụ MCP của phân hệ mẫu (CRM) + RBAC demo.

Thực tế: truy vấn DB của phân hệ. Quyền lấy từ RBAC CỦA PHÂN HỆ – KHÔNG lấy từ body / arguments.
Mỗi công cụ: tên snake_case có tiền tố phân hệ, mô tả rõ cho LLM, inputSchema chặt (additionalProperties=false),
quyền giống REST endpoint tương ứng, kết quả gọn (≤ MAX_ITEMS), có `link` để mở màn hình.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

MAX_ITEMS = 20

CUSTOMERS = [
    {"tenant": "t1", "code": "KH001", "name": "Công ty An Phát", "phone": "0901000001", "owner": "sale1@test.com", "tier": "gold"},
    {"tenant": "t1", "code": "KH002", "name": "Công ty Bình Minh", "phone": "0901000002", "owner": "sale2@test.com", "tier": "silver"},
    {"tenant": "t1", "code": "KH003", "name": "An Khang Group", "phone": "0901000003", "owner": "sale1@test.com", "tier": "silver"},
    {"tenant": "t2", "code": "KH900", "name": "An Phát (tenant khác)", "phone": "0909000000", "owner": "sale1@test.com", "tier": "gold"},
]
OPPORTUNITIES = [
    {"tenant": "t1", "code": "CH01", "customer": "KH001", "stage": "proposal", "value": 120_000_000, "owner": "sale1@test.com"},
    {"tenant": "t1", "code": "CH02", "customer": "KH002", "stage": "won", "value": 80_000_000, "owner": "sale2@test.com"},
]
MEMBERS = {  # (tenant, email) → quyền trong CRM
    ("t1", "sale1@test.com"): {"crm:customers:read:own", "crm:opportunities:read:own"},
    ("t1", "sale2@test.com"): {"crm:customers:read:own", "crm:opportunities:read:own"},
    ("t1", "manager@test.com"): {"crm:customers:read:all", "crm:opportunities:read:all"},
    ("t1", "guest@test.com"): set(),
    # Bot tự động (act=service trong X-Agent-Context): tài khoản dịch vụ, quyền TỐI THIỂU do phân hệ cấp
    ("t1", "bot-bao-cao@hrm.bot"): {"crm:opportunities:read:all"},
}


@dataclass
class Ctx:
    claims: dict
    tenant: str
    permissions: set[str]

    @property
    def email(self) -> str:
        return str(self.claims.get("email", "")).lower().strip()

    def can(self, *perms: str) -> bool:
        return any(p in self.permissions for p in perms)


def load_context(claims: dict, tenant: str) -> Ctx | None:
    """Người dùng phải là thành viên tenant trong CSDL phân hệ; None = không thuộc tenant."""
    email = str(claims.get("email", "")).lower().strip()
    perms = MEMBERS.get((tenant, email))
    return None if perms is None else Ctx(claims, tenant, set(perms))


def link(web: str, mobile: str | None = None, label: str | None = None) -> dict:
    out = {"web": web, "mobile": mobile or web}
    if label:
        out["label"] = label
    return out


@dataclass
class Tool:
    name: str
    title: str
    description: str
    permissions: tuple[str, ...]  # any-of; giống REST endpoint tương ứng. () = mọi người dùng đã xác thực
    handler: Callable[[Ctx, dict], dict]
    input_schema: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": False})
    meta: dict = field(default_factory=dict)  # group, keywords, priority, queryArg, suggestion, sensitive, roles

    def descriptor(self) -> dict:
        return {
            "name": self.name, "title": self.title, "description": self.description, "inputSchema": self.input_schema,
            "annotations": {"title": self.title, "readOnlyHint": True, "destructiveHint": False,
                            "idempotentHint": True, "openWorldHint": False},
            "x-dns": {"title": self.title, "module": "crm", "readOnly": True, "permissions": list(self.permissions),
                      "permissionMode": "any", "roles": [], "group": "Khác", "priority": 100,
                      "sensitive": False, **self.meta},
        }



def _scope(ctx: Ctx, rows: list[dict], all_perm: str) -> list[dict]:
    rows = [r for r in rows if r["tenant"] == ctx.tenant]  # cô lập tenant – LUÔN lọc ở tầng truy vấn
    return rows if ctx.can(all_perm) else [r for r in rows if r["owner"] == ctx.email]


def _public_customer(c: dict) -> dict:
    return {"code": c["code"], "name": c["name"], "phone": c["phone"], "tier": c["tier"], "owner": c["owner"],
            "link": link(f"/crm/customers/{c['code']}", f"/crm/customer/{c['code']}", c["name"])}


def crm_search_customers(ctx: Ctx, args: dict) -> dict:
    q = args["query"].lower()
    rows = [c for c in _scope(ctx, CUSTOMERS, "crm:customers:read:all") if q in c["name"].lower() or q in c["code"].lower()]
    limit = args["limit"]
    return {"total": len(rows), "items": [_public_customer(c) for c in rows[:limit]], "truncated": len(rows) > limit}


def crm_get_customer(ctx: Ctx, args: dict) -> dict:
    for c in _scope(ctx, CUSTOMERS, "crm:customers:read:all"):
        if c["code"].lower() == args["code"].lower():
            return _public_customer(c)
    # Không phân biệt "không tồn tại" và "không có quyền" → không lộ sự tồn tại của bản ghi
    return {"error": "not_found", "message": "Không tìm thấy khách hàng hoặc bạn không phụ trách khách hàng này"}


def crm_my_opportunities(ctx: Ctx, args: dict) -> dict:
    rows = _scope(ctx, OPPORTUNITIES, "crm:opportunities:read:all")
    if args.get("stage"):
        rows = [o for o in rows if o["stage"] == args["stage"]]
    items = [{k: o[k] for k in ("code", "customer", "stage", "value")} for o in rows[:MAX_ITEMS]]
    return {"total": len(rows), "total_value": sum(o["value"] for o in rows), "items": items,
            "link": link("/crm/opportunities", "/crm/opportunities", "Mở danh sách cơ hội")}


TOOLS: list[Tool] = [
    Tool("crm_search_customers", "Tìm khách hàng",
         "Tìm khách hàng theo tên hoặc mã (KH…). Trả mã, tên, SĐT, hạng, người phụ trách. "
         "Nhân viên kinh doanh chỉ thấy khách hàng mình phụ trách.",
         ("crm:customers:read:own", "crm:customers:read:all"), crm_search_customers,
         {"type": "object", "additionalProperties": False, "required": ["query"],
          "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 80, "description": "Tên hoặc mã khách hàng"},
                         "limit": {"type": "integer", "minimum": 1, "maximum": MAX_ITEMS, "default": 10,
                                   "description": "Số kết quả tối đa"}}},
         {"group": "Khách hàng", "keywords": [r"\bkhach hang\b", r"\bkh\d{3,}\b"], "priority": 20, "queryArg": "query",
          "suggestion": "Tìm khách hàng An Phát"}),
    Tool("crm_get_customer", "Chi tiết khách hàng", "Thông tin 1 khách hàng theo mã chính xác (vd. KH001).",
         ("crm:customers:read:own", "crm:customers:read:all"), crm_get_customer,
         {"type": "object", "additionalProperties": False, "required": ["code"],
          "properties": {"code": {"type": "string", "pattern": "^[A-Za-z0-9_-]{2,32}$", "description": "Mã khách hàng"}}},
         {"group": "Khách hàng", "priority": 30}),
    Tool("crm_my_opportunities", "Cơ hội bán hàng",
         "Danh sách cơ hội bán hàng (của tôi; quản lý thấy toàn công ty) và tổng giá trị, lọc theo giai đoạn.",
         ("crm:opportunities:read:own", "crm:opportunities:read:all"), crm_my_opportunities,
         {"type": "object", "additionalProperties": False,
          "properties": {"stage": {"type": "string", "enum": ["lead", "proposal", "won", "lost"], "description": "Giai đoạn"}}},
         {"group": "Bán hàng", "keywords": [r"\bco hoi\b", r"\bpipeline\b", r"\bdoanh so\b"], "priority": 40,
          "suggestion": "Tôi đang có bao nhiêu cơ hội bán hàng?"}),
]
TOOL_BY_NAME = {t.name: t for t in TOOLS}


def allowed_tools(ctx: Ctx) -> list[Tool]:
    return [t for t in TOOLS if not t.permissions or ctx.can(*t.permissions)]

