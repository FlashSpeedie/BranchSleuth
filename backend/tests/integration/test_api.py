import uuid

from app.db.models import AnalysisRun, Repository, RunStatus
from tests.conftest import ensure_workspace
from tests.fixture_builder import build_snapshot_pair


def _make_local_repo(db, tmp_path):
    ws = ensure_workspace(db)
    repo = Repository(name="tinyshop", source_type="local", local_path=str(tmp_path), workspace_id=ws.id)
    db.add(repo)
    db.commit()
    return repo


def _create_run(client, repo_id, **overrides):
    payload = {"repository_id": str(repo_id), "baseline_ref": None, "target_ref": None}
    payload.update(overrides)
    return client.post("/api/v1/analyses", json=payload)


def test_create_and_get_analysis(api_client, sqlite_db, tmp_path):
    with sqlite_db() as db:
        repo = _make_local_repo(db, tmp_path)
        repo_id = repo.id
    resp = _create_run(api_client, repo_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    run_id = body["id"]
    got = api_client.get(f"/api/v1/analyses/{run_id}")
    assert got.status_code == 200
    assert got.json()["stage"] == "queued"


def test_duplicate_active_analysis_rejected(api_client, sqlite_db, tmp_path):
    with sqlite_db() as db:
        repo = _make_local_repo(db, tmp_path)
    first = _create_run(api_client, repo.id)
    assert first.status_code == 201
    second = _create_run(api_client, repo.id)
    assert second.status_code == 409
    assert "already in progress" in second.json()["detail"]


def test_cancel_queued_then_retry(api_client, sqlite_db, tmp_path):
    with sqlite_db() as db:
        repo = _make_local_repo(db, tmp_path)
    created = _create_run(api_client, repo.id).json()
    run_id = created["id"]
    cancel = api_client.post(f"/api/v1/analyses/{run_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    again = api_client.post(f"/api/v1/analyses/{run_id}/cancel")
    assert again.status_code == 409
    retry = api_client.post(f"/api/v1/analyses/{run_id}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "queued"
    with sqlite_db() as db:
        run = db.get(AnalysisRun, uuid.UUID(run_id))
        assert run.status == RunStatus.QUEUED.value


def test_retry_completed_rejected(api_client, sqlite_db, tmp_path):
    with sqlite_db() as db:
        repo = _make_local_repo(db, tmp_path)
    created = _create_run(api_client, repo.id).json()
    run_id = uuid.UUID(created["id"])
    with sqlite_db() as db:
        run = db.get(AnalysisRun, run_id)
        run.status = RunStatus.COMPLETED.value
        db.add(run)
        db.commit()
    resp = api_client.post(f"/api/v1/analyses/{created['id']}/retry")
    assert resp.status_code == 409


def test_repository_local_path_validation(api_client, sqlite_db, tmp_path):
    resp = api_client.post(
        "/api/v1/repositories",
        json={"name": "missing", "local_path": str(tmp_path / "nope")},
    )
    assert resp.status_code == 422
    not_git = tmp_path / "plain"
    not_git.mkdir()
    resp = api_client.post(
        "/api/v1/repositories",
        json={"name": "plain", "local_path": str(not_git)},
    )
    assert resp.status_code == 422
    assert "not a git repository" in resp.json()["detail"]


def test_repository_url_validation(api_client, sqlite_db):
    resp = api_client.post(
        "/api/v1/repositories",
        json={"name": "bad", "git_url": "http://github.com/a/b"},
    )
    assert resp.status_code == 422
    resp = api_client.post(
        "/api/v1/repositories",
        json={"name": "bad", "git_url": "https://evil.example/a/b"},
    )
    assert resp.status_code == 422


def test_repository_requires_source(api_client, sqlite_db):
    resp = api_client.post("/api/v1/repositories", json={"name": "empty"})
    assert resp.status_code == 422


def test_upload_repository_flow(api_client, sqlite_db, tmp_path, data_dir):
    import io
    import zipfile

    baseline, modified = build_snapshot_pair(tmp_path)
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as zf:
        for path in sorted(baseline.rglob("*")):
            if path.is_file():
                zf.write(path, f"tinyshop/{path.relative_to(baseline).as_posix()}")
    zbuf.seek(0)
    resp = api_client.post(
        "/api/v1/repositories/upload",
        files={"file": ("repo.zip", zbuf.read(), "application/zip")},
        data={"name": "uploaded"},
    )
    assert resp.status_code == 201, resp.text
    repo = resp.json()
    assert repo["source_type"] == "upload"
    assert repo["snapshot_count"] == 1

    zbuf2 = io.BytesIO()
    with zipfile.ZipFile(zbuf2, "w") as zf:
        for path in sorted(modified.rglob("*")):
            if path.is_file():
                zf.write(path, f"tinyshop/{path.relative_to(modified).as_posix()}")
    resp2 = api_client.post(
        f"/api/v1/repositories/{repo['id']}/snapshots",
        files={"file": ("repo2.zip", zbuf2.getvalue(), "application/zip")},
    )
    assert resp2.status_code == 201, resp2.text
    refs = api_client.get(f"/api/v1/repositories/{repo['id']}/refs").json()
    assert [r["name"] for r in refs] == ["snapshot-1", "snapshot-2"]

    run = _create_run(api_client, repo["id"])
    assert run.status_code == 201
    assert run.json()["repository_name"] == "uploaded"


def test_api_key_enforced(api_client, sqlite_db, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_key", "test-secret-key")
    with sqlite_db() as db:
        _make_local_repo(db, tmp_path)
    resp = api_client.get("/api/v1/repositories")
    assert resp.status_code == 401
    resp = api_client.get("/api/v1/repositories", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401
    resp = api_client.get("/api/v1/repositories", headers={"X-API-Key": "test-secret-key"})
    assert resp.status_code == 200
    resp = api_client.get(
        "/api/v1/repositories",
        headers={"Authorization": "Bearer test-secret-key"},
    )
    assert resp.status_code == 200
    monkeypatch.setattr(settings, "api_key", "")


def test_health_and_readiness(api_client, sqlite_db):
    health = api_client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    ready = api_client.get("/api/v1/ready")
    assert ready.status_code == 200
    body = ready.json()
    assert body["database"] == "connected"
    assert body["docker"] in ("available", "unavailable", "unconfigured")


def test_secrets_never_in_responses(api_client, sqlite_db, tmp_path):
    with sqlite_db() as db:
        _make_local_repo(db, tmp_path)
    resp = api_client.get("/api/v1/repositories")
    text = resp.text
    for leak in ("postgres://", "npg_", "DATABASE_URL"):
        assert leak not in text
