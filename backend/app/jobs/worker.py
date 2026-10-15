from __future__ import annotations

import argparse
import logging
import shutil
import socket
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.session import get_engine
from app.engine.pipeline import PipelineCancelled, execute_analysis
from app.jobs.queue import claim_next_job, heartbeat, is_cancel_requested, reclaim_abandoned_jobs
from app.logging_config import configure_logging

logger = logging.getLogger("branchsleuth.jobs")

POLL_INTERVAL = 2.0
HB_INTERVAL = 10.0


def cleanup_tmp(days: float = 1.0) -> None:
    tmp_root = Path(settings.data_path()) / "tmp"
    if not tmp_root.exists():
        return
    cutoff = time.time() - days * 86400
    for child in tmp_root.iterdir():
        try:
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


def process_run(session_factory: sessionmaker, run_id: uuid.UUID) -> None:
    check_db: Session = session_factory()

    def wrapped_cancel_check() -> bool:
        try:
            heartbeat(check_db, run_id)
        except Exception:
            check_db.rollback()
        return is_cancel_requested(check_db, run_id)

    try:
        execute_analysis(run_id, session_factory, cancel_check=wrapped_cancel_check)
    except PipelineCancelled:
        logger.info("run %s cancelled", run_id)
    except Exception:
        logger.exception("run %s failed", run_id)
    finally:
        check_db.close()


def main() -> int:
    configure_logging("INFO")
    parser = argparse.ArgumentParser(description="BranchSleuth analysis worker")
    parser.add_argument("--once", action="store_true", help="process at most one queued job then exit")
    args = parser.parse_args()
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    engine = get_engine()
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    control_db: Session = session_factory()
    logger.info("worker %s started (image=%s)", worker_id, settings.worker_image)
    last_reclaim = 0.0
    last_cleanup = 0.0
    while True:
        try:
            if time.time() - last_reclaim > 60:
                reclaimed = reclaim_abandoned_jobs(control_db)
                if reclaimed:
                    logger.info("reclaimed %d abandoned jobs", reclaimed)
                last_reclaim = time.time()
            if time.time() - last_cleanup > 600:
                cleanup_tmp(1.0)
                last_cleanup = time.time()
            run_id = claim_next_job(control_db, worker_id)
            if run_id is None:
                if args.once:
                    break
                time.sleep(POLL_INTERVAL)
                continue
            logger.info("claimed run %s", run_id)
            process_run(session_factory, run_id)
            if args.once:
                break
        except KeyboardInterrupt:
            logger.info("worker interrupted")
            control_db.close()
            return 0
        except Exception:
            logger.exception("worker loop error")
            time.sleep(5)
    control_db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
