# -*- coding: utf-8 -*-
"""
Book to README Converter
========================
Converts a PDF book into chapter-wise Markdown (README) files.

Structure output:
  02_PDF/book/<BookName>/
  ├── README.md          ← Index + Preface
  ├── chapter_01.md
  ├── chapter_02.md
  └── ...

Usage:
  python book_to_readme.py
"""

import sys
import re
import os
import textwrap
import io

# Force UTF-8 on Windows stdout so emoji/special chars don't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)

from shared.console import (
    console,
    print_banner,
    print_success,
    print_error,
    print_warning,
    print_info,
)
from shared.config import PROJECT_ROOT

from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt
from rich.table import Table

RICH = True

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

BOOKS_DIR = PROJECT_ROOT / "output" / "books"
OUTPUT_BASE = BOOKS_DIR  # output folders go inside output/books/<BookName>/

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def log(msg: str, style: str = ""):
    console.print(msg, style=style)


def sanitize_filename(name: str) -> str:
    """Remove characters not safe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = name.strip(". ")
    return name or "untitled"


def slugify_chapter(title: str, index: int) -> str:
    """Create a safe chapter filename like chapter_01_intro.md"""
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")
    slug = slug[:40]  # cap length
    return f"chapter_{index:02d}_{slug}.md"


def heading_level_to_md(level: int) -> str:
    """Convert TOC level (1-based) to Markdown heading prefix."""
    # PDF TOC level 1 → #, level 2 → ##, etc.
    hashes = "#" * max(1, min(level, 6))
    return hashes


def extract_toc(doc: fitz.Document):
    """
    Extract the table of contents from the PDF.
    Returns list of (level, title, page_number) tuples.
    """
    toc = doc.get_toc(simple=False)
    result = []
    for entry in toc:
        if len(entry) >= 3:
            level, title, page = entry[0], entry[1], entry[2]
            result.append((int(level), str(title).strip(), int(page)))
    return result


def group_into_chapters(toc: list, total_pages: int) -> list[dict]:
    """
    Group TOC entries into top-level chapters.
    Each chapter dict has:
      - title, level, start_page, end_page, subsections[]
    """
    if not toc:
        return []

    # Find the minimum level (top-level entries)
    min_level = min(e[0] for e in toc)
    chapters = []

    top_entries = [(i, e) for i, e in enumerate(toc) if e[0] == min_level]

    for k, (idx, entry) in enumerate(top_entries):
        level, title, start_page = entry
        # end_page is one before the next top-level entry's start
        if k + 1 < len(top_entries):
            next_top_idx = top_entries[k + 1][0]
            end_page = toc[next_top_idx][2] - 1
        else:
            end_page = total_pages

        # Collect subsections between this top entry and the next
        subsections = []
        next_top_idx = top_entries[k + 1][0] if k + 1 < len(top_entries) else len(toc)
        for sub_entry in toc[idx + 1: next_top_idx]:
            sub_level, sub_title, sub_page = sub_entry
            subsections.append({
                "level": sub_level,
                "title": sub_title,
                "page": sub_page,
            })

        chapters.append({
            "title": title,
            "level": level,
            "start_page": max(1, start_page),
            "end_page": min(end_page, total_pages),
            "subsections": subsections,
        })

    return chapters


def extract_page_text(doc: fitz.Document, page_num: int) -> str:
    """Extract plain text from a single page (1-indexed)."""
    if page_num < 1 or page_num > len(doc):
        return ""
    page = doc[page_num - 1]
    return page.get_text("text")


def clean_text(text: str) -> str:
    """
    Basic cleaning:
    - Collapse excessive blank lines (max 2)
    - Strip trailing whitespace per line
    """
    lines = text.splitlines()
    cleaned = []
    blank_count = 0
    for line in lines:
        stripped = line.rstrip()
        if stripped == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(stripped)
    return "\n".join(cleaned)


def build_chapter_md(chapter: dict, doc: fitz.Document, chapter_num: int) -> str:
    """
    Build the full Markdown content for a chapter.
    """
    lines = []

    # Chapter heading
    heading = heading_level_to_md(1)  # always H1 for chapter title in its own file
    lines.append(f"{heading} {chapter['title']}")
    lines.append("")

    # Add navigation hint
    lines.append(f"> **Chapter {chapter_num}** | Pages {chapter['start_page']}–{chapter['end_page']}")
    lines.append("")

    # Subsection headings index (mini-TOC within the chapter)
    if chapter["subsections"]:
        lines.append("## Contents")
        lines.append("")
        for sub in chapter["subsections"]:
            indent = "  " * (sub["level"] - 2)
            anchor = re.sub(r"[^\w\s-]", "", sub["title"].lower())
            anchor = re.sub(r"[\s]+", "-", anchor).strip("-")
            lines.append(f"{indent}- [{sub['title']}](#{anchor})")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Extract text page by page, injecting subsection headings at right pages
    sub_map = {}  # page → list of subsections starting at that page
    for sub in chapter["subsections"]:
        sub_map.setdefault(sub["page"], []).append(sub)

    for pg in range(chapter["start_page"], chapter["end_page"] + 1):
        # Inject subsection headings before page text if a subsection starts here
        if pg in sub_map:
            for sub in sub_map[pg]:
                # subsection level relative to file: level 2 → ## , level 3 → ###, etc.
                relative_level = sub["level"]  # keep original hierarchy
                h = heading_level_to_md(relative_level)
                lines.append("")
                lines.append(f"{h} {sub['title']}")
                lines.append("")

        raw = extract_page_text(doc, pg)
        if raw.strip():
            page_text = clean_text(raw)
            lines.append(page_text)
            lines.append("")

    return "\n".join(lines)


def find_preface_pages(doc: fitz.Document, toc: list, first_chapter_page: int) -> tuple[int, int]:
    """
    Heuristically find the preface / front matter.
    Returns (start_page, end_page).
    Front matter = everything before the first TOC entry.
    """
    start = 1
    end = max(1, first_chapter_page - 1)
    return start, end


def build_index_readme(
    book_title: str,
    toc: list,
    chapters: list[dict],
    chapter_files: list[str],
    preface_text: str,
) -> str:
    """Build the root README.md with index and preface."""
    lines = []

    lines.append(f"# {book_title}")
    lines.append("")
    lines.append("> Auto-generated from PDF using `book_to_readme.py`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Preface / Front Matter ──────────────────────────────────────────────
    if preface_text.strip():
        lines.append("## Preface")
        lines.append("")
        lines.append(clean_text(preface_text))
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── Table of Contents ───────────────────────────────────────────────────
    lines.append("## Table of Contents")
    lines.append("")

    for i, (chapter, filename) in enumerate(zip(chapters, chapter_files), start=1):
        # Link to the chapter file
        rel_path = filename
        lines.append(f"### [{i}. {chapter['title']}]({rel_path})")
        if chapter["subsections"]:
            for sub in chapter["subsections"]:
                indent = "  " * max(0, sub["level"] - 2)
                lines.append(f"{indent}- {sub['title']} *(p. {sub['page']})*")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Generated by book_to_readme.py*")
    lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def list_available_books() -> list[Path]:
    """Return all PDF files in the books directory."""
    return sorted(BOOKS_DIR.glob("*.pdf"))


def pick_book() -> Path | None:
    """Prompt user to select a book by name or number."""
    pdfs = list_available_books()
    if not pdfs:
        log(f"[red]No PDF files found in {BOOKS_DIR}[/red]")
        return None

    if RICH:
        table = Table(title="Available Books", style="cyan", header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Book Name", style="bold")
        table.add_column("Size", justify="right")
        for i, p in enumerate(pdfs, 1):
            size_mb = p.stat().st_size / (1024 * 1024)
            table.add_row(str(i), p.stem, f"{size_mb:.1f} MB")
        console.print(table)
        console.print()

        choice = Prompt.ask(
            "[bold yellow]Enter book name (or number)[/bold yellow]",
            default="1"
        )
    else:
        print("\nAvailable books:")
        for i, p in enumerate(pdfs, 1):
            print(f"  [{i}] {p.name}")
        choice = input("\nEnter book name or number: ").strip()

    # Numeric selection
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(pdfs):
            return pdfs[idx]
        else:
            log("[red]Invalid number.[/red]")
            return None

    # Name match (partial, case-insensitive)
    choice_lower = choice.lower()
    matches = [p for p in pdfs if choice_lower in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        log(f"[yellow]Multiple matches:[/yellow]")
        for m in matches:
            log(f"  {m.name}")
        log("[red]Please be more specific.[/red]")
        return None
    else:
        log(f"[red]No book matching '{choice}' found.[/red]")
        return None


def convert_book(pdf_path: Path):
    """Main conversion pipeline."""
    if RICH:
        console.print(Panel(
            f"[bold green]Converting:[/bold green] [cyan]{pdf_path.name}[/cyan]",
            expand=False
        ))
    else:
        print(f"\nConverting: {pdf_path.name}\n")

    # ── Open PDF ────────────────────────────────────────────────────────────
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    log(f"[dim]  Pages: {total_pages}[/dim]")

    # ── Extract TOC ─────────────────────────────────────────────────────────
    toc = extract_toc(doc)
    if not toc:
        log("[yellow]⚠  No embedded Table of Contents found in this PDF.[/yellow]")
        log("[yellow]   Falling back to page-based splitting (every 30 pages = 1 chapter).[/yellow]")
        toc = _fake_toc_from_pages(total_pages)

    log(f"[dim]  TOC entries: {len(toc)}[/dim]")

    # ── Group into chapters ──────────────────────────────────────────────────
    chapters = group_into_chapters(toc, total_pages)
    if not chapters:
        log("[red]Could not determine chapters. Aborting.[/red]")
        return

    log(f"[bold]  Chapters detected: {len(chapters)}[/bold]")

    # ── Determine output folder ──────────────────────────────────────────────
    # Use PDF stem as folder name, sanitized
    folder_name = sanitize_filename(pdf_path.stem)
    out_dir = OUTPUT_BASE / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"[dim]  Output folder: {out_dir}[/dim]")

    # ── Extract preface / front matter ──────────────────────────────────────
    first_ch_page = chapters[0]["start_page"] if chapters else 1
    pre_start, pre_end = find_preface_pages(doc, toc, first_ch_page)
    preface_text = ""
    if pre_end >= pre_start:
        for pg in range(pre_start, pre_end + 1):
            preface_text += extract_page_text(doc, pg)

    # ── Write chapter files ──────────────────────────────────────────────────
    chapter_files = []

    progress_ctx = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) if RICH else None

    def _write_chapters():
        for i, chapter in enumerate(chapters, start=1):
            filename = slugify_chapter(chapter["title"], i)
            chapter_files.append(filename)
            md_content = build_chapter_md(chapter, doc, i)
            out_path = out_dir / filename
            out_path.write_text(md_content, encoding="utf-8")
            if progress_ctx:
                progress_ctx.advance(task_id)
            else:
                print(f"  ✓ {filename}")

    if RICH:
        with progress_ctx:
            task_id = progress_ctx.add_task(
                "[cyan]Writing chapters...", total=len(chapters)
            )
            _write_chapters()
    else:
        _write_chapters()

    # ── Write root README ────────────────────────────────────────────────────
    book_title = pdf_path.stem.replace("_", " ")
    readme_content = build_index_readme(
        book_title=book_title,
        toc=toc,
        chapters=chapters,
        chapter_files=chapter_files,
        preface_text=preface_text,
    )
    readme_path = out_dir / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")

    doc.close()

    # ── Summary ──────────────────────────────────────────────────────────────
    if RICH:
        console.print()
        console.print(Panel(
            f"[bold green]Done![/bold green]\n\n"
            f"  Output: [cyan]{out_dir}[/cyan]\n"
            f"  README.md  <- index + preface\n"
            f"  {len(chapters)} chapter files generated",
            title="Conversion Complete",
            expand=False,
        ))
    else:
        print(f"\nDone! Output: {out_dir}")
        print(f"   README.md + {len(chapters)} chapter files generated.")


def _fake_toc_from_pages(total_pages: int, chunk: int = 30) -> list:
    """Generate a fake TOC when the PDF has no embedded outline."""
    toc = []
    ch = 1
    for pg in range(1, total_pages + 1, chunk):
        toc.append((1, f"Chapter {ch}", pg))
        ch += 1
    return toc


def run():
    # Make sure output/books directory exists
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    console.print(Panel(
        "[bold magenta]Book -> README Converter[/bold magenta]\n"
        "[dim]Converts PDF books into chapter-wise Markdown files[/dim]",
        expand=False,
    ))
    console.print()

    pdf_path = pick_book()
    if pdf_path:
        convert_book(pdf_path)


if __name__ == "__main__":
    run()
