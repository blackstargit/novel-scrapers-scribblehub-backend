"""
GET /api/status/{job_id}  — Poll the live state of a scrape job.
GET /api/jobs             — List all known jobs (most recent first).
"""

from fastapi import APIRouter, HTTPException

from app.models import StatusResponse
from app.state import all_jobs, get_job


router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status/{job_id}", response_model=StatusResponse)
def get_status(job_id: str) -> StatusResponse:
    """Return the current state of a specific job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return StatusResponse(**job.model_dump())


@router.get("/jobs", response_model=list[StatusResponse])
def list_jobs() -> list[StatusResponse]:
    """Return all known jobs, most recently created first."""
    jobs = all_jobs()
    return [StatusResponse(**j.model_dump()) for j in reversed(jobs)]
