import sys
import uuid
import re
import threading
from pathlib import Path
from typing import Dict

from fastapi import FastAPI, BackgroundTasks, HTTPException
import os
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel

# Add parent directories to access scraper and other tools
base_dir = Path(__file__).resolve().parent
sys.path.append(str(base_dir))

import scraper
import md_to_epub
from emailer import send_epub_to_email

app = FastAPI(title="ScribbleHub Novel Downloader API")

# Setup Security Middlewares
ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "*").split(",") if host.strip()]
ALLOWED_ORIGINS = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]

app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# In-memory job state storage
jobs: Dict[str, dict] = {}
jobs_lock = threading.Lock()


class ScrapeRequest(BaseModel):
    url: str
    email: str


def update_job(job_id: str, updates: dict):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(updates)


def background_scrape_and_send(job_id: str, url: str, email: str):
    """The main orchestration pipeline that runs for each job."""
    
    # directories for this job
    work_dir = base_dir / "data" / job_id
    chapters_dir = work_dir / "chapters"
    epub_out = work_dir / "novel.epub"
    
    update_job(job_id, {"status": "scraping", "message": "Starting scrape process..."})
    
    def on_progress(current, total, msg):
        update_job(job_id, {"progress": f"{current}/{total}", "message": msg})

    # Step 1: Scrape
    try:
        metadata = scraper.scrape(
            url=url,
            output_dir=chapters_dir,
            skip_existing=True,
            progress_callback=on_progress
        )
    except Exception as e:
        update_job(job_id, {"status": "error", "message": f"Scrape failed: {e}"})
        return
        
    update_job(job_id, {"status": "converting", "message": "Converting to EPUB..."})

    # Step 2: Convert to EPUB
    try:
        # Build Title: we try to grab it from metadata
        title = metadata.get("title", f"ScribbleHub Novel {job_id[:4]}")
        # Build valid filename
        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
        epub_out = work_dir / f"{safe_title}.epub"
        
        md_to_epub.build_epub(chapters_dir, epub_out, book_title=title, metadata=metadata)
    except Exception as e:
        update_job(job_id, {"status": "error", "message": f"EPUB generation failed: {e}"})
        return

    update_job(job_id, {"status": "emailing", "message": "Sending EPUB via Email..."})

    # Step 3: Send Email
    try:
        success = send_epub_to_email(epub_out, email)
        if success:
            update_job(job_id, {"status": "done", "message": "Pipeline completed successfully!"})
        else:
            update_job(job_id, {"status": "error", "message": "Email sending failed. Please check backend logs / credentials."})
    except Exception as e:
        update_job(job_id, {"status": "error", "message": f"Emailing failed: {e}"})


@app.post("/api/scrape")
def start_scrape(req: ScrapeRequest, bg_tasks: BackgroundTasks):
    match = re.search(r"scribblehub\.com/series/(\d+)", req.url)
    if not match:
        raise HTTPException(status_code=400, detail="Not a valid ScribbleHub series URL or missing series ID")
    
    job_id = match.group(1)

    with jobs_lock:
        job = jobs.get(job_id)
        if job and job["status"] not in ("done", "error"):
            # Job is currently running. Return ID so frontend can attach.
            return {"job_id": job_id, "status": job["status"]}
            
        jobs[job_id] = {
            "id": job_id,
            "url": req.url,
            "status": "queued",
            "progress": "0/0",
            "message": "Queued"
        }

    bg_tasks.add_task(background_scrape_and_send, job_id, req.url, req.email)
    
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

from fastapi.responses import FileResponse

app.mount("/assets", StaticFiles(directory=base_dir / "assets"), name="assets")

@app.get("/")
def serve_index():
    index_path = base_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)

