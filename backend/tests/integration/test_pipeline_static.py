from pathlib import Path

import pytest

from app.config import settings
from app.db.models import AnalysisRun, Repository, RepoSnapshot, RunStatus
from app.engine.pipeline import execute_analysis
from tests.conftest import ensure_workspace
from tests.fixture_builder import build_snapshot_pair

PROPERTY_CODE = """import math

def check(kwargs, outcome):
    subtotal = kwargs["subtotal"]
    if outcome["kind"] != "return":
        return False
    value = outcome["value"]
    if subtotal <= 100:
        return value == subtotal
    return math.isclose(value, subtotal * 0.9, rel_tol=1e-9)
"""


def _seed_upload_repo(db, tmp_path):
    ws = ensure_workspace(db)
    baseline, modified = build_snapshot_pair(tmp_path / "sources")
    repo = Repository(name="tinyshop", source_type="upload", workspace_id=ws.id)
    db.add(repo)
    db.flush()
    db.add(RepoSnapshot(repository_id=repo.id, label="snapshot-1", storage_path=str(baseline), file_count=5))
    db.add(RepoSnapshot(repository_id=repo.id, label="snapshot-2", storage_path=str(modified), file_count=5))
    db.commit()
    return repo


@pytest.fixture()
def no_docker(monkeypatch):
    from app.worker_runtime import docker_worker

    class UnavailableSession:
        def __init__(self, run_key):
            raise docker_worker.WorkerUnavailable("Docker daemon not reachable (test override)")

    monkeypatch.setattr(docker_worker, "WorkerSession", UnavailableSession)


def test_static_pipeline_without_docker(sqlite_db, tmp_path, data_dir, no_docker):
    with sqlite_db() as db:
        repo = _seed_upload_repo(db, tmp_path)
        run = AnalysisRun(
            repository_id=repo.id,
            baseline_ref="snapshot-1",
            target_ref="snapshot-2",
            options={"property_code": PROPERTY_CODE, "property_target": "tinyshop/pricing.py::apply_discount"},
        )
        db.add(run)
        db.commit()
        run_id = run.id

    execute_analysis(run_id, sqlite_db)

    with sqlite_db() as db:
        run = db.get(AnalysisRun, run_id)
        assert run.status == RunStatus.COMPLETED.value, run.error_message
        assert run.resolved_baseline_sha == "upload-snapshot-1"
        assert run.resolved_target_sha == "upload-snapshot-2"
        summary = run.summary
        assert summary["changed_files"] == 1
        assert summary["runtime_status"] == "unavailable"
        assert summary["tests"]["count"] == 0

        from app.db.models import ChangedFile, ChangedScope

        files = db.query(ChangedFile).filter(ChangedFile.run_id == run_id).all()
        assert len(files) == 1
        f = files[0]
        assert f.path == "tinyshop/pricing.py"
        assert f.change_type == "modified"
        assert 6 in f.added_lines and 6 in f.removed_lines
        scopes = db.query(ChangedScope).filter(ChangedScope.run_id == run_id).all()
        assert len(scopes) == 1
        assert scopes[0].qualname == "apply_discount"
        assert scopes[0].changed_lines == [6]
        assert scopes[0].coverage_status == "COVERAGE_UNAVAILABLE"
        diff_artifact = Path(settings.data_path()) / "artifacts" / str(run_id) / "unified.diff"
        assert diff_artifact.exists()
        diff_text = diff_artifact.read_text()
        assert "-    if subtotal > 100:" in diff_text
        assert "+    if subtotal >= 100:" in diff_text


def test_pipeline_invalid_snapshot_refs_fail(sqlite_db, tmp_path, data_dir, no_docker):
    with sqlite_db() as db:
        repo = _seed_upload_repo(db, tmp_path)
        run = AnalysisRun(repository_id=repo.id, baseline_ref="snapshot-1", target_ref="snapshot-1")
        db.add(run)
        db.commit()
        run_id = run.id
    execute_analysis(run_id, sqlite_db)
    with sqlite_db() as db:
        run = db.get(AnalysisRun, run_id)
        assert run.status == RunStatus.FAILED.value
        assert "must differ" in run.error_message


def test_pipeline_single_snapshot_fails_cleanly(sqlite_db, tmp_path, data_dir, no_docker):
    baseline, _ = build_snapshot_pair(tmp_path / "solo")
    with sqlite_db() as db:
        ws = ensure_workspace(db)
        repo = Repository(name="one-snap", source_type="upload", workspace_id=ws.id)
        db.add(repo)
        db.flush()
        db.add(RepoSnapshot(repository_id=repo.id, label="snapshot-1", storage_path=str(baseline), file_count=5))
        db.add(AnalysisRun(repository_id=repo.id))
        db.commit()
        run_id = db.query(AnalysisRun).first().id
    execute_analysis(run_id, sqlite_db)
    with sqlite_db() as db:
        run = db.get(AnalysisRun, run_id)
        assert run.status == RunStatus.FAILED.value
        assert "two snapshots" in run.error_message
