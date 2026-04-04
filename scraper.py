import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

import requests
from bs4 import BeautifulSoup

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FLARESOLVERR_URL = os.environ.get("FLARESOLVERR_URL", "http://localhost:8191")


def fetch_via_flaresolverr(url: str, method: str = "GET", post_data: dict = None, retries: int = 3) -> str:
    """Fetch a URL by passing it through FlareSolverr to bypass Cloudflare challenges."""
    endpoint = f"{FLARESOLVERR_URL}/v1"

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
            raise RuntimeError(f"FlareSolverr status: {data.get('status')} — {data.get('message', '')}")
        except Exception as exc:
            err = str(exc)[:120]
            logger.warning(f"FlareSolverr attempt {attempt}/{retries} failed for {url}: {err}")
            if attempt < retries:
                time.sleep(5 * attempt)

    raise RuntimeError(f"FlareSolverr failed to fetch {url} after {retries} attempts.")


def fetch_direct(url: str, retries: int = 3) -> str:
    """Direct GET request — fast, no Cloudflare bypass. Raises on failure."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            err = str(exc)[:120]
            logger.warning(f"Direct fetch attempt {attempt}/{retries} failed for {url}: {err}")
            if attempt < retries:
                time.sleep(3 * attempt)
    raise RuntimeError(f"Direct fetch failed for {url} after {retries} attempts.")


def parse_series_metadata(html: str) -> dict:
    """Parse the series main page to extract metadata."""
    soup = BeautifulSoup(html, "lxml")
    
    title_el = soup.find(class_='fic_title') or soup.find(property='name')
    title = title_el.get_text(strip=True) if title_el else "Unknown Title"
    
    author_el = soup.find(class_='auth_name_fic')
    author = author_el.get_text(strip=True) if author_el else "Unknown Author"
    
    desc_el = soup.find(class_='wi_fic_desc')
    description = ""
    if desc_el:
        ps = desc_el.find_all('p')
        description = "\n\n".join(p.get_text(strip=True) for p in ps if p.get_text(strip=True))

    cover_el = soup.select_one(".fic_image img[src]")
    cover_url = cover_el["src"] if cover_el else ""

    post_id_el = soup.find("input", id="mypostid")
    post_id = post_id_el["value"] if post_id_el else None

    # Handle scenario where hidden input isn't found exactly (fallback)
    if not post_id and soup.find("a", id="report_id"):
        # Sometimes id="mypostid" misses, try to grab from report_id
        post_id = soup.find("a", id="report_id").get("value")

    chp_count_el = soup.find("input", id="chpcounter")
    total_chapters = int(chp_count_el["value"]) if chp_count_el and chp_count_el["value"].isdigit() else 0

    return {
        "title": title,
        "author": author,
        "description": description,
        "cover_url": cover_url,
        "post_id": post_id,
        "total_chapters": total_chapters
    }


def parse_chapter_list_from_html(html: str) -> list:
    """Extract chapter list from static HTML (series page). May be incomplete if TOC is paginated."""
    soup = BeautifulSoup(html, "lxml")
    chapters = []
    for li in soup.select("li.toc_w"):
        a = li.find("a", class_="toc_a")
        if not a:
            continue
        order_attr = li.get("order")
        chapters.append({
            "number": int(order_attr) if order_attr and order_attr.isdigit() else 0,
            "title": a.get_text(strip=True),
            "url": a.get("href"),
        })
    chapters.sort(key=lambda x: x["number"])
    for idx, ch in enumerate(chapters, 1):
        ch["number"] = idx
    return chapters


def fetch_chapter_list(post_id: str, total_chapters: int) -> list:
    """Fetch all chapters via the WordPress AJAX endpoint, routed through FlareSolverr."""
    ajax_url = "https://www.scribblehub.com/wp-admin/admin-ajax.php"
    chapters = []
    pagenum = 1

    while True:
        data = {
            "action": "wi_getreleases_pagination",
            "pagenum": pagenum,
            "mypostid": post_id
        }

        html = fetch_via_flaresolverr(ajax_url, method="POST", post_data=data)
        soup = BeautifulSoup(html, "lxml")
        
        items = soup.select("li.toc_w")
        
        if not items:
            break
            
        page_chapters = []
        for li in items:
            a = li.find("a", class_="toc_a")
            if not a:
                continue
                
            title = a.get_text(strip=True)
            url = a.get("href")
            order_attr = li.get("order")
            order = int(order_attr) if order_attr and order_attr.isdigit() else 0
            
            page_chapters.append({
                "number": order,
                "title": title,
                "url": url
            })
            
        chapters.extend(page_chapters)
        
        if len(chapters) >= total_chapters and total_chapters > 0:
            break
            
        pagenum += 1
        time.sleep(0.3) # Gentle rate-limit on TOC fetches
        
    # Sort chapters by their order attribute to ensure we always have 1 to N
    chapters.sort(key=lambda x: x["number"] if x["number"] else 0)
    
    # Re-assign sequential numbers cleanly
    for idx, ch in enumerate(chapters, 1):
        ch["number"] = idx
        
    return chapters


def parse_chapter_content(html: str) -> tuple[str, str]:
    """Parse chapter title and text content from a chapter page."""
    soup = BeautifulSoup(html, "lxml")
    
    title_el = soup.select_one(".chapter-title") or soup.find("h1")
    title = title_el.get_text(strip=True) if title_el else "Unknown Chapter"
    
    content_div = soup.find(id="chp_raw")
    if not content_div:
        return title, ""
        
    # Strip HTML tags
    paragraphs = []
    for p in content_div.find_all("p"):
        text = p.get_text(strip=True)
        if text:
            paragraphs.append(text)
            
    content = "\n\n".join(paragraphs)
    return title, content


def scrape(url: str, output_dir: Path, start: int = 1, end: Optional[int] = None,
           delay: float = 1.5, skip_existing: bool = True,
           progress_callback: Optional[Callable[[int, int, str], None]] = None) -> dict:
    """
    Scrape novel from ScribbleHub.
    progress_callback receives (current_chapter_idx, total_chapters, message)
    """
    def log_progress(current, total, msg):
        logger.info(msg)
        if progress_callback:
            progress_callback(current, total, msg)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log_progress(0, 0, f"Fetching series metadata for {url}...")

    # 1. Fetch Series page for metadata (via FlareSolverr to bypass Cloudflare)
    html = fetch_via_flaresolverr(url)
    metadata = parse_series_metadata(html)
    
    if not metadata["post_id"]:
        raise ValueError("Could not find post_id on the page. Is this a valid ScribbleHub series URL?")
        
    # Save metadata
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)
        
    log_progress(0, metadata["total_chapters"], f"Found novel '{metadata['title']}' with {metadata['total_chapters']} total chapters. Fetching TOC...")

    # 2. Extract Table of Contents — try static HTML first, fall back to paginated AJAX
    all_chapters = parse_chapter_list_from_html(html)
    if len(all_chapters) < metadata["total_chapters"]:
        logger.info(f"Static TOC has {len(all_chapters)}/{metadata['total_chapters']} chapters — fetching remainder via AJAX...")
        all_chapters = fetch_chapter_list(metadata["post_id"], metadata["total_chapters"])
    
    if not all_chapters:
        log_progress(0, 0, "No chapters found. Aborting.")
        return metadata

    start_idx = max(0, start - 1)
    end_idx = min(len(all_chapters), end) if end is not None else len(all_chapters)
    
    chapters_to_scrape = all_chapters[start_idx:end_idx]
    total_to_scrape = len(chapters_to_scrape)
    
    log_progress(0, total_to_scrape, f"Scraping chapters {start} to {start_idx + total_to_scrape}...")
    
    # 3. Download Chapters
    for i, ch_info in enumerate(chapters_to_scrape, 1):
        num = ch_info["number"]
        ch_url = ch_info["url"]
        out_filepath = output_dir / f"chapter{num}.md"
        
        if skip_existing and out_filepath.exists():
            log_progress(i, total_to_scrape, f"Skipping chapter {num} - already exists")
            continue
            
        log_progress(i, total_to_scrape, f"Scraping chapter {num}: {ch_info['title']}")

        try:
            try:
                ch_html = fetch_direct(ch_url)
            except RuntimeError:
                logger.info(f"Direct fetch failed for chapter {num} — retrying via FlareSolverr...")
                ch_html = fetch_via_flaresolverr(ch_url)
            ch_title, content = parse_chapter_content(ch_html)
            
            if not content:
                log_progress(i, total_to_scrape, f"Warning: Empty content for chapter {num}")
                continue
                
            md_content = f"# {ch_title}\n\n{content}\n"
            
            with open(out_filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)
                
            if i < total_to_scrape:
                time.sleep(delay)
                
        except Exception as e:
            log_progress(i, total_to_scrape, f"Error scraping chapter {num}: {e}")
            
    log_progress(total_to_scrape, total_to_scrape, "Scraping complete.")
    
    return metadata


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Scrape from ScribbleHub.")
    parser.add_argument("url", help="Novel URL (e.g. https://www.scribblehub.com/series/311974/invincible-me/)")
    parser.add_argument("--output", default="./chapters", help="Output directory")
    parser.add_argument("--start", type=int, default=1, help="Start chapter")
    parser.add_argument("--end", type=int, default=None, help="End chapter")
    parser.add_argument("--no-skip", action="store_true", help="Do not skip existing")
    args = parser.parse_args()
    
    scrape(
        args.url, 
        Path(args.output), 
        start=args.start, 
        end=args.end, 
        skip_existing=not args.no_skip
    )
