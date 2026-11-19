"""Verify X-Agent-Context (signed_context) – JWT RS256 do svc-agent ký cho MỖI lời gọi /mcp (giai đoạn C, hướng dẫn v1.2).

Khuyến nghị dùng thay cho chuyển tiếp JWT SOPBase vì:
  - aud = mã nguồn của CHÍNH phân hệ (crm) → token không dùng lại được ở phân hệ khác;
  - có cả bot tự động (act="service") – bot không có JWT SOPBase;
  - permissions = quyền mcp:<nguồn>:* HRM đã cấp cho người hỏi (thông tin bổ sung, phân hệ vẫn tự kiểm RBAC của mình).

Biến môi trường:
  AGENT_ISSUER     https://hrmapi.digigov.vn/agent      (dev: http://127.0.0.1:8100)
  AGENT_JWKS_URL   http://svc-agent.hrm-platform.svc.cluster.local:8000/.well-known/jwks.json  (trong cụm)
  MCP_SOURCE_KEY   crm                                   (= mã nguồn quản trị nền tảng đặt trên HRM)
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from authlib.jose.errors import JoseError

_jwt = JsonWebToken(["RS256"])
_cache: dict[str, Any] = {"at": 0.0, "keys": None}
JWKS_TTL = 3600


class ContextError(Exception):
    pass


def configured() -> bool:
    return bool(os.getenv("AGENT_JWKS_URL") and os.getenv("MCP_SOURCE_KEY") and os.getenv("AGENT_ISSUER"))


async def _fetch() -> dict:
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
        resp = await client.get(os.environ["AGENT_JWKS_URL"])
        resp.raise_for_status()
        return resp.json()


async def _keys(force: bool = False):
    now = time.monotonic()
    if force or _cache["keys"] is None or now - _cache["at"] > JWKS_TTL:
        _cache["keys"] = JsonWebKey.import_key_set(await _fetch())
        _cache["at"] = now
    return _cache["keys"]


async def verify(token: str | None) -> dict:
    """→ claims {sub, email, name, tenant, app, act: user|service, permissions[]}. Sai/hết hạn → ContextError."""
    if not token:
        raise ContextError("missing_context")
    options = {"iss": {"essential": True, "value": os.environ["AGENT_ISSUER"].rstrip("/")},
               "aud": {"essential": True, "values": [os.environ["MCP_SOURCE_KEY"]]},
               "exp": {"essential": True}, "tenant": {"essential": True}}
    for attempt in (0, 1):
        try:
            claims = _jwt.decode(token, await _keys(force=attempt == 1), claims_options=options)
            claims.validate(leeway=10)
            return dict(claims)
        except JoseError as exc:
            raise ContextError(type(exc).__name__) from exc
        except ValueError as exc:  # kid lạ (svc-agent xoay khoá) → nạp lại JWKS 1 lần
            if attempt == 1:
                raise ContextError("invalid_context") from exc
    raise ContextError("invalid_context")
