#!/usr/bin/env python3
"""mcp-check – kiểm tra MCP server của phân hệ theo chuẩn DNS trước khi đăng ký với svc-agent.

Cách dùng:
  python mcp_check.py --url http://localhost:8300/mcp --agent-token <token> --tenant <tenant-id> \
      --token "$USER_JWT" [--low-token "$JWT_NGUOI_IT_QUYEN"] [--call crm_search_customers='{"query":"an"}']

Kiểm: bảo vệ X-Agent-Token / Bearer · initialize · tools/list (schema, annotations, x-dns, tên, mô tả) ·
lọc quyền (so sánh 2 người dùng) · tools/call (kết quả hợp lệ, kích thước) · tham số lạ bị từ chối · GET → 405.
Mã thoát: 0 = đạt (có thể có cảnh báo), 1 = có lỗi bắt buộc.
Chỉ cần: pip install httpx
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import httpx

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
MAX_RESULT_BYTES = 32_000
results: list[tuple[str, str, str]] = []  # (level, check, detail)


def report(level: str, check: str, detail: str = "") -> None:
    results.append((level, check, detail))
    icon = {"PASS": "✔", "WARN": "!", "FAIL": "✘"}[level]
    print(f"  {icon} [{level}] {check}" + (f" – {detail}" if detail else ""))


def post(url, body, agent=None, token=None, tenant=None, timeout=20.0):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2025-06-18", "X-Agent-App": "mcp-check"}
    if agent is not None:
        headers["X-Agent-Token"] = agent
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if tenant is not None:
        headers["tenant-id"] = tenant
    started = time.perf_counter()
    resp = httpx.post(url, json=body, headers=headers, timeout=timeout, follow_redirects=False)
    return resp, int((time.perf_counter() - started) * 1000)


def rpc(args, method, params=None, token=None):
    body = {"jsonrpc": "2.0", "id": int(time.time() * 1000) % 1_000_000, "method": method, "params": params or {}}
    return post(args.url, body, args.agent_token, token or args.token, args.tenant)


def check_auth(args) -> None:
    print("\n▶ Xác thực")
    body = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
    r, _ = post(args.url, body, None, args.token, args.tenant)
    report("PASS" if r.status_code in (401, 403) else "FAIL", "Thiếu X-Agent-Token bị từ chối", f"HTTP {r.status_code}")
    r, _ = post(args.url, body, "wrong-" + args.agent_token, args.token, args.tenant)
    report("PASS" if r.status_code in (401, 403) else "FAIL", "Sai X-Agent-Token bị từ chối", f"HTTP {r.status_code}")
    r, _ = post(args.url, body, args.agent_token, None, args.tenant)
    report("PASS" if r.status_code == 401 else "FAIL", "Thiếu Bearer người dùng → 401", f"HTTP {r.status_code}")
    r, _ = post(args.url, body, args.agent_token, "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ4In0.", args.tenant)
    report("PASS" if r.status_code == 401 else "FAIL", "JWT alg=none bị từ chối", f"HTTP {r.status_code}")
    if r.status_code == 401 and "www-authenticate" not in {k.lower() for k in r.headers}:
        report("WARN", "Nên trả header WWW-Authenticate khi 401")
    try:
        g = httpx.get(args.url, headers={"X-Agent-Token": args.agent_token}, timeout=10)
        report("PASS" if g.status_code in (401, 405) else "WARN", "GET /mcp trả 405 (không mở SSE)", f"HTTP {g.status_code}")
    except httpx.HTTPError as exc:
        report("WARN", "GET /mcp", type(exc).__name__)


def check_initialize(args) -> None:
    print("\n▶ initialize / ping")
    r, ms = rpc(args, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "mcp-check", "version": "1.0"}})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    res = data.get("result") or {}
    ok = r.status_code == 200 and "tools" in (res.get("capabilities") or {}) and res.get("serverInfo", {}).get("name")
    report("PASS" if ok else "FAIL", "initialize trả capabilities.tools + serverInfo", f"{ms} ms")
    report("PASS" if res.get("protocolVersion") else "FAIL", "protocolVersion", str(res.get("protocolVersion")))
    report("PASS" if res.get("instructions") else "WARN", "instructions (mô tả nguồn cho AI)")
    r, _ = rpc(args, "ping")
    report("PASS" if r.status_code == 200 and (r.json().get("result") == {}) else "FAIL", "ping → {}")
    r, _ = rpc(args, "no/such_method")
    code = ((r.json() if r.status_code == 200 else {}).get("error") or {}).get("code")
    report("PASS" if code == -32601 else "WARN", "Method lạ → -32601", str(code))


def check_tool_descriptor(t: dict) -> None:
    name = t.get("name", "")
    report("PASS" if NAME_RE.match(name) else "FAIL", f"{name}: tên snake_case 3–64 ký tự")
    desc = t.get("description") or ""
    report("PASS" if 20 <= len(desc) <= 1024 else "WARN", f"{name}: mô tả 20–1024 ký tự", f"{len(desc)} ký tự")
    schema = t.get("inputSchema") or {}
    report("PASS" if schema.get("type") == "object" else "FAIL", f"{name}: inputSchema.type = object")
    if schema.get("additionalProperties") is not False:
        report("WARN", f"{name}: nên đặt additionalProperties=false")
    for key, spec in (schema.get("properties") or {}).items():
        if not spec.get("description") and not spec.get("enum"):
            report("WARN", f"{name}.{key}: nên có description cho tham số")
        if spec.get("type") == "string" and "maxLength" not in spec and "enum" not in spec and "pattern" not in spec:
            report("WARN", f"{name}.{key}: chuỗi nên có maxLength / pattern")
    ann = t.get("annotations") or {}
    report("PASS" if ann.get("readOnlyHint") is True else "FAIL", f"{name}: annotations.readOnlyHint = true")
    meta = t.get("x-dns") or {}
    report("PASS" if meta.get("readOnly") is True else "FAIL", f"{name}: x-dns.readOnly = true")
    report("PASS" if isinstance(meta.get("permissions"), list) else "FAIL", f"{name}: x-dns.permissions (list)")
    report("PASS" if meta.get("title") and meta.get("group") else "WARN", f"{name}: x-dns.title + group")
    for pattern in meta.get("keywords") or []:
        try:
            re.compile(pattern)
            if re.search(r"[À-ỹđĐ]", pattern):
                report("WARN", f"{name}: keyword '{pattern}' phải viết KHÔNG dấu (so trên câu đã bỏ dấu)")
        except re.error:
            report("FAIL", f"{name}: keyword regex lỗi", pattern)
    qa = meta.get("queryArg")
    if qa and qa not in (schema.get("properties") or {}):
        report("FAIL", f"{name}: queryArg '{qa}' không có trong inputSchema")


def check_tools(args) -> list[dict]:
    print("\n▶ tools/list")
    r, ms = rpc(args, "tools/list")
    tools = ((r.json() if r.status_code == 200 else {}).get("result") or {}).get("tools")
    if not isinstance(tools, list):
        report("FAIL", "tools/list trả result.tools", f"HTTP {r.status_code}")
        return []
    report("PASS", f"tools/list: {len(tools)} công cụ", f"{ms} ms")
    report("PASS" if ms < 2000 else "WARN", "tools/list < 2 s")
    names = [t.get("name") for t in tools]
    report("PASS" if len(names) == len(set(names)) else "FAIL", "Tên công cụ không trùng")
    prefixes = {n.split("_", 1)[0] for n in names if n}
    if len(prefixes) > 1:
        report("WARN", "Nên dùng chung tiền tố phân hệ (vd. crm_, kho_)", ", ".join(sorted(prefixes)))
    for t in tools:
        check_tool_descriptor(t)
    if args.low_token:
        r2, _ = rpc(args, "tools/list", token=args.low_token)
        low = {t.get("name") for t in ((r2.json() if r2.status_code == 200 else {}).get("result") or {}).get("tools") or []}
        report("PASS" if low < set(names) or (low == set(names) and not names) else "WARN",
               "Lọc quyền: người ít quyền thấy ít công cụ hơn", f"{len(low)} / {len(names)}")
    return tools



def check_calls(args, tools: list[dict]) -> None:
    print("\n▶ tools/call")
    r, _ = rpc(args, "tools/call", {"name": "__khong_ton_tai__", "arguments": {}})
    res = (r.json() if r.status_code == 200 else {}).get("result") or {}
    report("PASS" if res.get("isError") is True else "FAIL", "Công cụ không tồn tại → isError=true")
    targets = dict(args.call or [])
    for t in tools:
        name = t.get("name")
        props = (t.get("inputSchema") or {}).get("properties") or {}
        r, _ = rpc(args, "tools/call", {"name": name, "arguments": {"__la__": "x"}})
        res = (r.json() if r.status_code == 200 else {}).get("result") or {}
        if (t.get("inputSchema") or {}).get("additionalProperties") is False or props:
            report("PASS" if res.get("isError") is True else "WARN", f"{name}: tham số lạ bị từ chối")
        if name not in targets and (t.get("inputSchema") or {}).get("required"):
            continue
        r, ms = rpc(args, "tools/call", {"name": name, "arguments": targets.get(name, {})})
        res = (r.json() if r.status_code == 200 else {}).get("result")
        if not isinstance(res, dict):
            report("FAIL", f"{name}: tools/call trả result", f"HTTP {r.status_code}")
            continue
        content_ok = isinstance(res.get("content"), list) and all(c.get("type") == "text" for c in res["content"])
        report("PASS" if content_ok else "FAIL", f"{name}: content[] dạng text", f"{ms} ms")
        report("PASS" if isinstance(res.get("structuredContent"), dict) else "WARN", f"{name}: có structuredContent (object)")
        size = len(json.dumps(res, ensure_ascii=False).encode())
        report("PASS" if size <= MAX_RESULT_BYTES else "WARN", f"{name}: kết quả ≤ 32 KB", f"{size} B")
        report("PASS" if ms < 5000 else "WARN", f"{name}: thời gian < 5 s", f"{ms} ms")
        if res.get("isError"):
            report("WARN", f"{name}: trả lỗi nghiệp vụ", json.dumps(res.get("structuredContent"), ensure_ascii=False)[:160])


def parse_call(value: str) -> tuple[str, dict]:
    name, _, raw = value.partition("=")
    try:
        data = json.loads(raw) if raw else {}
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--call {name}: JSON lỗi") from exc
    if not isinstance(data, dict):
        raise argparse.ArgumentTypeError(f"--call {name}: arguments phải là object")
    return name, data


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Kiểm tra MCP server theo chuẩn DNS")
    p.add_argument("--url", required=True, help="Endpoint MCP, vd. http://localhost:8300/mcp")
    p.add_argument("--agent-token", required=True, help="X-Agent-Token của nguồn")
    p.add_argument("--token", required=True, help="JWT SOPBase của người dùng thử (không gồm 'Bearer ')")
    p.add_argument("--tenant", required=True, help="tenant-id")
    p.add_argument("--low-token", help="JWT của người dùng ít quyền (kiểm lọc công cụ)")
    p.add_argument("--call", action="append", type=parse_call, help="name='{json args}' – gọi thử công cụ có tham số bắt buộc")
    args = p.parse_args(argv)
    print(f"mcp-check → {args.url}")
    try:
        check_auth(args)
        check_initialize(args)
        check_calls(args, check_tools(args))
    except httpx.HTTPError as exc:
        report("FAIL", "Kết nối MCP server", f"{type(exc).__name__}: {exc}")
    fails = sum(1 for lv, *_ in results if lv == "FAIL")
    warns = sum(1 for lv, *_ in results if lv == "WARN")
    print(f"\nKết quả: {len(results) - fails - warns} đạt · {warns} cảnh báo · {fails} lỗi")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

