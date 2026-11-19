"""Mã hoá token nguồn MCP (Fernet = AES-128-CBC + HMAC-SHA256). Khoá dẫn xuất SHA-256 từ CREDENTIAL_KEY."""
from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_DEV_KEY = "svc-agent-dev-only-credential-key"


class CredentialKeyMissing(RuntimeError):
    pass


def _fernet() -> Fernet:
    raw = settings.credential_key or (_DEV_KEY if settings.is_dev else "")
    if not raw:
        raise CredentialKeyMissing("Chưa cấu hình CREDENTIAL_KEY (k8s Secret) – không lưu được token nguồn MCP")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))


def new_token() -> str:
    """Token 48 ký tự (URL-safe) cho X-Agent-Token."""
    return secrets.token_urlsafe(36)[:48]


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str:
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, CredentialKeyMissing):
        return ""
