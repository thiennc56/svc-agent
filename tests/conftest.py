import os

# Phải đặt trước khi import app (Settings đọc env lúc import)
os.environ["APP_ENV"] = "test"
os.environ["DB_URL"] = "sqlite://"
os.environ["SERVICE_TOKENS"] = '{"hrm": "tok-hrm", "erp": "tok-erp"}'
os.environ["MCP_SERVERS"] = (
    '{"hrm": {"url": "http://svc-hrm.test/mcp", "title": "HRM – Nhân sự", "apps": ["hrm"]},'
    ' "kho": {"url": "http://svc-kho.test/mcp", "title": "Kho", "apps": ["erp"]}}'
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, engine  # noqa: E402
import app.flows.models  # noqa: E402,F401

HEADERS = {
    "X-Service-Token": "tok-hrm",
    "X-User-Authorization": "Bearer user-jwt",
    "X-Tenant-Id": "00000000-0000-0000-0000-000000000010",
    "X-User-Id": "u1",
    "X-User-Email": "admin@test.vn",
}


@pytest.fixture(autouse=True)
def _db():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)
