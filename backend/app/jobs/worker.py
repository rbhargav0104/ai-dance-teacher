"""Background analysis worker.

Development runs one in-process thread next to the single API process (spec 24 allows a single
worker with SQLite). The worker claims jobs atomically, heartbeats while it works, and on start
recovers jobs whose worker died. Production gets a dedicated worker process in Outcome 10.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_sessionmaker
from app.jobs import queue
from app.models import AnalysisJob, DanceProject
from app.pipeline.errors import AnalysisFailed
from app.services.intake import project_prefix
from app.storage import get_storage

log = logging.getLogger("app.worker")


class Worker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.worker_id = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_recover = 0.0

    # -- lifecycle -------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="analysis-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _loop(self) -> None:
        log.info("worker_started", extra={"worker_id": self.worker_id})
        while not self._stop.is_set():
            try:
                did_work = self.run_once()
            except Exception:  # pragma: no cover - keep the loop alive; logged
                log.exception("worker_loop_error")
                did_work = False
            if not did_work:
                self._stop.wait(self.settings.worker_poll_seconds)

    # -- one iteration -----------------------------------------------------------------------
    def recover(self) -> int:
        with get_sessionmaker()() as db:
            return queue.recover(
                db,
                lease_seconds=self.settings.job_lease_seconds,
                max_attempts=self.settings.job_max_attempts,
            )

    def run_once(self) -> bool:
        """Recover stale jobs (at most every 30 s), then claim and run one job."""
        now = time.monotonic()
        if now - self._last_recover > 30 or self._last_recover == 0.0:
            self._last_recover = now
            self.recover()
        with get_sessionmaker()() as db:
            job_id = queue.claim_next(db, self.worker_id)
        if job_id is None:
            return False
        self._run(job_id)
        return True

    def _run(self, job_id: str) -> None:
        storage = get_storage()
        with get_sessionmaker()() as db:
            job = db.get(AnalysisJob, job_id)
            if job is None:
                return
            project_id = job.project_id
            owner_id = job.owner_id
            attempts = job.attempts

            def progress(stage: str, frac: float) -> None:
                with get_sessionmaker()() as hb:
                    queue.heartbeat(hb, job_id, self.worker_id, stage=stage, progress=frac)

            log.info("job_started", extra={"job_id": job_id, "attempt": attempts})
            try:
                if job.kind != queue.REFERENCE_ANALYSIS:
                    raise AnalysisFailed("unknown_job", "Unknown job type.")
                try:
                    from app.pipeline.reference import run_reference_analysis
                except ImportError as exc:
                    raise AnalysisFailed(
                        "analysis_unavailable",
                        "The movement-analysis runtime is not installed on this server.",
                        retryable=True,
                    ) from exc
                outcome = run_reference_analysis(db, storage, self.settings, job, progress)
                note = "Analysis complete."
                if outcome.warnings:
                    note = "Analysis complete with warnings."
                queue.finish(
                    db,
                    job_id,
                    self.worker_id,
                    status="succeeded",
                    message=note,
                    project_status="analyzed",
                )
                log.info("job_succeeded", extra={"job_id": job_id, "frames": outcome.frames})
            except queue.JobLost:
                db.rollback()
                self._cleanup_if_deleted(project_id, owner_id)
                log.info("job_lost", extra={"job_id": job_id})
            except AnalysisFailed as exc:
                db.rollback()
                self._safe_finish_failed(db, job_id, exc.code, exc.message, exc.retryable)
                self._cleanup_if_deleted(project_id, owner_id)
            except Exception:
                db.rollback()
                log.exception("job_crashed", extra={"job_id": job_id})
                if self._cleanup_if_deleted(project_id, owner_id):
                    return
                if attempts < self.settings.job_max_attempts:
                    queue.requeue(db, job_id, self.worker_id, "Retrying after an internal error…")
                else:
                    self._safe_finish_failed(
                        db,
                        job_id,
                        "analysis_crashed",
                        "Analysis failed unexpectedly. You can try again.",
                        True,
                    )

    def _safe_finish_failed(
        self, db: Session, job_id: str, code: str, message: str, retryable: bool
    ) -> None:
        try:
            queue.finish(
                db,
                job_id,
                self.worker_id,
                status="failed",
                message=message,
                error_code=code,
                retryable=retryable,
                project_status="failed",
                project_error=message,
            )
            log.info("job_failed", extra={"job_id": job_id, "code": code})
        except queue.JobLost:
            pass

    def _cleanup_if_deleted(self, project_id: str | None, owner_id: str) -> bool:
        """If the project was deleted mid-job, remove anything the job wrote after deletion."""
        if project_id is None:
            return False
        with get_sessionmaker()() as db:
            if db.get(DanceProject, project_id) is not None:
                return False
        get_storage().delete_prefix(project_prefix(owner_id, project_id))
        return True


_worker: Worker | None = None
_worker_lock = threading.Lock()


def get_worker() -> Worker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = Worker()
        return _worker


def reset_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.stop()
        _worker = None


def worker_available(settings: Settings) -> bool:
    if settings.worker_mode == "off":
        return False
    if settings.worker_mode == "manual":
        return True
    return get_worker().alive
