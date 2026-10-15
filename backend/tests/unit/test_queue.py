
from app.db.models import AnalysisRun, Repository, RunStatus
from app.jobs.queue import claim_next_job, clear_evidence_for_rerun, reclaim_abandoned_jobs
from app.config import settings
from datetime import timedelta
from app.db.models import utcnow


def _seed_runs(db, repo):
    queued = AnalysisRun(repository_id=repo.id, status=RunStatus.QUEUED.value)
    db.add(queued)
    db.commit()
    return queued


def _make_repo(db):
    from app.db.models import Workspace

    ws = db.query(Workspace).filter(Workspace.name == "default").first()
    if ws is None:
        ws = Workspace(name="default")
        db.add(ws)
        db.commit()
    repo = Repository(name="q", source_type="local", local_path="/tmp/x", workspace_id=ws.id)
    db.add(repo)
    db.commit()
    return repo


def test_claim_marks_preparing_and_increments_attempts(sqlite_db):
    with sqlite_db() as db:
        repo = _make_repo(db)
        run = _seed_runs(db, repo)
        assert run.attempts == 0
        claimed = claim_next_job(db, "worker-a")
        assert claimed == run.id
        db.refresh(run)
        assert run.status == RunStatus.PREPARING.value
        assert run.attempts == 1
        assert run.locked_by == "worker-a"
        again = claim_next_job(db, "worker-b")
        assert again is None


def test_reclaim_abandoned(sqlite_db, monkeypatch):
    monkeypatch.setattr(settings, "job_lease_seconds", 60)
    with sqlite_db() as db:
        repo = _make_repo(db)
        run = AnalysisRun(
            repository_id=repo.id,
            status=RunStatus.VERIFYING.value,
            locked_by="dead-worker",
            locked_at=utcnow() - timedelta(seconds=3600),
            attempts=1,
        )
        db.add(run)
        db.commit()
        reclaimed = reclaim_abandoned_jobs(db)
        assert reclaimed == 1
        db.refresh(run)
        assert run.status == RunStatus.QUEUED.value
        assert run.locked_by is None


def test_reclaim_respects_attempt_limit(sqlite_db, monkeypatch):
    monkeypatch.setattr(settings, "job_lease_seconds", 60)
    monkeypatch.setattr(settings, "max_job_attempts", 2)
    with sqlite_db() as db:
        repo = _make_repo(db)
        run = AnalysisRun(
            repository_id=repo.id,
            status=RunStatus.PREPARING.value,
            locked_by="dead-worker",
            locked_at=utcnow() - timedelta(seconds=3600),
            attempts=2,
        )
        db.add(run)
        db.commit()
        reclaim_abandoned_jobs(db)
        db.refresh(run)
        assert run.status == RunStatus.FAILED.value
        assert "attempt limit" in run.error_message


def test_clear_evidence_for_rerun(sqlite_db):
    from app.db.models import ChangedFile, TestRecord, VerificationAttempt

    with sqlite_db() as db:
        repo = _make_repo(db)
        run = AnalysisRun(repository_id=repo.id, status=RunStatus.FAILED.value)
        db.add(run)
        db.flush()
        f = ChangedFile(run_id=run.id, path="a.py", change_type="modified", added_lines=[1], removed_lines=[], supported=True)
        db.add(f)
        db.flush()
        db.add(TestRecord(run_id=run.id, node_id="t", name="t", category="STABLE_PASS", baseline_outcome="passed", modified_outcome="passed", executed_changed_lines={}, ran_changed_code=False))
        db.add(VerificationAttempt(run_id=run.id, file_path="a.py", function_qualname="f", kind="differential_probe", classification="INCONCLUSIVE", environment={}, detail={}))
        db.commit()
        clear_evidence_for_rerun(db, run.id)
        assert db.query(ChangedFile).count() == 0
        assert db.query(TestRecord).count() == 0
        assert db.query(VerificationAttempt).count() == 0
        assert db.query(AnalysisRun).count() == 1
