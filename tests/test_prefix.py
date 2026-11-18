"""PATH_PREFIX: API mount dưới /agent (chung domain hrmapi qua ingress), health có ở cả gốc và prefix."""
import importlib

from fastapi.testclient import TestClient

from tests.conftest import HEADERS


def test_path_prefix(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "path_prefix", "agent/")
    import app.main as main

    main = importlib.reload(main)
    try:
        c = TestClient(main.app)
        assert c.get("/agent/v1/apps/hrm/flow", headers=HEADERS).status_code == 200
        assert c.get("/v1/apps/hrm/flow", headers=HEADERS).status_code == 404
        assert c.get("/health").status_code == 200 and c.get("/agent/health").status_code == 200
        assert c.get("/agent/openapi.json").status_code == 200
    finally:
        monkeypatch.setattr(settings, "path_prefix", "")
        importlib.reload(main)
