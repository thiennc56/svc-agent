"""MCP server mẫu cho phân hệ DNS (ví dụ: CRM) – FastAPI + Authlib.

Chuẩn: Model Context Protocol 2025-06-18, transport Streamable HTTP (chỉ phản hồi JSON), JSON-RPC 2.0.
Profile DNS: công cụ CHỈ ĐỌC, lọc theo quyền người hỏi, metadata `x-dns` cho Trợ lý AI (svc-agent).

Hai lớp xác thực (bắt buộc cả hai):
  1. X-Agent-Token – chỉ svc-agent được gọi (so sánh hằng thời gian).
  2. Authorization: Bearer <JWT SOPBase của NGƯỜI HỎI> – verify chữ ký (JWKS, RS256), iss, exp, aud (allowlist).
Sau đó: người dùng phải là thành viên tenant (header tenant-id) → quyền lấy từ RBAC CỦA PHÂN HỆ.

Chạy:  pip install -r requirements.txt && MCP_AGENT_TOKEN=... OIDC_ACCEPTED_AUDIENCES=... uvicorn mcp_server:app --port 8300
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from crm_tools import TOOL_BY_NAME, Ctx, allowed_tools, load_context
from schema_check import validate_args

logger = logging.getLogger("svc-crm.mcp")

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = {"2025-06-18", "2025-03-26"}
SERVER_INFO = {"name": "svc-crm", "title": "CRM – Khách hàng", "version": "1.0.0"}
INSTRUCTIONS = ("Dữ liệu CRM: khách hàng, cơ hội bán hàng. Chỉ đọc; kết quả đã lọc theo quyền người hỏi "
                "(nhân viên kinh doanh chỉ thấy khách hàng mình phụ trách).")
MAX_BODY_BYTES = 64_000  # chặn request quá lớn
_jwt = JsonWebToken(["RS256"])  # CHỈ RS256 (SOPBase) – chặn alg=none / HS256 giả mạo


class Settings:
    """Đọc env mỗi lần truy cập (đơn giản cho mẫu; dự án thật dùng pydantic-settings như svc-hrm)."""

    @property
    def agent_token(self) -> str:  # token RIÊNG của nguồn này, đội nền tảng cấp (k8s Secret)
        return os.getenv("MCP_AGENT_TOKEN", "")

    @property
    def issuer(self) -> str:
        return os.getenv("OIDC_ISSUER", "https://sopbase.digigov.vn/auth")

    @property
    def jwks_url(self) -> str:
        return os.getenv("OIDC_JWKS_URL", "https://sopbase.digigov.vn/auth/jwks")

    @property
    def audiences(self) -> list[str]:
        # Client SOPBase mà token NGƯỜI HỎI được cấp cho (web HRM, mobile HRM…) – KHÁC client của phân hệ!
        return [a.strip() for a in os.getenv("OIDC_ACCEPTED_AUDIENCES", "").split(",") if a.strip()]


settings = Settings()


# ───────────────────────────── JWT (SOPBase) ─────────────────────────────
_jwks_cache: dict[str, Any] = {"at": 0.0, "keys": None}
JWKS_TTL = 3600


async def _fetch_jwks() -> dict:
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
        resp = await client.get(settings.jwks_url)
        resp.raise_for_status()
        return resp.json()


async def _key_set(force: bool = False):
    now = time.monotonic()
    if force or _jwks_cache["keys"] is None or now - _jwks_cache["at"] > JWKS_TTL:
        _jwks_cache["keys"] = JsonWebKey.import_key_set(await _fetch_jwks())
        _jwks_cache["at"] = now
    return _jwks_cache["keys"]


class AuthError(Exception):
    pass


async def verify_user_jwt(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("missing_bearer")
    token = authorization[7:].strip()
    if not settings.audiences:
        raise AuthError("audience_not_configured")  # fail-closed: chưa cấu hình aud = không nhận ai
    options = {
        "iss": {"essential": True, "value": settings.issuer},
        "exp": {"essential": True},
        "sub": {"essential": True},
        "aud": {"essential": True, "values": settings.audiences},
    }
    for attempt in (0, 1):
        try:
            claims = _jwt.decode(token, await _key_set(force=attempt == 1), claims_options=options)
            claims.validate(leeway=30)
            return dict(claims)
        except JoseError as exc:  # chữ ký sai, hết hạn, sai iss/aud → từ chối ngay
            raise AuthError(type(exc).__name__) from exc
        except ValueError as exc:  # không tìm thấy kid (SOPBase vừa xoay khoá) / token hỏng → nạp lại JWKS 1 lần
            if attempt == 1:
                raise AuthError("invalid_token") from exc
    raise AuthError("invalid_token")


# ───────────────────────────── JSON-RPC ─────────────────────────────
def _ok(rid, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _tool_result(data: dict) -> dict:
    is_error = isinstance(data, dict) and "error" in data
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, default=str)}],
            "structuredContent": data, "isError": is_error}


def call_tool(ctx: Ctx, name: str, args: dict) -> dict:
    tool = TOOL_BY_NAME.get(name)
    if tool is None or tool not in allowed_tools(ctx):  # kiểm quyền LẦN 2 – không tin việc tools/list đã lọc
        return {"error": "not_permitted_or_unknown_tool"}
    try:
        clean = validate_args(tool.input_schema, args)
    except ValueError as exc:
        return {"error": "invalid_arguments", "message": str(exc)}
    try:
        return tool.handler(ctx, clean)
    except Exception:  # không trả stacktrace / dữ liệu nội bộ cho model
        logger.exception("tool failed: %s", name)
        return {"error": "internal_error", "message": "Công cụ tạm thời lỗi, vui lòng thử lại sau"}


def handle(ctx: Ctx, message: dict) -> dict | None:
    if message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _err(message.get("id"), -32600, "Invalid Request")
    rid, method, params = message.get("id"), message["method"], message.get("params") or {}
    if rid is None:  # notification (notifications/initialized…) → không trả lời
        return None
    if not isinstance(params, dict):
        return _err(rid, -32602, "params phải là object")
    if method == "initialize":
        asked = str(params.get("protocolVersion") or PROTOCOL_VERSION)
        return _ok(rid, {"protocolVersion": asked if asked in SUPPORTED_VERSIONS else PROTOCOL_VERSION,
                         "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS})
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": [t.descriptor() for t in allowed_tools(ctx)]})
    if method == "tools/call":
        name, args = str(params.get("name") or ""), params.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return _err(rid, -32602, "arguments phải là object")
        started = time.perf_counter()
        result = call_tool(ctx, name, args)
        # Audit: ai, công cụ, tenant, kết quả, thời gian – KHÔNG log arguments/kết quả (có thể chứa dữ liệu cá nhân)
        logger.info("mcp tools/call tool=%s user=%s tenant=%s ok=%s ms=%d", name, ctx.email, ctx.tenant,
                    "error" not in result, int((time.perf_counter() - started) * 1000))
        return _ok(rid, _tool_result(result))
    return _err(rid, -32601, f"Method không hỗ trợ: {method}")


# ───────────────────────────── HTTP ─────────────────────────────
app = FastAPI(title="svc-crm MCP (mẫu)", docs_url=None, redoc_url=None, openapi_url=None)


def _http_error(status: int, error: str, message: str) -> JSONResponse:
    headers = {"WWW-Authenticate": f'Bearer error="{error}"'} if status == 401 else None
    return JSONResponse(status_code=status, content={"error": error, "message": message}, headers=headers)


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    # 1) Chỉ svc-agent
    expected, given = settings.agent_token, request.headers.get("X-Agent-Token") or ""
    if not expected:
        return _http_error(503, "mcp_disabled", "MCP chưa bật (thiếu MCP_AGENT_TOKEN)")
    if not hmac.compare_digest(expected.encode(), given.encode()):
        return _http_error(401, "invalid_agent_token", "X-Agent-Token không hợp lệ")
    # 2) Người hỏi (JWT SOPBase)
    try:
        claims = await verify_user_jwt(request.headers.get("Authorization"))
    except AuthError as exc:
        logger.warning("mcp auth failed: %s", exc)  # KHÔNG log token
        return _http_error(401, "invalid_token", "Token người dùng không hợp lệ hoặc hết hạn")
    # 3) Tenant – người dùng phải là thành viên
    tenant = (request.headers.get("tenant-id") or "").strip()
    if not tenant or len(tenant) > 64:
        return _http_error(400, "tenant_required", "Thiếu header tenant-id")
    ctx = load_context(claims, tenant)
    if ctx is None:
        return _http_error(403, "forbidden", "Người dùng không thuộc tenant này")
    # 4) JSON-RPC
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content=_err(None, -32600, "Request quá lớn"))
    try:
        payload = json.loads(body)
    except ValueError:
        return JSONResponse(status_code=400, content=_err(None, -32700, "Parse error"))
    if isinstance(payload, list):  # batch (tối đa 20)
        out = [r for r in (handle(ctx, m) if isinstance(m, dict) else _err(None, -32600, "Invalid Request")
                           for m in payload[:20]) if r is not None]
        return JSONResponse(out) if out else Response(status_code=202)
    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content=_err(None, -32600, "Invalid Request"))
    res = handle(ctx, payload)
    return Response(status_code=202) if res is None else JSONResponse(res)


@app.get("/mcp")
async def mcp_get():
    # Không mở luồng SSE do server khởi tạo – spec cho phép trả 405
    return Response(status_code=405, headers={"Allow": "POST"})


@app.get("/health")
async def health():
    return {"status": "ok"}

