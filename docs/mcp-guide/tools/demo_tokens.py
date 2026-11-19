#!/usr/bin/env python3
"""Sinh JWKS + JWT thử cho môi trường DEV (không dùng SOPBase thật) – phục vụ chạy mcp-check với server mẫu.

  python demo_tokens.py /tmp/mcp-demo        → ghi jwks.json, token_sale1.txt, token_guest.txt, token_manager.txt
  python -m http.server 8399 -d /tmp/mcp-demo → phục vụ JWKS tại http://127.0.0.1:8399/jwks.json
Server mẫu: OIDC_JWKS_URL=http://127.0.0.1:8399/jwks.json OIDC_ISSUER=https://sopbase.test/auth
            OIDC_ACCEPTED_AUDIENCES=hrm-web-client MCP_AGENT_TOKEN=dev-agent-token
KHÔNG dùng cho production.
"""
import json
import sys
import time
from pathlib import Path

from authlib.jose import JsonWebKey, jwt

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/mcp-demo")
out.mkdir(parents=True, exist_ok=True)
key = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "dev-kid"})
(out / "jwks.json").write_text(json.dumps({"keys": [key.as_dict(is_private=False)]}))
now = int(time.time())
for email in ("sale1@test.com", "guest@test.com", "manager@test.com"):
    claims = {"sub": "11111111-1111-1111-1111-111111111111", "email": email, "iss": "https://sopbase.test/auth",
              "aud": "hrm-web-client", "iat": now, "exp": now + 3600}
    (out / f"token_{email.split('@')[0]}.txt").write_text(jwt.encode({"alg": "RS256", "kid": "dev-kid"}, claims, key).decode())
print(f"Đã ghi JWKS + token vào {out}")
