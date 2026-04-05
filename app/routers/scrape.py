"""
POST /api/scrape  — Start or attach to an existing ScribbleHub scrape job.

If the novel's Post ID is already running, the frontend is attached to the
existing background task instead of launching a duplicate.
"""

import re
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.config import get_settings
from app.models import JobState, ScrapeRequest, ScrapeResponse
from app.services import emailer, md_to_epub, scraper
from app.state import get_job, set_job, update_job

router = APIRouter(prefix="/api", tags=["scrape"])
settings = get_settings()

# ── Background pipeline ────────────────────────────────────────────────────────
def _run_pipeline(job_id: str, url: str, email: str) -> None:
    """
    Full scrape → EPUB → email pipeline.
    Runs in a background thread via FastAPI BackgroundTasks.
    """
    data_dir = settings.data_dir / job_id
    chapters_dir = data_dir / "chapters"

    # ── Step 1: Scrape ─────────────────────────────────────────────────────────
    update_job(job_id, status="scraping", message="Starting scrape…")

    def _on_progress(current: int, total: int, msg: str) -> None:
        update_job(job_id, progress=f"{current}/{total}", message=msg)

    try:
        metadata = scraper.scrape(
            url=url,
            output_dir=chapters_dir,
            skip_existing=True,
            progress_callback=_on_progress,
        )
    except Exception as exc:
        update_job(job_id, status="error", message=f"Scrape failed: {exc}")
        return

    # ── Step 2: Convert to EPUB ────────────────────────────────────────────────
    update_job(job_id, status="converting", message="Converting to EPUB…")

    try:
        title = metadata.get("title", f"Novel-{job_id[:6]}")
        safe_title = "".join(
            c for c in title if c.isalnum() or c in (" ", "-", "_")
        ).strip()
        epub_path = data_dir / f"{safe_title}.epub"

        md_to_epub.build_epub(
            chapters_dir,
            epub_path,
            book_title=title,
            metadata=metadata,
        )
    except Exception as exc:
        update_job(job_id, status="error", message=f"EPUB generation failed: {exc}")
        return

    # ── Step 3: Email ──────────────────────────────────────────────────────────
    update_job(job_id, status="emailing", message="Sending EPUB via email…")

    try:
        success = emailer.send_epub_to_email(epub_path, email)
        if success:
            update_job(
                job_id,
                status="done",
                message="Done! Check your inbox.",
                epub_path=str(epub_path),
            )
        else:
            update_job(
                job_id,
                status="error",
                message="Email failed — check GMAIL_* credentials in .env.",
            )
    except Exception as exc:
        update_job(job_id, status="error", message=f"Email error: {exc}")

# ── Route ──────────────────────────────────────────────────────────────────────
@router.post("/scrape", response_model=ScrapeResponse, status_code=202)
def start_scrape(req: ScrapeRequest, bg: BackgroundTasks) -> ScrapeResponse:
    """
    Validate the ScribbleHub URL, derive the Post ID, and launch the pipeline
    (or attach to an already-running pipeline for the same novel).
    """
    match = re.search(r"scribblehub\.com/series/(\d+)", req.url)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="Not a valid ScribbleHub series URL — expected /series/<id>/",
        )

    job_id = match.group(1)
    existing = get_job(job_id)

    if existing and existing.status not in ("done", "error"):
        # Already running — let the frontend attach to it
        return ScrapeResponse(job_id=job_id, status=existing.status)

    job = JobState(id=job_id, url=req.url, email=req.email)
    set_job(job)
    bg.add_task(_run_pipeline, job_id, req.url, req.email)

    return ScrapeResponse(job_id=job_id, status="queued")
