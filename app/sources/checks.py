"""Kiểm tra chuẩn MCP server (rút gọn từ docs/mcp-guide/tools/mcp_check.py) – chạy từ nút "Kiểm tra chuẩn" trên HRM.

Dùng JWT của chính quản trị viên đang bấm (không có token người ít quyền → bỏ qua ca so sánh lọc quyền).
"""
from __future__ import annotations

import json
import re
import time

import httpx

from app.core.security import UserAuth
from app.runtime.mcp_client import PROTOCOL_VERSION

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
VI_RE = re.compile(r"[À-ỹđĐ]")


class Report:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, level: str, check: str, detail: str = "") -> None:
        self.items.append({"level": level, "check": check, "detail": detail[:200]})

    def ok(self, cond: bool, check: str, detail: str = "", fail: str = "fail") -> bool:
        self.add("pass" if cond else fail, check, detail)
        return cond

    def summary(self) -> dict:
        count = {lv: sum(1 for i in self.items if i["level"] == lv) for lv in ("pass", "warn", "fail")}
        return {"ok": count["fail"] == 0, **count, "items": self.items}


async def run_check(url: str, agent_token: str, auth: UserAuth, timeout: float = 20.0) -> dict:
    rep = Report()
    base = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION, "X-Agent-App": "mcp-check"}
    user = {"Authorization": auth.authorization, "tenant-id": auth.tenant_id}
    seq = iter(range(1, 1000))

    async def rpc(client, method, params=None, headers=None):
        body = {"jsonrpc": "2.0", "id": next(seq), "method": method, "params": params or {}}
        started = time.perf_counter()
        r = await client.post(url, json=body, headers=headers if headers is not None else {**base, **user, "X-Agent-Token": agent_token})
        return r, int((time.perf_counter() - started) * 1000)

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0), follow_redirects=False) as client:
            # Xác thực 2 lớp
            r, _ = await rpc(client, "ping", headers={**base, **user})
            rep.ok(r.status_code in (401, 403), "Thiếu X-Agent-Token bị từ chối", f"HTTP {r.status_code}")
            r, _ = await rpc(client, "ping", headers={**base, **user, "X-Agent-Token": "wrong-" + agent_token[:6]})
            rep.ok(r.status_code in (401, 403), "Sai X-Agent-Token bị từ chối", f"HTTP {r.status_code}")
            r, _ = await rpc(client, "ping", headers={**base, "tenant-id": auth.tenant_id, "X-Agent-Token": agent_token})
            rep.ok(r.status_code == 401, "Thiếu JWT người dùng → 401", f"HTTP {r.status_code}")
            forged = {**base, "tenant-id": auth.tenant_id, "X-Agent-Token": agent_token,
                      "Authorization": "Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0."}
            r, _ = await rpc(client, "ping", headers=forged)
            rep.ok(r.status_code == 401, "JWT alg=none bị từ chối", f"HTTP {r.status_code}")
            # initialize
            r, ms = await rpc(client, "initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                                     "clientInfo": {"name": "mcp-check", "version": "1.0"}})
            if not rep.ok(r.status_code == 200, "initialize với token hợp lệ", f"HTTP {r.status_code} · {ms} ms"):
                return {**rep.summary(), "tools": 0}
            res = (r.json() or {}).get("result") or {}
            rep.ok("tools" in (res.get("capabilities") or {}) and bool((res.get("serverInfo") or {}).get("name")),
                   "capabilities.tools + serverInfo")
            rep.ok(bool(res.get("instructions")), "instructions (mô tả nguồn cho AI)", fail="warn")
            # tools/list
            r, ms = await rpc(client, "tools/list")
            tools = ((r.json() if r.status_code == 200 else {}).get("result") or {}).get("tools")
            if not rep.ok(isinstance(tools, list), "tools/list trả result.tools", f"{ms} ms"):
                return {**rep.summary(), "tools": 0}
            rep.ok(ms < 2000, "tools/list < 2 s", f"{ms} ms", fail="warn")
            names = [t.get("name") for t in tools]
            rep.ok(len(names) == len(set(names)), "Tên công cụ không trùng")
            for t in tools:
                n = t.get("name", "?")
                meta, schema = t.get("x-dns") or {}, t.get("inputSchema") or {}
                rep.ok(bool(NAME_RE.match(n)), f"{n}: tên snake_case")
                rep.ok(20 <= len(t.get("description") or "") <= 1024, f"{n}: mô tả 20–1024 ký tự", fail="warn")
                rep.ok(schema.get("type") == "object", f"{n}: inputSchema.type = object")
                rep.ok((t.get("annotations") or {}).get("readOnlyHint") is True and meta.get("readOnly") is True,
                       f"{n}: chỉ đọc (readOnlyHint + x-dns.readOnly)")
                rep.ok(isinstance(meta.get("permissions"), list), f"{n}: x-dns.permissions")
                for kw in meta.get("keywords") or []:
                    try:
                        re.compile(kw)
                        if VI_RE.search(kw):
                            rep.add("warn", f"{n}: keyword phải viết không dấu", kw)
                    except re.error:
                        rep.add("fail", f"{n}: keyword regex lỗi", kw)
            # tools/call công cụ lạ
            r, _ = await rpc(client, "tools/call", {"name": "__khong_ton_tai__", "arguments": {}})
            res = (r.json() if r.status_code == 200 else {}).get("result") or {}
            rep.ok(res.get("isError") is True, "Công cụ không tồn tại → isError")
            size = len(json.dumps(tools, ensure_ascii=False).encode())
            rep.ok(size <= 64_000, "tools/list ≤ 64 KB", f"{size} B", fail="warn")
            return {**rep.summary(), "tools": len(tools)}
    except httpx.HTTPError as exc:
        rep.add("fail", "Kết nối MCP server", type(exc).__name__)
        return {**rep.summary(), "tools": 0}
