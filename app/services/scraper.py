"""
ScribbleHub chapter scraper.

Two-tier fetching strategy:
  1. Direct GET (fast, no overhead) — tried first for chapter pages.
  2. FlareSolverr fallback — used for the series/TOC pages and when
     direct fetch is blocked by Cloudflare.
"""

import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup

from app.config import get_settings

logger = logging.getLogger(__name__)

def _flaresolverr_url() -> str:
    return get_settings().flaresolverr_url

# ── Low-level fetchers ─────────────────────────────────────────────────────────
def fetch_via_flaresolverr(
    url: str,
    method: str = "GET",
    post_data: dict | None = None,
    retries: int = 3,
) -> str:
    """Fetch a URL through FlareSolverr to bypass Cloudflare JS challenges."""
    endpoint = f"{_flaresolverr_url()}/v1"

    if method.upper() == "POST" and post_data:
        payload = {
            "cmd": "request.post",
            "url": url,
            "postData": "&".join(f"{k}={v}" for k, v in post_data.items()),
            "maxTimeout": 60000,
        }
    else:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}

    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(endpoint, json=payload, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "ok":
                return data["solution"]["response"]
            raise RuntimeError(
                f"FlareSolverr status: {data.get('status')} — {data.get('message', '')}"
            )
        except Exception as exc:
            logger.warning(
                "FlareSolverr attempt %d/%d failed for %s: %s",
                attempt,
                retries,
                url,
                str(exc)[:120],
            )
            if attempt < retries:
                time.sleep(5 * attempt)

    raise RuntimeError(f"FlareSolverr failed to fetch {url} after {retries} attempts.")

def fetch_direct(url: str, retries: int = 3) -> str:
    """Direct GET request — fast, no Cloudflare bypass. Raises RuntimeError on failure."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/135.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            logger.warning(
                "Direct fetch attempt %d/%d failed for %s: %s",
                attempt,
                retries,
                url,
                str(exc)[:120],
            )
            if attempt < retries:
                time.sleep(3 * attempt)
    raise RuntimeError(f"Direct fetch failed for {url} after {retries} attempts.")

# ── Parsers ───────────────────────────────────────────────────────────────────
def parse_series_metadata(html: str) -> dict:
    """Parse the series main page to extract metadata."""
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.find(class_="fic_title") or soup.find(property="name")
    title = title_el.get_text(strip=True) if title_el else "Unknown Title"

    author_el = soup.find(class_="auth_name_fic")
    author = author_el.get_text(strip=True) if author_el else "Unknown Author"

    desc_el = soup.find(class_="wi_fic_desc")
    description = ""
    if desc_el:
        ps = desc_el.find_all("p")
        description = "\n\n".join(
            p.get_text(strip=True) for p in ps if p.get_text(strip=True)
        )

    cover_el = soup.select_one(".fic_image img[src]")
    cover_url = cover_el["src"] if cover_el else ""

    post_id_el = soup.find("input", id="mypostid")
    post_id = post_id_el["value"] if post_id_el else None

    # Fallback: try the report link
    if not post_id:
        report_el = soup.find("a", id="report_id")
        if report_el:
            post_id = report_el.get("value")

    chp_count_el = soup.find("input", id="chpcounter")
    total_chapters = (
        int(chp_count_el["value"])
        if chp_count_el and chp_count_el["value"].isdigit()
        else 0
    )

    return {
        "title": title,
        "author": author,
        "description": description,
        "cover_url": cover_url,
        "post_id": post_id,
        "total_chapters": total_chapters,
    }

def parse_chapter_list_from_html(html: str) -> list:
    """
    Extract chapter list from the static series page HTML.
    May be incomplete if the TOC is paginated.
    """
    soup = BeautifulSoup(html, "lxml")
    chapters = []
    for li in soup.select("li.toc_w"):
        a = li.find("a", class_="toc_a")
        if not a:
            continue
        order_attr = li.get("order")
        chapters.append(
            {
                "number": int(order_attr) if order_attr and order_attr.isdigit() else 0,
                "title": a.get_text(strip=True),
                "url": a.get("href"),
            }
        )
    chapters.sort(key=lambda x: x["number"])
    for idx, ch in enumerate(chapters, 1):
        ch["number"] = idx
    return chapters

def fetch_chapter_list(post_id: str, total_chapters: int) -> list:
    """Fetch the full chapter list via the WordPress AJAX endpoint (via FlareSolverr)."""
    ajax_url = "https://www.scribblehub.com/wp-admin/admin-ajax.php"
    chapters = []
    pagenum = 1

    while True:
        data = {
            "action": "wi_getreleases_pagination",
            "pagenum": pagenum,
            "mypostid": post_id,
        }
        html = fetch_via_flaresolverr(ajax_url, method="POST", post_data=data)
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("li.toc_w")

        if not items:
            break

        for li in items:
            a = li.find("a", class_="toc_a")
            if not a:
                continue
            order_attr = li.get("order")
            chapters.append(
                {
                    "number": int(order_attr) if order_attr and order_attr.isdigit() else 0,
                    "title": a.get_text(strip=True),
                    "url": a.get("href"),
                }
            )

        if total_chapters > 0 and len(chapters) >= total_chapters:
            break

        pagenum += 1
        time.sleep(0.3)

    chapters.sort(key=lambda x: x["number"] or 0)
    for idx, ch in enumerate(chapters, 1):
        ch["number"] = idx
    return chapters

def parse_chapter_content(html: str) -> tuple[str, str]:
    """Parse chapter title and body text from a chapter page."""
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".chapter-title") or soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else "Unknown Chapter"

    content_div = soup.find(id="chp_raw")
    if not content_div:
        return title, ""

    paragraphs = [
        p.get_text(strip=True)
        for p in content_div.find_all("p")
        if p.get_text(strip=True)
    ]
    return title, "\n\n".join(paragraphs)

# ── Main entrypoint ───────────────────────────────────────────────────────────
def scrape(
    url: str,
    output_dir: Path,
    start: int = 1,
    end: Optional[int] = None,
    delay: float = 1.5,
    skip_existing: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict:
    """
    Scrape a ScribbleHub novel, saving each chapter as a Markdown file.

    Args:
        url: ScribbleHub series URL.
        output_dir: Directory to write chapter .md files into.
        start: First chapter number to scrape (1-indexed).
        end: Last chapter number (inclusive), or None for all.
        delay: Seconds to wait between chapter requests.
        skip_existing: Skip chapters that already have a file on disk.
        progress_callback: Called with (current, total, message) on each step.

    Returns:
        Metadata dict parsed from the series page.
    """

    def log(current: int, total: int, msg: str) -> None:
        logger.info(msg)
        if progress_callback:
            progress_callback(current, total, msg)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log(0, 0, f"Fetching series metadata for {url}…")

    # 1 — Series page (always via FlareSolverr — reliably triggers JS challenge)
    html = fetch_via_flaresolverr(url)
    metadata = parse_series_metadata(html)

    if not metadata["post_id"]:
        raise ValueError(
            "Could not find post_id on the page. Is this a valid ScribbleHub series URL?"
        )

    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)

    log(
        0,
        metadata["total_chapters"],
        f"Found '{metadata['title']}' ({metadata['total_chapters']} chapters). Fetching TOC…",
    )

    # 2 — Table of Contents
    all_chapters = parse_chapter_list_from_html(html)
    if len(all_chapters) < metadata["total_chapters"]:
        logger.info(
            "Static TOC has %d/%d chapters — fetching remainder via AJAX…",
            len(all_chapters),
            metadata["total_chapters"],
        )
        all_chapters = fetch_chapter_list(metadata["post_id"], metadata["total_chapters"])

    if not all_chapters:
        log(0, 0, "No chapters found. Aborting.")
        return metadata

    start_idx = max(0, start - 1)
    end_idx = min(len(all_chapters), end) if end is not None else len(all_chapters)
    chapters_to_scrape = all_chapters[start_idx:end_idx]
    total = len(chapters_to_scrape)

    log(0, total, f"Scraping chapters {start}–{start_idx + total}…")

    # 3 — Download chapters
    for i, ch in enumerate(chapters_to_scrape, 1):
        num = ch["number"]
        ch_url = ch["url"]
        out_path = output_dir / f"chapter{num}.md"

        if skip_existing and out_path.exists():
            log(i, total, f"Skipping chapter {num} (already downloaded)")
            continue

        log(i, total, f"Scraping chapter {num}: {ch['title']}")

        try:
            try:
                ch_html = fetch_direct(ch_url)
            except RuntimeError:
                logger.info("Direct fetch failed for chapter %d — retrying via FlareSolverr…", num)
                ch_html = fetch_via_flaresolverr(ch_url)

            ch_title, content = parse_chapter_content(ch_html)

            if not content:
                log(i, total, f"Warning: empty content for chapter {num}")
                continue

            out_path.write_text(f"# {ch_title}\n\n{content}\n", encoding="utf-8")

            if i < total:
                time.sleep(delay)

        except Exception as exc:
            log(i, total, f"Error scraping chapter {num}: {exc}")

    log(total, total, "Scraping complete.")
    return metadata

# ── CLI (standalone usage) ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape a ScribbleHub novel.")
    parser.add_argument("url", help="Series URL, e.g. https://www.scribblehub.com/series/311974/")
    parser.add_argument("--output", default="./chapters", help="Output directory")
    parser.add_argument("--start", type=int, default=1, help="First chapter number")
    parser.add_argument("--end", type=int, default=None, help="Last chapter number")
    parser.add_argument("--no-skip", action="store_true", help="Re-download existing chapters")
    args = parser.parse_args()

    scrape(
        args.url,
        Path(args.output),
        start=args.start,
        end=args.end,
        skip_existing=not args.no_skip,
    )
