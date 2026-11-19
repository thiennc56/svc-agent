"""signed_context – svc-agent ký JWT ngắn hạn mô tả "ai đang hỏi" gửi tới MCP server của phân hệ.

Thay cho chuyển tiếp JWT SOPBase của người dùng (MCP spec cấm token passthrough). Phân hệ verify bằng JWKS công khai
`{AGENT_ISSUER}/.well-known/jwks.json`, kiểm `iss`, `aud` (= mã nguồn của chính nó), `exp`.

Khoá: AGENT_SIGNING_KEY (PEM RSA, k8s Secret). Dev không có khoá → tự sinh 1 lần, lưu `.dev-signing-key.pem` (git-ignored).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import time
import uuid
from functools import lru_cache
from pathlib import Path

from authlib.jose import JsonWebKey, jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.config import settings

logger = logging.getLogger(__name__)
DEV_KEY_FILE = Path(__file__).resolve().parents[2] / ".dev-signing-key.pem"


class SigningKeyMissing(RuntimeError):
    pass


def _pem() -> bytes:
    if settings.agent_signing_key.strip():
        return settings.agent_signing_key.strip().replace("\\n", "\n").encode()
    if not settings.is_dev:
        raise SigningKeyMissing("Chưa cấu hình AGENT_SIGNING_KEY (k8s Secret) – không ký được signed_context")
    if not DEV_KEY_FILE.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        DEV_KEY_FILE.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                   serialization.NoEncryption()))
        DEV_KEY_FILE.chmod(0o600)
        logger.warning("dev: tạo khoá ký signed_context tại %s", DEV_KEY_FILE)
    return DEV_KEY_FILE.read_bytes()


@lru_cache(maxsize=1)
def _keys() -> tuple[object, dict]:
    private = JsonWebKey.import_key(_pem(), {"kty": "RSA"})
    public = private.as_dict(is_private=False)
    thumb = hashlib.sha256(f'{{"e":"{public["e"]}","kty":"RSA","n":"{public["n"]}"}}'.encode()).digest()
    kid = base64.urlsafe_b64encode(thumb).rstrip(b"=").decode()[:22]
    public.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private, public


def jwks() -> dict:
    return {"keys": [_keys()[1]]}


def issuer() -> str:
    return settings.agent_issuer.rstrip("/")


def sign_context(audience: str, *, sub: str, email: str, tenant: str, app: str, act: str = "user", name: str = "",
                 permissions: list[str] | tuple[str, ...] = ()) -> str:
    """JWT RS256, sống CONTEXT_TTL_SECONDS. `permissions` chỉ gồm quyền mcp:<audience>:* liên quan nguồn đích."""
    private, public = _keys()
    now = int(time.time())
    own = [p for p in permissions if p in ("*", "mcp:*") or p.startswith(f"mcp:{audience}:")]
    claims = {"iss": issuer(), "aud": [audience], "sub": sub or email, "email": email, "name": name[:160],
              "tenant": tenant, "app": app, "act": act, "permissions": own,
              "iat": now, "nbf": now - 5, "exp": now + settings.context_ttl_seconds, "jti": uuid.uuid4().hex}
    token = jwt.encode({"alg": "RS256", "kid": public["kid"], "typ": "JWT"}, claims, private)
    return token.decode() if isinstance(token, bytes) else str(token)
