"""Pydantic model của định dạng flow `dns.agent-flow/v1` (lưu JSON, editor web đọc/ghi đúng cấu trúc này)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ID = r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"


class Position(BaseModel):
    x: float = Field(ge=-100000, le=100000)
    y: float = Field(ge=-100000, le=100000)


class FlowNode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=ID)
    kind: str = Field(max_length=60)
    name: str = Field(default="", max_length=80)
    position: Position = Field(default_factory=lambda: Position(x=0, y=0))
    disabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class Endpoint(BaseModel):
    node: str = Field(pattern=ID)
    port: str = Field(max_length=30)


class FlowEdge(BaseModel):
    id: str = Field(pattern=ID)
    source: Endpoint
    target: Endpoint


class FlowViewport(BaseModel):
    x: float = 0
    y: float = 0
    zoom: float = Field(default=1, ge=0.1, le=4)


class FlowDocument(BaseModel):
    """Toàn bộ tài liệu flow. `nodes`/`edges` giới hạn số lượng để tránh payload lớn bất thường."""

    model_config = ConfigDict(extra="ignore")

    format: Literal["dns.agent-flow/v1"] = "dns.agent-flow/v1"
    name: str = Field(default="Trợ lý", max_length=120)
    description: str = Field(default="", max_length=500)
    nodes: list[FlowNode] = Field(default_factory=list, max_length=60)
    edges: list[FlowEdge] = Field(default_factory=list, max_length=200)
    viewport: FlowViewport = Field(default_factory=FlowViewport)
