from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import delete, select, text, update

from app.config import settings
from app.db.models import AnalysisRun, ChangedFile, ChangedScope, RunStatus, TestRecord, VerificationAttempt, utcnow
from sqlalchemy.orm import Session

ACTIVE_STATUSES = (
    RunStatus.PREPARING.value,
    RunStatus.ANALYZING.value,
    RunStatus.VERIFYING.value,
)


def claim_next_job(db: Session, worker_id: str) -> uuid.UUID | None:
    engine = db.get_bind()
    if engine.dialect.name == "postgresql":
        sql = text(
            """
            UPDATE analysis_runs
            SET status = 'preparing',
                locked_by = :worker,
                locked_at = now(),
                heartbeat_at = now(),
                attempts = attempts + 1
            WHERE id = (
                SELECT id FROM analysis_runs
                WHERE status = 'queued'
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
            """
        )
        row = db.execute(sql, {"worker": worker_id}).fetchone()
        db.commit()
        if row is None:
            return None
        val = row[0]
        return val if isinstance(val, uuid.UUID) else uuid.UUID(val)
    rows = db.scalars(select(AnalysisRun).where(AnalysisRun.status == RunStatus.QUEUED.value).order_by(AnalysisRun.created_at).limit(1)).all()
    if not rows:
        db.commit()
        return None
    run = rows[0]
    run.status = RunStatus.PREPARING.value
    run.locked_by = worker_id
    run.locked_at = utcnow()
    run.heartbeat_at = utcnow()
    run.attempts = run.attempts + 1
    db.add(run)
    db.commit()
    return run.id


def heartbeat(db: Session, run_id: uuid.UUID) -> None:
    db.execute(update(AnalysisRun).where(AnalysisRun.id == run_id).values(heartbeat_at=utcnow()))
    db.commit()


def is_cancel_requested(db: Session, run_id: uuid.UUID) -> bool:
    run = db.get(AnalysisRun, run_id)
    return bool(run and run.cancel_requested)


def reclaim_abandoned_jobs(db: Session) -> int:
    cutoff = utcnow() - timedelta(seconds=settings.job_lease_seconds)
    stale = db.scalars(
        select(AnalysisRun).where(
            AnalysisRun.status.in_(ACTIVE_STATUSES),
            AnalysisRun.locked_at.isnot(None),
            AnalysisRun.locked_at < cutoff,
        )
    ).all()
    reclaimed = 0
    for run in stale:
        if run.attempts >= settings.max_job_attempts:
            run.status = RunStatus.FAILED.value
            run.error_message = "job lease expired and was not retried (attempt limit reached)"
            run.completed_at = utcnow()
        else:
            run.status = RunStatus.QUEUED.value
            run.locked_by = None
            run.locked_at = None
            run.stage = "queued"
            run.stage_detail = "requeued after abandoned lease"
        db.add(run)
        reclaimed += 1
    if reclaimed:
        db.commit()
    return reclaimed


def clear_evidence_for_rerun(db: Session, run_id: uuid.UUID) -> None:
    db.execute(delete(VerificationAttempt).where(VerificationAttempt.run_id == run_id))
    db.execute(delete(TestRecord).where(TestRecord.run_id == run_id))
    db.execute(delete(ChangedScope).where(ChangedScope.run_id == run_id))
    db.execute(delete(ChangedFile).where(ChangedFile.run_id == run_id))
    db.commit()
