"""Quyền mcp:<nguồn>:<công cụ> / wf:<workflow>:<hành động> do HRM quản lý (gán vào role ở màn Phân quyền vai trò).

Khớp wildcard giống svc-hrm app/shared/rbac.py: `*`, `mcp:*`, `mcp:crm:*`, `mcp:crm:crm_search_customers`.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

PERM_RE = re.compile(r"^(\*|(mcp|wf)(:[A-Za-z0-9_*-]{1,64}){0,2})$")


def clean(raw: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({p.strip() for p in raw if p and PERM_RE.match(p.strip())}))[:500]


def _candidates(required: str) -> set[str]:
    parts = required.split(":")
    out = {"*"}
    for i in range(1, len(parts) + 1):
        prefix = ":".join(parts[:i])
        out.add(prefix)
        out.add(prefix + ":*" if i < len(parts) else prefix)
    out.add(f"{parts[0]}:*")
    return out


def has(perms: Iterable[str], required: str) -> bool:
    return bool(_candidates(required) & set(perms))


def can_use_source(perms: Iterable[str], server: str) -> bool:
    """Có quyền ít nhất 1 công cụ của nguồn (mcp:<server>:* hoặc mcp:<server>:<tool> bất kỳ)."""
    p = set(perms)
    return bool({"*", "mcp", "mcp:*", f"mcp:{server}", f"mcp:{server}:*"} & p) or any(x.startswith(f"mcp:{server}:") for x in p)


def can_use_tool(perms: Iterable[str], server: str, tool: str) -> bool:
    return has(perms, f"mcp:{server}:{tool}")
