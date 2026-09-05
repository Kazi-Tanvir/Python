# -*- coding: utf-8 -*-
"""
PDF Splitter Tool
=================
Split a PDF into smaller portions using three methods:

  1. **Page Range**     — Extract a page range into a single new PDF.
  2. **Manual Chapters** — Define chapter ranges interactively; each chapter
                           becomes a separate PDF inside a named folder.
  3. **Auto Chapters**  — Detect chapters from the PDF's embedded Table of
                           Contents and split automatically.

Output goes to:
  output/pdf_split/<BookName>/

Usage (standalone):
  python pdf_splitter.py

Usage (via main.py launcher):
  Registered as "PDF Splitter" in the toolkit menu.
"""

import sys
import re
import io

# Force UTF-8 on Windows stdout so special chars don't crash
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] PyMuPDF not installed. Run: pip install pymupdf")
    # Don't sys.exit — we're run inside the launcher
    fitz = None

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
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

BOOKS_DIR = PROJECT_ROOT / "output" / "books"
OUTPUT_BASE = PROJECT_ROOT / "output" / "pdf_split"


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def sanitize_filename(name: str) -> str:
    """Remove characters not safe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = name.strip(". ")
    return name or "untitled"


# Windows MAX_PATH is 260; we leave headroom for the drive prefix, etc.
_MAX_PATH = 250


def _clamp_path_length(path: Path) -> Path:
    """
    If *path* would exceed _MAX_PATH on Windows, shorten the **stem**
    (filename without extension) so the full path fits.
    """
    full = str(path)
    if len(full) <= _MAX_PATH:
        return path
    overshoot = len(full) - _MAX_PATH
    stem = path.stem
    new_stem = stem[: max(10, len(stem) - overshoot - 3)] + "..."
    return path.with_name(new_stem + path.suffix)


def _truncate_slug(slug: str, max_len: int = 100) -> str:
    """Truncate a slug to *max_len* characters, keeping it readable."""
    if len(slug) <= max_len:
        return slug
    return slug[: max_len - 3].rstrip() + "..."


def _open_pdf(pdf_path: Path) -> "fitz.Document | None":
    """Open a PDF and return the document, or None on failure."""
    if fitz is None:
        print_error("PyMuPDF is not installed. Run: pip install pymupdf")
        return None
    try:
        doc = fitz.open(str(pdf_path))
        return doc
    except Exception as e:
        print_error(f"Could not open PDF: {e}")
        return None


def _save_page_range(
    doc: "fitz.Document",
    start: int,
    end: int,
    out_path: Path,
) -> bool:
    """
    Save pages [start, end] (1-indexed, inclusive) to a new PDF.
    Returns True on success.
    """
    try:
        new_doc = fitz.open()  # blank document
        # fitz uses 0-indexed pages
        new_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
        new_doc.save(str(out_path))
        new_doc.close()
        return True
    except Exception as e:
        print_error(f"Failed to save {out_path.name}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PDF PICKER (reused across all modes)
# ─────────────────────────────────────────────────────────────────────────────


def _list_pdfs() -> list[Path]:
    """Return all PDF files in the books directory."""
    if not BOOKS_DIR.exists():
        return []
    return sorted(BOOKS_DIR.glob("*.pdf"))


def _pick_pdf() -> Path | None:
    """Prompt user to select a PDF from the books directory."""
    pdfs = _list_pdfs()
    if not pdfs:
        print_error(f"No PDF files found in {BOOKS_DIR}")
        print_info("Place your PDF files in the above directory and try again.")
        return None

    table = Table(
        title="Available PDFs",
        border_style="bright_cyan",
        header_style="bold magenta",
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Filename", style="bold")
    table.add_column("Pages", justify="right", style="cyan")
    table.add_column("Size", justify="right", style="dim")

    page_counts = []
    for i, p in enumerate(pdfs, 1):
        size_mb = p.stat().st_size / (1024 * 1024)
        # Quick page count
        try:
            d = fitz.open(str(p))
            pages = len(d)
            d.close()
        except Exception:
            pages = "?"
        page_counts.append(pages)
        table.add_row(str(i), p.name, str(pages), f"{size_mb:.1f} MB")

    console.print()
    console.print(table)
    console.print()

    choice = Prompt.ask(
        "  [bold yellow]Select a PDF (number or name)[/bold yellow]",
        default="1",
    )

    # Numeric selection
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(pdfs):
            return pdfs[idx]
        print_error("Invalid number.")
        return None

    # Name match (partial, case-insensitive)
    choice_lower = choice.lower()
    matches = [p for p in pdfs if choice_lower in p.name.lower()]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print_warning("Multiple matches:")
        for m in matches:
            console.print(f"    {m.name}")
        print_error("Please be more specific.")
        return None
    else:
        print_error(f"No PDF matching '{choice}' found.")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# MODE 1 — Split by Page Range
# ─────────────────────────────────────────────────────────────────────────────


def _mode_page_range() -> None:
    """Extract a page range from a PDF into a new file."""
    console.print()
    print_banner("Split by Page Range", "Extract a range of pages into a new PDF")
    console.print()

    pdf_path = _pick_pdf()
    if not pdf_path:
        return

    doc = _open_pdf(pdf_path)
    if not doc:
        return

    total = len(doc)
    print_info(f"PDF has [bold]{total}[/bold] pages.")
    console.print()

    # Get page range
    range_str = Prompt.ask(
        "  [bold yellow]Enter page range (e.g. 1-50 or 10-25)[/bold yellow]"
    )

    # Parse range
    match = re.match(r"^\s*(\d+)\s*[-–]\s*(\d+)\s*$", range_str)
    if not match:
        print_error("Invalid range format. Use: START-END  (e.g. 1-50)")
        doc.close()
        return

    start, end = int(match.group(1)), int(match.group(2))

    if start < 1 or end > total or start > end:
        print_error(f"Range must be between 1 and {total}, with start ≤ end.")
        doc.close()
        return

    # Output filename
    default_name = f"{pdf_path.stem}_p{start}-{end}.pdf"
    out_name = Prompt.ask(
        "  [bold yellow]Output filename[/bold yellow]",
        default=default_name,
    )
    if not out_name.lower().endswith(".pdf"):
        out_name += ".pdf"

    out_dir = OUTPUT_BASE / sanitize_filename(pdf_path.stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / sanitize_filename(out_name)

    if _save_page_range(doc, start, end, out_path):
        print_success(
            f"Saved {end - start + 1} pages → [cyan]{out_path}[/cyan]"
        )
    doc.close()


# ─────────────────────────────────────────────────────────────────────────────
# MODE 2 — Manual Chapter Splitting
# ─────────────────────────────────────────────────────────────────────────────


def _mode_manual_chapters() -> None:
    """Let user define chapter ranges and split into individual PDFs."""
    console.print()
    print_banner(
        "Manual Chapter Splitting",
        "Define chapter page ranges → each becomes a separate PDF",
    )
    console.print()

    pdf_path = _pick_pdf()
    if not pdf_path:
        return

    doc = _open_pdf(pdf_path)
    if not doc:
        return

    total = len(doc)
    print_info(f"PDF has [bold]{total}[/bold] pages.")
    console.print()

    # Book name for output folder & file prefix
    default_book = pdf_path.stem.replace("_", " ")
    book_name = Prompt.ask(
        "  [bold yellow]Book name (used for folder & file naming)[/bold yellow]",
        default=default_book,
    )
    book_slug = _truncate_slug(sanitize_filename(book_name))

    # Collect chapter definitions
    chapters: list[dict] = []

    console.print()
    console.print(
        Panel(
            "[bold]Define your chapters below.[/bold]\n\n"
            "For each chapter, enter:\n"
            "  • Page range (e.g. [cyan]1-24[/cyan])\n"
            "  • An optional name (or leave blank for auto-naming)\n\n"
            "Type [bold red]done[/bold red] when finished.",
            title="Chapter Entry",
            border_style="bright_cyan",
            padding=(1, 3),
        )
    )
    console.print()

    idx = 0
    while True:
        range_str = Prompt.ask(
            f"  [bold cyan]Chapter {idx}[/bold cyan] page range (or 'done')"
        )
        if range_str.strip().lower() == "done":
            break

        match = re.match(r"^\s*(\d+)\s*[-–]\s*(\d+)\s*$", range_str)
        if not match:
            print_error("Invalid format. Use: START-END  (e.g. 1-50)")
            continue

        start, end = int(match.group(1)), int(match.group(2))
        if start < 1 or end > total or start > end:
            print_error(f"Range must be between 1 and {total}, with start ≤ end.")
            continue

        # Chapter name — auto-generate suffix based on index
        if idx == 0:
            default_suffix = "Index"
        else:
            default_suffix = f"Chapter {idx:02d}"

        ch_name = Prompt.ask(
            f"  [bold yellow]  Name for this section[/bold yellow]",
            default=default_suffix,
        )

        chapters.append({
            "index": idx,
            "start": start,
            "end": end,
            "name": ch_name.strip(),
        })
        idx += 1

    if not chapters:
        print_warning("No chapters defined. Aborting.")
        doc.close()
        return

    # Preview
    console.print()
    preview = Table(
        title=f'Chapters for "{book_name}"',
        border_style="bright_magenta",
        show_lines=True,
    )
    preview.add_column("#", style="dim", width=4)
    preview.add_column("Name", style="bold")
    preview.add_column("Pages", justify="center", style="cyan")
    preview.add_column("Output File", style="dim")

    for ch in chapters:
        filename = f"{book_slug} - {ch['name']}.pdf"
        preview.add_row(
            str(ch["index"]),
            ch["name"],
            f"{ch['start']}–{ch['end']}",
            filename,
        )

    console.print(preview)
    console.print()

    if not Confirm.ask("  [bold yellow]Proceed with splitting?[/bold yellow]", default=True):
        print_warning("Cancelled.")
        doc.close()
        return

    # Create output folder
    out_dir = OUTPUT_BASE / book_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # Split
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("[cyan]Splitting chapters...", total=len(chapters))

        for ch in chapters:
            filename = f"{book_slug} - {ch['name']}.pdf"
            out_path = _clamp_path_length(out_dir / sanitize_filename(filename))
            _save_page_range(doc, ch["start"], ch["end"], out_path)
            progress.advance(task_id)

    doc.close()

    console.print()
    console.print(
        Panel(
            f"[bold green]Done![/bold green]\n\n"
            f"  Output folder: [cyan]{out_dir}[/cyan]\n"
            f"  Files created: [bold]{len(chapters)}[/bold]",
            title="Split Complete",
            border_style="green",
            expand=False,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODE 3 — Auto Chapter Detection
# ─────────────────────────────────────────────────────────────────────────────


def _extract_toc(doc: "fitz.Document") -> list[tuple[int, str, int]]:
    """
    Extract the Table of Contents from the PDF.
    Returns list of (level, title, page_number) tuples.
    """
    toc = doc.get_toc(simple=False)
    result = []
    for entry in toc:
        if len(entry) >= 3:
            level, title, page = entry[0], entry[1], entry[2]
            result.append((int(level), str(title).strip(), int(page)))
    return result


def _group_top_level_chapters(
    toc: list[tuple[int, str, int]],
    total_pages: int,
) -> list[dict]:
    """
    Group TOC entries into top-level chapters.
    Each dict has: title, start_page, end_page
    """
    if not toc:
        return []

    min_level = min(e[0] for e in toc)
    top_entries = [(i, e) for i, e in enumerate(toc) if e[0] == min_level]
    chapters = []

    for k, (idx, entry) in enumerate(top_entries):
        _level, title, start_page = entry

        if k + 1 < len(top_entries):
            next_start = toc[top_entries[k + 1][0]][2]
            end_page = max(start_page, next_start - 1)
        else:
            end_page = total_pages

        chapters.append({
            "title": title,
            "start_page": max(1, start_page),
            "end_page": min(end_page, total_pages),
        })

    return chapters


def _mode_auto_chapters() -> None:
    """Detect chapters from PDF TOC and split automatically."""
    console.print()
    print_banner(
        "Auto Chapter Detection",
        "Detect chapters from the PDF's Table of Contents",
    )
    console.print()

    pdf_path = _pick_pdf()
    if not pdf_path:
        return

    doc = _open_pdf(pdf_path)
    if not doc:
        return

    total = len(doc)
    print_info(f"PDF has [bold]{total}[/bold] pages.")
    console.print()

    # Attempt TOC extraction
    toc = _extract_toc(doc)

    if not toc:
        console.print()
        console.print(
            Panel(
                "[bold red]Unable to identify chapters automatically.[/bold red]\n\n"
                "This PDF does not contain an embedded Table of Contents (outline / bookmarks).\n"
                "Not all PDFs have this metadata — it depends on how the PDF was created.\n\n"
                "[dim]Suggestions:[/dim]\n"
                "  • Use [bold cyan]Manual Chapter Splitting[/bold cyan] (Mode 2) instead.\n"
                "  • Use [bold cyan]Page Range Split[/bold cyan] (Mode 1) for quick extraction.",
                title="⚠  Auto-Detection Failed",
                border_style="red",
                padding=(1, 3),
            )
        )
        doc.close()
        return

    # Group into chapters
    chapters = _group_top_level_chapters(toc, total)
    if not chapters:
        print_error("Could not group TOC entries into chapters.")
        doc.close()
        return

    # Show detected chapters
    console.print()
    table = Table(
        title="Detected Chapters",
        border_style="bright_green",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold")
    table.add_column("Pages", justify="center", style="cyan")
    table.add_column("Page Count", justify="right", style="dim")

    for i, ch in enumerate(chapters):
        count = ch["end_page"] - ch["start_page"] + 1
        table.add_row(
            str(i),
            ch["title"],
            f"{ch['start_page']}–{ch['end_page']}",
            str(count),
        )

    console.print(table)
    console.print()
    print_info(f"Found [bold]{len(chapters)}[/bold] top-level chapters.")
    console.print()

    if not Confirm.ask(
        "  [bold yellow]Split PDF using these chapters?[/bold yellow]",
        default=True,
    ):
        print_warning("Cancelled.")
        doc.close()
        return

    # Book name
    default_book = pdf_path.stem.replace("_", " ")
    book_name = Prompt.ask(
        "  [bold yellow]Book name (for folder & file prefix)[/bold yellow]",
        default=default_book,
    )
    book_slug = _truncate_slug(sanitize_filename(book_name))

    # Create output folder
    out_dir = OUTPUT_BASE / book_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # Split
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("[cyan]Splitting chapters...", total=len(chapters))

        for i, ch in enumerate(chapters):
            # Build filename: BookName - Index/Chapter ##.pdf
            if i == 0 and ch["title"].lower() in (
                "contents", "table of contents", "preface",
                "foreword", "introduction", "front matter", "index",
            ):
                suffix = "Index"
            else:
                ch_title = sanitize_filename(ch["title"])
                # Truncate long titles
                if len(ch_title) > 60:
                    ch_title = ch_title[:57] + "..."
                suffix = f"Chapter {i:02d} - {ch_title}"

            filename = f"{book_slug} - {suffix}.pdf"
            out_path = _clamp_path_length(out_dir / sanitize_filename(filename))
            _save_page_range(doc, ch["start_page"], ch["end_page"], out_path)
            progress.advance(task_id)

    doc.close()

    console.print()
    console.print(
        Panel(
            f"[bold green]Done![/bold green]\n\n"
            f"  Output folder: [cyan]{out_dir}[/cyan]\n"
            f"  Files created: [bold]{len(chapters)}[/bold]",
            title="Auto-Split Complete",
            border_style="green",
            expand=False,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN MENU
# ─────────────────────────────────────────────────────────────────────────────


def run() -> None:
    """Entry point — called by main.py launcher or standalone."""
    # Ensure directories exist
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

    while True:
        console.print()
        console.print(
            Panel(
                "[bold magenta]PDF Splitter[/bold magenta]\n"
                "[dim]Split PDFs into smaller portions[/dim]\n\n"
                f"[dim]Source folder:[/dim] [cyan]{BOOKS_DIR}[/cyan]\n"
                f"[dim]Output folder:[/dim] [cyan]{OUTPUT_BASE}[/cyan]",
                border_style="bright_magenta",
                expand=False,
            )
        )
        console.print()

        console.print(
            Panel(
                "[bold cyan]1[/]  Split by Page Range       [dim]— extract pages into a single PDF[/dim]\n"
                "[bold cyan]2[/]  Manual Chapter Splitting  [dim]— define chapter ranges yourself[/dim]\n"
                "[bold cyan]3[/]  Auto Chapter Detection    [dim]— detect chapters from TOC metadata[/dim]\n"
                "[bold cyan]0[/]  Back",
                title="[bold]Split Mode[/bold]",
                border_style="bright_cyan",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask(
            "  Choice",
            choices=["0", "1", "2", "3"],
            default="1",
        )

        if choice == "0":
            break
        elif choice == "1":
            _mode_page_range()
        elif choice == "2":
            _mode_manual_chapters()
        elif choice == "3":
            _mode_auto_chapters()


if __name__ == "__main__":
    run()
