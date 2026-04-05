"""
In-memory job store + thread lock.

All routers and background tasks access job state exclusively through the
helpers defined here. This keeps concurrency logic in one place and makes
it trivial to swap the store for SQLite/Redis later.
"""

import threading
from typing import Dict, Optional

from app.models import JobState


# The single source of truth for all running/completed jobs (keyed by Post ID)
_jobs: Dict[str, JobState] = {}
_lock = threading.Lock()

def get_job(job_id: str) -> Optional[JobState]:
    """Thread-safe read of a single job. Returns None if not found."""
    with _lock:
        return _jobs.get(job_id)

def set_job(job: JobState) -> None:
    """Thread-safe write (create or replace) of a job."""
    with _lock:
        _jobs[job.id] = job

def update_job(job_id: str, **fields) -> None:
    """
    Thread-safe partial update of an existing job.
    Only fields that are passed as kwargs are modified.
    Silently no-ops if the job_id doesn't exist.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is not None:
            updated = job.model_copy(update=fields)
            _jobs[job_id] = updated

def all_jobs() -> list[JobState]:
    """Return a snapshot of all jobs (safe to iterate outside the lock)."""
    with _lock:
        return list(_jobs.values())
