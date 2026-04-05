"""
EPUB builder — converts a directory of Markdown chapter files into a
QuickNovel-compatible .epub file.

Chapter files must be named chapter<N>.md (e.g. chapter1.md, chapter42.md).
"""

import logging
import re
from pathlib import Path

import markdown
import requests
from ebooklib import epub

logger = logging.getLogger(__name__)


def _download_cover(cover_url: str, dest: Path) -> bool:
    """Download a cover image to *dest*. Returns True on success."""
    try:
        resp = requests.get(
            cover_url,
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        logger.info("Downloaded cover: %s", cover_url)
        return True
    except Exception as exc:
        logger.warning("Could not download cover image: %s", exc)
        return False


def build_epub(
    input_dir: Path,
    output_file: Path,
    book_title: str = "QuickNovel Book",
    metadata: dict | None = None,
) -> None:
    """
    Build a .epub from Markdown chapter files in *input_dir*.

    Args:
        input_dir: Directory containing chapter<N>.md files (and optionally
                   a metadata.json and cover image).
        output_file: Destination path for the generated .epub.
        book_title: Title embedded in EPUB metadata.
        metadata: Dict with optional keys: author, description, cover_url.
    """
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    metadata = metadata or {}

    # ── Book metadata ──────────────────────────────────────────────────────────
    book = epub.EpubBook()
    book.set_identifier(book_title.lower().replace(" ", "_"))
    book.set_title(book_title)
    book.set_language("en")

    if metadata.get("author"):
        book.add_author(metadata["author"])
    if metadata.get("description"):
        book.add_metadata("DC", "description", metadata["description"])

    # ── Cover image ────────────────────────────────────────────────────────────
    if metadata.get("cover_url"):
        cover_url: str = metadata["cover_url"]
        ext = cover_url.split("?")[0].rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = "jpg"
        cover_path = input_dir / f"cover.{ext}"
        if not cover_path.exists():
            _download_cover(cover_url, cover_path)
        if cover_path.exists():
            book.set_cover(f"cover.{ext}", cover_path.read_bytes())
            logger.info("Set cover image: %s", cover_path.name)

    # ── Spine / chapters ───────────────────────────────────────────────────────
    epub_chapters: list[epub.EpubHtml] = []
    spine: list = ["nav"]

    # Preface / description chapter (Chapter 0)
    if metadata.get("description"):
        desc_html = markdown.markdown(metadata["description"])
        full_desc = (
            f"<html><head><title>Description</title></head>"
            f"<body><h1>Description</h1>{desc_html}</body></html>"
        )
        desc_ch = epub.EpubHtml(
            title="Description", file_name="description.xhtml", lang="en"
        )
        desc_ch.set_content(full_desc)
        book.add_item(desc_ch)
        epub_chapters.append(desc_ch)
        spine.append(desc_ch)
        logger.info("Added: Description (Preface)")

    # Sort chapter files numerically
    md_files: list[tuple[int, Path]] = []
    for f in input_dir.glob("chapter*.md"):
        m = re.search(r"chapter(\d+)", f.name)
        if m:
            md_files.append((int(m.group(1)), f))
    md_files.sort(key=lambda x: x[0])

    for num, filepath in md_files:
        content = filepath.read_text(encoding="utf-8")

        # Use the first H1 as the chapter title
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else f"Chapter {num}"

        html_body = markdown.markdown(content)
        full_html = (
            f"<html><head><title>{title}</title></head>"
            f"<body>{html_body}</body></html>"
        )

        ch = epub.EpubHtml(
            title=title,
            file_name=f"chapter_{num}.xhtml",
            lang="en",
        )
        ch.set_content(full_html)
        book.add_item(ch)
        epub_chapters.append(ch)
        spine.append(ch)
        logger.info("Added: %s", title)

    # ── TOC / NCX / spine ─────────────────────────────────────────────────────
    book.toc = epub_chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    # ── Write output ───────────────────────────────────────────────────────────
    output_file.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Writing EPUB: %s", output_file)
    epub.write_epub(output_file, book)
    logger.info("EPUB build complete — %d chapters.", len(epub_chapters))


# ── CLI (standalone usage) ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Build a QuickNovel-compatible EPUB from Markdown chapters."
    )
    parser.add_argument(
        "--input", type=Path, default=Path("chapters"), help="Input directory"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("novel.epub"), help="Output EPUB path"
    )
    parser.add_argument("--title", type=str, default="Scraped Novel", help="Book title")
    args = parser.parse_args()

    build_epub(args.input, args.output, args.title)
