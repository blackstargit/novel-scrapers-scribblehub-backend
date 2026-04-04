import argparse
import os
import re
from pathlib import Path

try:
    from ebooklib import epub
    import markdown
    import requests
except ImportError:
    print("Please install required libraries: pip install EbookLib markdown requests")
    exit(1)

def _download_cover(cover_url: str, dest: Path) -> bool:
    """Download cover image to dest. Returns True on success."""
    try:
        resp = requests.get(cover_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        print(f"Downloaded cover: {cover_url}")
        return True
    except Exception as e:
        print(f"Warning: Could not download cover image: {e}")
        return False

def build_epub(input_dir: Path, output_file: Path, book_title="QuickNovel Book", metadata: dict = None):
    if not input_dir.exists():
        print(f"Error: Directory {input_dir} does not exist.")
        return

    book = epub.EpubBook()

    # Set metadata
    book.set_identifier(book_title.lower().replace(" ", "_"))
    book.set_title(book_title)
    book.set_language('en')

    if metadata and metadata.get("author"):
        book.add_author(metadata["author"])
    if metadata and metadata.get("description"):
        book.add_metadata('DC', 'description', metadata["description"])

    # Embed cover image
    if metadata and metadata.get("cover_url"):
        cover_url = metadata["cover_url"]
        ext = cover_url.split("?")[0].rsplit(".", 1)[-1].lower() or "jpg"
        cover_path = input_dir / f"cover.{ext}"
        if not cover_path.exists():
            _download_cover(cover_url, cover_path)
        if cover_path.exists():
            book.set_cover(f"cover.{ext}", cover_path.read_bytes())
            print(f"Set cover image: {cover_path.name}")

    # Read markdown files sequentially based on their chapter number
    md_files = []
    for f in input_dir.glob("chapter*.md"):
        # Extract number from filename, e.g. "chapter12.md" -> 12
        match = re.search(r"chapter(\d+)", f.name)
        if match:
            md_files.append((int(match.group(1)), f))
    
    # Sort files naturally by chapter number
    md_files.sort(key=lambda x: x[0])

    chapters = []
    spine_items = ['nav']

    if metadata and metadata.get("description"):
        desc_html = markdown.markdown(metadata["description"])
        full_desc_html = f"<html><head><title>Description</title></head><body><h1>Description</h1>{desc_html}</body></html>"
        desc_chapter = epub.EpubHtml(title="Description", file_name='description.xhtml', lang='en')
        desc_chapter.set_content(full_desc_html)
        book.add_item(desc_chapter)
        chapters.append(desc_chapter)
        spine_items.append(desc_chapter)
        print("Added: Description (Preface)")

    for num, filepath in md_files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract title from the first H1 tag, or use a default
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else f"Chapter {num}"

        # Convert markdown to html
        html_content = markdown.markdown(content)

        # Wrap it in standard HTML for the EPUB
        full_html = f"""
        <html>
        <head>
            <title>{title}</title>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """

        # Create EPUB chapter instance
        # IMPORTANT: QuickNovel tracks chapter progress based on separate HTML items
        chapter = epub.EpubHtml(
            title=title,
            file_name=f'chapter_{num}.xhtml',
            lang='en'
        )
        chapter.set_content(full_html)
        
        book.add_item(chapter)
        chapters.append(chapter)
        spine_items.append(chapter)
        
        print(f"Added: {title}")

    # Define Table of Contents
    book.toc = chapters

    # Add default NCX and Nav file (needed for EPUB 2/3 TOC which QuickNovel relies on)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Set spine
    book.spine = spine_items

    # Write output
    print(f"Generating EPUB: {output_file}")
    epub.write_epub(output_file, book)
    print("Done! The EPUB is fully compatible with QuickNovel's chapter tracking.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build EPUB for QuickNovel from markdown chapters.")
    parser.add_argument("--input", type=Path, default=Path("chapters"), help="Input directory of markdown files")
    parser.add_argument("--output", type=Path, default=Path("novel.epub"), help="Output EPUB filename")
    parser.add_argument("--title", type=str, default="Scraped Novel", help="Book title")
    args = parser.parse_args()

    # Create the epub
    build_epub(args.input, args.output, args.title)
