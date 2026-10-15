from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("BS_DATA_DIR", "./data-test")
os.environ.setdefault("BS_ALLOW_LOCAL_REPOS", "true")
os.environ.setdefault("DATABASE_URL", "sqlite://")

from app.config import settings  # noqa: E402

settings.data_dir = "./data-test"
settings.allow_local_repos = True
settings.api_key = ""

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402


@pytest.fixture()
def sqlite_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    yield factory
    engine.dispose()


def ensure_workspace(db) -> "object":
    from app.db.models import Workspace

    ws = db.query(Workspace).filter(Workspace.name == "default").first()
    if ws is None:
        ws = Workspace(name="default")
        db.add(ws)
        db.commit()
    return ws


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture()
def api_client(sqlite_db, monkeypatch):
    from fastapi.testclient import TestClient

    import app.api.deps as deps
    from app.main import app

    def override_get_session():
        db = sqlite_db()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(deps, "get_session", override_get_session)
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()
