"""Kiểm tham số công cụ theo inputSchema (tập con JSON Schema đủ dùng, không phụ thuộc thư viện).

Dự án thật có thể dùng `jsonschema` (Python) / `ajv` (Node). Quy tắc: KHÔNG tin arguments do model sinh ra –
luôn kiểm kiểu, độ dài, pattern, enum, khoảng giá trị, và từ chối tham số lạ (additionalProperties=false).
"""
from __future__ import annotations

import re

_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def validate_args(schema: dict, args: dict) -> dict:
    """Trả args đã điền default; ValueError (thông điệp an toàn để trả cho model) nếu sai."""
    props = schema.get("properties") or {}
    for req in schema.get("required") or []:
        if req not in args:
            raise ValueError(f"thiếu tham số '{req}'")
    if schema.get("additionalProperties") is False:
        extra = set(args) - set(props)
        if extra:
            raise ValueError(f"tham số không hỗ trợ: {', '.join(sorted(extra))}")
    out = dict(args)
    for key, spec in props.items():
        if key not in out:
            if "default" in spec:
                out[key] = spec["default"]
            continue
        val, typ = out[key], spec.get("type")
        if typ and (not isinstance(val, _TYPES[typ]) or (typ in ("integer", "number") and isinstance(val, bool))):
            raise ValueError(f"'{key}' phải là {typ}")
        if isinstance(val, str):
            if len(val) < spec.get("minLength", 0) or len(val) > spec.get("maxLength", 10_000):
                raise ValueError(f"'{key}' độ dài không hợp lệ")
            if spec.get("pattern") and not re.fullmatch(spec["pattern"], val):
                raise ValueError(f"'{key}' sai định dạng")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if val < spec.get("minimum", float("-inf")) or val > spec.get("maximum", float("inf")):
                raise ValueError(f"'{key}' ngoài khoảng cho phép")
        if "enum" in spec and val not in spec["enum"]:
            raise ValueError(f"'{key}' phải thuộc {spec['enum']}")
    return out
