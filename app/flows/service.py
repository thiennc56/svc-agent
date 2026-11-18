"""Lưu / đọc / kích hoạt flow. Chưa có bản lưu nào → dùng flow mặc định (default_flow) – chatbot chạy ngay."""
from __future__ import annotations

import copy

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.flows.compiler import CompileResult, compile_flow
from app.flows.defaults import default_flow
from app.flows.models import AgentFlowVersion

SECRET_MASK = "********"
SECRET_FIELDS = ("apiKey",)
KEEP_VERSIONS = 50


def mask_secrets(doc: dict) -> dict:
    """Không bao giờ trả API key trong flow về trình duyệt."""
    out = copy.deepcopy(doc)
    for n in out.get("nodes") or []:
        cfg = n.get("config") or {}
        for f in SECRET_FIELDS:
            if cfg.get(f):
                cfg[f] = SECRET_MASK
    return out


def merge_secrets(incoming: dict, current: dict | None) -> dict:
    """'********' = giữ secret đang lưu của node cùng id; '' = xoá."""
    old = {n.get("id"): (n.get("config") or {}) for n in ((current or {}).get("nodes") or [])}
    out = copy.deepcopy(incoming)
    for n in out.get("nodes") or []:
        cfg = n.setdefault("config", {})
        for f in SECRET_FIELDS:
            if cfg.get(f) == SECRET_MASK:
                kept = old.get(n.get("id"), {}).get(f)
                if kept:
                    cfg[f] = kept
                else:
                    cfg.pop(f, None)
    return out


class FlowService:
    def __init__(self, db: Session):
        self.db = db

    def _q(self, app: str, tenant: str):
        return self.db.query(AgentFlowVersion).filter(AgentFlowVersion.app == app, AgentFlowVersion.tenant_id == tenant)

    def active(self, app: str, tenant: str) -> AgentFlowVersion | None:
        return self._q(app, tenant).filter(AgentFlowVersion.is_active.is_(True)).order_by(AgentFlowVersion.version.desc()).first()

    def active_document(self, app: str, tenant: str) -> tuple[dict, int | None]:
        """(document, version) – version None = flow mặc định chưa lưu."""
        row = self.active(app, tenant)
        return (row.document, row.version) if row else (default_flow(app), None)

    def versions(self, app: str, tenant: str, limit: int = 30) -> list[AgentFlowVersion]:
        return self._q(app, tenant).order_by(AgentFlowVersion.version.desc()).limit(limit).all()

    def get_version(self, app: str, tenant: str, version: int) -> AgentFlowVersion:
        row = self._q(app, tenant).filter(AgentFlowVersion.version == version).first()
        if not row:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiên bản flow")
        return row

    def save(self, app: str, tenant: str, document: dict, actor: str, note: str | None = None) -> tuple[AgentFlowVersion, CompileResult]:
        current = self.active(app, tenant)
        doc = merge_secrets(document, current.document if current else None)
        result = compile_flow(doc, app)
        if not result.ok:
            raise HTTPException(status_code=422, detail={"message": "Flow chưa hợp lệ", **result.report()})
        doc = result_document(doc)
        next_version = (self._q(app, tenant).with_entities(func.max(AgentFlowVersion.version)).scalar() or 0) + 1
        self._q(app, tenant).filter(AgentFlowVersion.is_active.is_(True)).update({AgentFlowVersion.is_active: False})
        row = AgentFlowVersion(app=app, tenant_id=tenant, version=next_version, document=doc, is_active=True,
                               note=(note or "")[:300] or None, created_by=actor)
        self.db.add(row)
        self.db.commit()
        self._prune(app, tenant)
        return row, result

    def activate(self, app: str, tenant: str, version: int, actor: str) -> AgentFlowVersion:
        """Khôi phục: sao chép phiên bản cũ thành phiên bản mới (giữ lịch sử tuyến tính)."""
        old = self.get_version(app, tenant, version)
        row, _ = self.save(app, tenant, old.document, actor, note=f"Khôi phục từ v{version}")
        return row

    def reset(self, app: str, tenant: str, actor: str) -> AgentFlowVersion:
        row, _ = self.save(app, tenant, default_flow(app), actor, note="Khôi phục flow mặc định")
        return row

    def _prune(self, app: str, tenant: str) -> None:
        old = self._q(app, tenant).order_by(AgentFlowVersion.version.desc()).offset(KEEP_VERSIONS).all()
        for row in old:
            self.db.delete(row)
        if old:
            self.db.commit()


def result_document(doc: dict) -> dict:
    """Chuẩn hoá tài liệu đã validate (bỏ field lạ, điền format) trước khi lưu."""
    from app.flows.schema import FlowDocument

    return FlowDocument.model_validate(doc).model_dump(mode="json")
