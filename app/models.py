"""
Pydantic models for API request/response bodies.
Keeping these separate from routing logic ensures easy reuse and testing.
"""

from typing import Literal, Optional
from pydantic import BaseModel, HttpUrl, field_validator


# ── Request Models ─────────────────────────────────────────────────────────────
class ScrapeRequest(BaseModel):
    """Body for POST /api/scrape"""
    url: str
    email: str

    @field_validator("url")
    @classmethod
    def url_must_be_scribblehub(cls, v: str) -> str:
        if "scribblehub.com/series/" not in v:
            raise ValueError("URL must be a ScribbleHub series URL")
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_must_have_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Provide a valid email address")
        return v.strip()

# ── Response / State Models ────────────────────────────────────────────────────
JobStatus = Literal["queued", "scraping", "converting", "emailing", "done", "error"]

class JobState(BaseModel):
    """Full in-memory state dict for a single scrape job."""
    id: str
    url: str
    email: str
    status: JobStatus = "queued"
    progress: str = "0/0"
    message: str = "Queued"
    epub_path: Optional[str] = None


class ScrapeResponse(BaseModel):
    """Returned immediately after POST /api/scrape."""
    job_id: str
    status: JobStatus

class StatusResponse(JobState):
    """Returned by GET /api/status/{job_id} — identical to JobState for now."""
    pass
