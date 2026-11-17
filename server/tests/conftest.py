import os
import sys

import pytest

os.environ.setdefault("EXCHANGE_DB", ":memory:")
os.environ.setdefault("EXCHANGE_RUN_SIM", "false")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def app():
    config = Settings(db_path=":memory:", run_simulation=False)
    return create_app(config)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def trader(client):
    def make(name):
        response = client.post("/api/register", json={"name": name})
        assert response.status_code == 200
        return {"X-API-Key": response.json()["api_key"]}
    return make
