"""
ZIP → PDF Converter
===================
A polished utility to convert every ZIP file in a specified directory into
a PDF file with its respective name (e.g., 'archive.zip' -> 'archive.pdf').

Features:
    - Scans a directory and converts all .zip files into .pdf files
    - Handles images (.png, .jpg, .jpeg, .webp, .bmp, .tiff, .gif) with natural sorting
    - Handles embedded PDF files (.pdf) by merging them into the final document
    - Handles text / markdown files (.txt, .md, .log) by formatting into pages
    - Recursive directory scan option (--recursive / -r)
    - Optional custom output directory (--output-dir / -o)
    - Memory-efficient streaming extraction with temp directory isolation
    - Error resilience: corrupt or non-convertible zips are skipped without halting batch
    - Dual Interface:
        1. Rich interactive TUI / CLI with progress bars and summary table
        2. Modern dark-themed Tkinter GUI with Drag-and-Drop and folder picker
    - Seamless integration with the 98_PYTHON toolkit

Entry points:
    run()   — launched from converter/main.py or project main.py
    main()  — CLI entry point (supports arguments or interactive mode)
"""

import argparse
import gc
import os
import re
import sys
import time
import shutil
import zipfile
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Try PyMuPDF
try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] PyMuPDF is required. Install with: pip install pymupdf")
    sys.exit(1)

# Try Rich components
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeElapsedColumn,
        TaskProgressColumn,
    )
    from shared.console import (
        console,
        print_banner,
        print_success,
        print_error,
        print_warning,
        print_info,
    )
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False
    class DummyConsole:
        def print(self, *args, **kwargs):
            print(*args)
    console = DummyConsole()
    def print_success(msg: str): print(f"[+] {msg}")
    def print_error(msg: str): print(f"[!] {msg}")
    def print_warning(msg: str): print(f"[*] {msg}")
    def print_info(msg: str): print(f"[>] {msg}")
    def print_banner(title: str, subtitle: str = ""):
        print(f"=== {title} ===\n{subtitle}")

# Tkinter & Drag-and-Drop
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _HAS_DND = True
except ImportError:
    _HAS_DND = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif"}
PDF_EXTENSIONS = {".pdf"}
TEXT_EXTENSIONS = {".txt", ".md", ".log", ".json", ".py", ".html", ".csv", ".xml"}
ALL_SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS | TEXT_EXTENSIONS

GC_INTERVAL = 15  # Garbage collect every N pages
DEFAULT_PAGE_WIDTH = 595   # A4 width in pt
DEFAULT_PAGE_HEIGHT = 842  # A4 height in pt

# GUI Palette — sleek dark theme
BG_PRIMARY = "#0f0f14"
BG_SECONDARY = "#16161e"
BG_CARD = "#1e1e2e"
BG_INPUT = "#24243a"
FG_PRIMARY = "#e0e0f0"
FG_SECONDARY = "#8888aa"
FG_MUTED = "#555570"
ACCENT = "#7c6ff7"
ACCENT_HOVER = "#9b8aff"
ACCENT_GLOW = "#6655cc"
SUCCESS = "#44dd88"
ERROR = "#ff5577"
WARNING_CLR = "#ffaa44"
BORDER = "#2a2a40"
DROP_ZONE_BG = "#1a1a2a"
DROP_ZONE_ACTIVE = "#252540"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _natural_sort_key(s: str) -> list:
    """Sort key that handles embedded numbers naturally (page2 < page10)."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", s)
    ]


def _human_size(nbytes: int | float) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _is_system_junk(filename: str) -> bool:
    """Filter out OS metadata files like __MACOSX, .DS_Store, Thumbs.db."""
    parts = Path(filename).parts
    for part in parts:
        if part.startswith(".") or part in ("__MACOSX", "Thumbs.db", "desktop.ini"):
            return True
    return False


@dataclass
class ConversionResult:
    zip_path: Path
    pdf_path: Optional[Path]
    status: str  # "success", "skipped", "error"
    pages: int = 0
    size_bytes: int = 0
    error_message: str = ""
    duration: float = 0.0


# ---------------------------------------------------------------------------
# Core Conversion Engine
# ---------------------------------------------------------------------------
def _format_text_to_pdf(pdf_doc: fitz.Document, text_content: str, source_name: str) -> int:
    """Format plain text content across one or more pages in the PDF document."""
    lines = text_content.replace("\r\n", "\n").split("\n")
    margin_x = 40
    margin_y = 50
    content_width = DEFAULT_PAGE_WIDTH - (margin_x * 2)
    content_height = DEFAULT_PAGE_HEIGHT - (margin_y * 2)
    
    font_size = 9
    line_spacing = font_size * 1.35
    max_lines_per_page = int((content_height - 30) // line_spacing)
    
    chunk = []
    pages_created = 0

    for line in lines:
        max_chars = int(content_width / (font_size * 0.55))
        if len(line) > max_chars:
            for i in range(0, len(line), max_chars):
                chunk.append(line[i:i + max_chars])
        else:
            chunk.append(line)

    if not chunk:
        chunk = ["[Empty File]"]

    for i in range(0, len(chunk), max_lines_per_page):
        page_lines = chunk[i:i + max_lines_per_page]
        page = pdf_doc.new_page(width=DEFAULT_PAGE_WIDTH, height=DEFAULT_PAGE_HEIGHT)
        
        page.insert_text(
            (margin_x, margin_y - 15),
            f"{source_name} (Part {pages_created + 1})",
            fontsize=8,
            color=(0.4, 0.4, 0.5),
        )
        
        text_body = "\n".join(page_lines)
        rect = fitz.Rect(margin_x, margin_y, margin_x + content_width, margin_y + content_height)
        page.insert_textbox(rect, text_body, fontsize=font_size, fontname="courier", color=(0.15, 0.15, 0.15))
        pages_created += 1

    return pages_created


def convert_single_zip_to_pdf(
    zip_path: Path,
    output_dir: Optional[Path] = None,
    overwrite: bool = True,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_flag: Optional[threading.Event] = None,
) -> ConversionResult:
    """
    Convert a single ZIP file into a PDF file named <zip_path.stem>.pdf.

    Extracts images, embedded PDFs, and text documents in natural order,
    compiling them into a single multi-page PDF document.

    Parameters:
        zip_path: Path to the .zip archive.
        output_dir: Destination folder (defaults to zip_path.parent).
        overwrite: Overwrite existing target PDF if True.
        progress_cb: Callback (current_step, total_steps, current_item_name).
        cancel_flag: threading.Event to abort conversion mid-process.

    Returns:
        ConversionResult detailing outcome, page count, and performance.
    """
    start_time = time.time()
    zip_path = Path(zip_path).resolve()
    
    if output_dir is None:
        target_dir = zip_path.parent
    else:
        target_dir = Path(output_dir).resolve()
    
    target_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = target_dir / f"{zip_path.stem}.pdf"

    if pdf_path.exists() and not overwrite:
        return ConversionResult(
            zip_path=zip_path,
            pdf_path=pdf_path,
            status="skipped",
            pages=0,
            size_bytes=pdf_path.stat().st_size,
            error_message="Target PDF already exists (overwrite=False)",
            duration=time.time() - start_time,
        )

    # Check valid zip archive
    if not zipfile.is_zipfile(zip_path):
        return ConversionResult(
            zip_path=zip_path,
            pdf_path=None,
            status="error",
            error_message="Not a valid or readable ZIP file",
            duration=time.time() - start_time,
        )

    tmp_dir = tempfile.mkdtemp(prefix="zip2pdf_")
    pdf_doc = fitz.open()

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            all_entries = zf.namelist()
            
            # Filter and naturally sort supported files
            valid_entries = [
                n for n in all_entries
                if not _is_system_junk(n)
                and not n.endswith("/")
                and Path(n).suffix.lower() in ALL_SUPPORTED_EXTENSIONS
            ]
            valid_entries.sort(key=_natural_sort_key)

            if not valid_entries:
                return ConversionResult(
                    zip_path=zip_path,
                    pdf_path=None,
                    status="skipped",
                    error_message="No supported images, PDFs, or documents found in ZIP",
                    duration=time.time() - start_time,
                )

            total_items = len(valid_entries)
            total_pages = 0

            for idx, entry_name in enumerate(valid_entries):
                if cancel_flag and cancel_flag.is_set():
                    pdf_doc.close()
                    raise InterruptedError("Operation cancelled by user")

                entry_ext = Path(entry_name).suffix.lower()
                safe_name = f"item_{idx:05d}{entry_ext}"
                tmp_file = os.path.join(tmp_dir, safe_name)

                if progress_cb:
                    progress_cb(idx + 1, total_items, Path(entry_name).name)

                try:
                    data = zf.read(entry_name)
                    with open(tmp_file, "wb") as f:
                        f.write(data)
                    del data
                except Exception:
                    # Skip unreadable single entry
                    continue

                # Process based on type
                try:
                    if entry_ext in IMAGE_EXTENSIONS:
                        img_doc = fitz.open(tmp_file)
                        rect = img_doc[0].rect
                        img_doc.close()
                        del img_doc

                        page = pdf_doc.new_page(width=rect.width, height=rect.height)
                        page.insert_image(rect, filename=tmp_file)
                        total_pages += 1

                    elif entry_ext in PDF_EXTENSIONS:
                        sub_pdf = fitz.open(tmp_file)
                        total_pages += len(sub_pdf)
                        pdf_doc.insert_pdf(sub_pdf)
                        sub_pdf.close()
                        del sub_pdf

                    elif entry_ext in TEXT_EXTENSIONS:
                        with open(tmp_file, "r", encoding="utf-8", errors="replace") as tf:
                            text_str = tf.read()
                        text_pages = _format_text_to_pdf(pdf_doc, text_str, Path(entry_name).name)
                        total_pages += text_pages

                except Exception:
                    pass  # Skip corrupted individual item
                finally:
                    try:
                        if os.path.exists(tmp_file):
                            os.remove(tmp_file)
                    except OSError:
                        pass

                if idx % GC_INTERVAL == 0:
                    gc.collect()

            if total_pages == 0:
                pdf_doc.close()
                return ConversionResult(
                    zip_path=zip_path,
                    pdf_path=None,
                    status="error",
                    error_message="All files in archive were unreadable or corrupt",
                    duration=time.time() - start_time,
                )

            # Save the final PDF with compression
            pdf_doc.save(
                str(pdf_path),
                garbage=3,
                deflate=True,
                clean=True,
            )
            pdf_doc.close()

            file_size = pdf_path.stat().st_size if pdf_path.exists() else 0
            return ConversionResult(
                zip_path=zip_path,
                pdf_path=pdf_path,
                status="success",
                pages=total_pages,
                size_bytes=file_size,
                duration=time.time() - start_time,
            )

    except InterruptedError:
        raise
    except Exception as e:
        return ConversionResult(
            zip_path=zip_path,
            pdf_path=None,
            status="error",
            error_message=str(e),
            duration=time.time() - start_time,
        )
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except OSError:
            pass
        gc.collect()


def collect_zip_files(directory: Path, recursive: bool = False) -> List[Path]:
    """Discover all .zip files in the given directory."""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        return []

    if recursive:
        pattern = "**/*.zip"
    else:
        pattern = "*.zip"

    zips = [p for p in directory.glob(pattern) if p.is_file() and not p.name.startswith(".")]
    zips.sort(key=lambda p: _natural_sort_key(p.name))
    return zips


def convert_zip_directory(
    directory: Path,
    output_dir: Optional[Path] = None,
    recursive: bool = False,
    overwrite: bool = True,
    delete_zip: bool = False,
    batch_cb: Optional[Callable[[int, int, Path, Optional[ConversionResult]], None]] = None,
    file_progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_flag: Optional[threading.Event] = None,
) -> List[ConversionResult]:
    """
    Batch converts every .zip file in `directory` to a corresponding .pdf.

    Parameters:
        directory: Directory containing .zip files.
        output_dir: Optional custom output folder.
        recursive: If True, searches subdirectories recursively.
        overwrite: If True, overwrites existing .pdf files.
        delete_zip: If True, deletes original .zip file upon successful conversion.
        batch_cb: Callback (zip_index, total_zips, current_zip_path, result_or_none).
        file_progress_cb: Callback for inner pages of current archive.
        cancel_flag: Cancel event flag.

    Returns:
        List of ConversionResult for each zip file found.
    """
    zip_files = collect_zip_files(directory, recursive=recursive)
    total_zips = len(zip_files)
    results: List[ConversionResult] = []

    for idx, zip_p in enumerate(zip_files):
        if cancel_flag and cancel_flag.is_set():
            break

        if batch_cb:
            batch_cb(idx + 1, total_zips, zip_p, None)

        res = convert_single_zip_to_pdf(
            zip_p,
            output_dir=output_dir,
            overwrite=overwrite,
            progress_cb=file_progress_cb,
            cancel_flag=cancel_flag,
        )
        results.append(res)

        if res.status == "success" and delete_zip:
            try:
                zip_p.unlink()
            except OSError:
                pass

        if batch_cb:
            batch_cb(idx + 1, total_zips, zip_p, res)

    return results


# ---------------------------------------------------------------------------
# Rich CLI / TUI
# ---------------------------------------------------------------------------
def run_cli_batch(
    directory: Path,
    output_dir: Optional[Path] = None,
    recursive: bool = False,
    overwrite: bool = True,
    delete_zip: bool = False,
) -> None:
    """Execute batch conversion from the CLI with styled progress and output."""
    directory = Path(directory).resolve()
    if not directory.is_dir():
        print_error(f"Directory not found: '{directory}'")
        return

    zip_files = collect_zip_files(directory, recursive=recursive)
    if not zip_files:
        print_warning(f"No .zip files found in '{directory}'.")
        return

    print_banner(
        "ZIP → PDF BATCH CONVERTER",
        f"Directory: {directory} | Total Archives: {len(zip_files)}",
    )

    console.print(f"  [info][>][/info] Found [highlight]{len(zip_files)}[/highlight] ZIP file(s).")
    if output_dir:
        console.print(f"  [info][>][/info] Output directory: [highlight]{output_dir}[/highlight]")
    else:
        console.print("  [info][>][/info] Output directory: [highlight]Same folder as source ZIPs[/highlight]")
    console.print(f"  [info][>][/info] Overwrite existing: [highlight]{overwrite}[/highlight]")
    console.print()

    start_batch_time = time.time()
    results: List[ConversionResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40, complete_style="cyan", finished_style="green"),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        batch_task = progress.add_task("[bold cyan]Total Batch Progress", total=len(zip_files))
        current_task = progress.add_task("[dim]Preparing...", total=100)

        def batch_update(curr_idx, total, zip_path, res):
            if res is None:
                progress.update(
                    batch_task,
                    completed=curr_idx - 1,
                    description=f"[bold cyan]Converting [{curr_idx}/{total}]: {zip_path.name}",
                )
                progress.update(current_task, completed=0, total=100, description="[dim]Reading archive...")
            else:
                progress.update(batch_task, completed=curr_idx)

        def file_update(curr, total, item_name):
            progress.update(
                current_task,
                completed=curr,
                total=total,
                description=f"[magenta]Parsing: {item_name[:25]} ({curr}/{total})",
            )

        try:
            results = convert_zip_directory(
                directory=directory,
                output_dir=output_dir,
                recursive=recursive,
                overwrite=overwrite,
                delete_zip=delete_zip,
                batch_cb=batch_update,
                file_progress_cb=file_update,
            )
        except KeyboardInterrupt:
            console.print("\n  [warning][*][/warning] Batch conversion interrupted by user.")
            return

    elapsed_total = time.time() - start_batch_time
    success_count = sum(1 for r in results if r.status == "success")
    skip_count = sum(1 for r in results if r.status == "skipped")
    err_count = sum(1 for r in results if r.status == "error")

    console.print()
    table = Table(title="Conversion Summary", border_style="bright_magenta", header_style="bold cyan")
    table.add_column("ZIP Archive", style="white", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Pages", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("Time", justify="right")
    table.add_column("Details", style="dim")

    for r in results:
        if r.status == "success":
            status_txt = "[bold green]OK[/bold green]"
            details = f"Saved as {r.pdf_path.name}" if r.pdf_path else ""
        elif r.status == "skipped":
            status_txt = "[bold yellow]SKIPPED[/bold yellow]"
            details = r.error_message
        else:
            status_txt = "[bold red]ERROR[/bold red]"
            details = r.error_message

        table.add_row(
            r.zip_path.name,
            status_txt,
            str(r.pages) if r.pages else "-",
            _human_size(r.size_bytes) if r.size_bytes else "-",
            f"{r.duration:.2f}s",
            details,
        )

    console.print(table)
    console.print()

    summary_msg = (
        f"[bold green]{success_count} Converted[/bold green] | "
        f"[bold yellow]{skip_count} Skipped[/bold yellow] | "
        f"[bold red]{err_count} Failed[/bold red] | "
        f"Elapsed: [bold cyan]{elapsed_total:.2f}s[/bold cyan]"
    )
    console.print(Panel(summary_msg, border_style="bright_magenta", padding=(0, 2)))


def run_interactive_tui() -> None:
    """Interactive Rich TUI menu."""
    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  Convert Directory of ZIPs (CLI Mode)\n"
                "[bold cyan]2[/]  Launch Graphical GUI (Drag-and-Drop)\n"
                "[bold cyan]0[/]  Back to Previous Menu",
                title="[bold bright_magenta]ZIP → PDF Converter[/bold bright_magenta]",
                border_style="bright_magenta",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask("  Choice", choices=["0", "1", "2"], default="1")
        if choice == "0":
            break
        elif choice == "2":
            run_gui()
            break
        elif choice == "1":
            path_input = Prompt.ask("  Enter directory containing .zip files").strip(' "\'')
            if not path_input:
                print_warning("No directory entered.")
                continue

            target_path = Path(path_input)
            if not target_path.is_dir():
                print_error(f"Directory not found: '{target_path}'")
                continue

            recursive = Confirm.ask("  Scan subdirectories recursively?", default=False)
            custom_out = Confirm.ask("  Specify custom output directory?", default=False)
            out_path = None
            if custom_out:
                out_input = Prompt.ask("  Enter output directory").strip(' "\'')
                if out_input:
                    out_path = Path(out_input)

            overwrite = Confirm.ask("  Overwrite existing PDF files?", default=True)

            run_cli_batch(
                directory=target_path,
                output_dir=out_path,
                recursive=recursive,
                overwrite=overwrite,
            )
            Prompt.ask("\n  Press Enter to continue...")


# ---------------------------------------------------------------------------
# Dark-Themed GUI with Drag-and-Drop
# ---------------------------------------------------------------------------
class ZipToPdfApp:
    """Modern, dark-themed Tkinter GUI for batch ZIP to PDF conversion."""

    def __init__(self, root: Optional[tk.Tk] = None):
        if root is None:
            if _HAS_DND:
                self.root = TkinterDnD.Tk()
            else:
                self.root = tk.Tk()
        else:
            self.root = root

        self.root.title("ZIP → PDF Converter")
        self.root.configure(bg=BG_PRIMARY)
        self.root.resizable(False, False)

        width, height = 740, 680
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        self._pending_zips: List[Path] = []
        self._output_dir: Optional[Path] = None
        self._is_converting = False
        self._cancel_event = threading.Event()

        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=BG_PRIMARY)
        style.configure("Card.TFrame", background=BG_CARD, relief="flat")
        style.configure("TLabel", background=BG_PRIMARY, foreground=FG_PRIMARY, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG_PRIMARY, foreground=FG_PRIMARY, font=("Segoe UI", 17, "bold"))
        style.configure("Subtitle.TLabel", background=BG_PRIMARY, foreground=FG_SECONDARY, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=BG_PRIMARY, foreground=FG_SECONDARY, font=("Segoe UI", 9))
        style.configure("Success.TLabel", background=BG_PRIMARY, foreground=SUCCESS, font=("Segoe UI", 9, "bold"))
        style.configure("Error.TLabel", background=BG_PRIMARY, foreground=ERROR, font=("Segoe UI", 9, "bold"))
        style.configure("Warning.TLabel", background=BG_PRIMARY, foreground=WARNING_CLR, font=("Segoe UI", 9))

        style.configure(
            "Batch.Horizontal.TProgressbar",
            troughcolor=BG_INPUT,
            background=ACCENT,
            darkcolor=ACCENT,
            lightcolor=ACCENT_HOVER,
            bordercolor=BG_PRIMARY,
            thickness=10,
        )
        style.configure(
            "File.Horizontal.TProgressbar",
            troughcolor=BG_INPUT,
            background=ACCENT_GLOW,
            darkcolor=ACCENT_GLOW,
            lightcolor=ACCENT,
            bordercolor=BG_PRIMARY,
            thickness=6,
        )

    def _build_ui(self):
        container = ttk.Frame(self.root, style="TFrame")
        container.pack(fill="both", expand=True, padx=24, pady=18)

        # Header
        ttk.Label(container, text="ZIP → PDF Converter", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Convert every ZIP archive into a corresponding PDF with matching names.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 14))

        # Drop Zone
        self._drop_frame = tk.Frame(
            container,
            bg=DROP_ZONE_BG,
            highlightbackground=BORDER,
            highlightthickness=2,
            cursor="hand2",
        )
        self._drop_frame.pack(fill="x", ipady=20)

        self._drop_icon = tk.Label(self._drop_frame, text="📦", font=("Segoe UI Emoji", 26), bg=DROP_ZONE_BG, fg=FG_PRIMARY)
        self._drop_icon.pack(pady=(6, 2))

        self._drop_label = tk.Label(
            self._drop_frame,
            text="Drop Folder with ZIP Files Here",
            font=("Segoe UI", 11, "bold"),
            bg=DROP_ZONE_BG,
            fg=FG_PRIMARY,
        )
        self._drop_label.pack()

        hint_text = "or click to select directory" + ("" if _HAS_DND else " (DND disabled)")
        self._drop_hint = tk.Label(self._drop_frame, text=hint_text, font=("Segoe UI", 9), bg=DROP_ZONE_BG, fg=FG_MUTED)
        self._drop_hint.pack(pady=(2, 6))

        for widget in (self._drop_frame, self._drop_icon, self._drop_label, self._drop_hint):
            widget.bind("<Button-1>", lambda e: self._choose_directory())

        if _HAS_DND:
            self._drop_frame.drop_target_register(DND_FILES)
            self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)
            self._drop_frame.dnd_bind("<<DragEnter>>", lambda e: self._drop_frame.configure(bg=DROP_ZONE_ACTIVE))
            self._drop_frame.dnd_bind("<<DragLeave>>", lambda e: self._drop_frame.configure(bg=DROP_ZONE_BG))

        # Output folder options
        opt_card = ttk.Frame(container, style="Card.TFrame")
        opt_card.pack(fill="x", pady=12, ipady=6, ipadx=10)

        out_row = tk.Frame(opt_card, bg=BG_CARD)
        out_row.pack(fill="x", padx=10, pady=4)

        tk.Label(out_row, text="Output Directory:", font=("Segoe UI", 9, "bold"), bg=BG_CARD, fg=FG_PRIMARY).pack(side="left")
        self._out_dir_label = tk.Label(out_row, text="Same as source ZIPs", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_SECONDARY)
        self._out_dir_label.pack(side="left", padx=8)

        btn_browse_out = tk.Button(
            out_row,
            text="Change...",
            font=("Segoe UI", 8),
            bg=BG_INPUT,
            fg=FG_PRIMARY,
            activebackground=BORDER,
            activeforeground=FG_PRIMARY,
            relief="flat",
            cursor="hand2",
            command=self._choose_output_dir,
        )
        btn_browse_out.pack(side="right")

        btn_reset_out = tk.Button(
            out_row,
            text="Reset",
            font=("Segoe UI", 8),
            bg=BG_INPUT,
            fg=FG_MUTED,
            activebackground=BORDER,
            relief="flat",
            cursor="hand2",
            command=self._reset_output_dir,
        )
        btn_reset_out.pack(side="right", padx=6)

        # File List Section
        list_header = tk.Frame(container, bg=BG_PRIMARY)
        list_header.pack(fill="x", pady=(4, 2))

        self._list_title = tk.Label(
            list_header,
            text="Discovered ZIP Archives (0)",
            font=("Segoe UI", 10, "bold"),
            bg=BG_PRIMARY,
            fg=FG_PRIMARY,
        )
        self._list_title.pack(side="left")

        btn_clear = tk.Button(
            list_header,
            text="Clear List",
            font=("Segoe UI", 8),
            bg=BG_PRIMARY,
            fg=FG_MUTED,
            relief="flat",
            cursor="hand2",
            command=self._clear_list,
        )
        btn_clear.pack(side="right")

        list_frame = tk.Frame(container, bg=BORDER)
        list_frame.pack(fill="both", expand=True, pady=4)

        self._listbox = tk.Listbox(
            list_frame,
            bg=BG_CARD,
            fg=FG_PRIMARY,
            selectbackground=BG_INPUT,
            selectforeground=FG_PRIMARY,
            font=("Segoe UI", 9),
            relief="flat",
            highlightthickness=0,
            activestyle="none",
        )
        self._listbox.pack(side="left", fill="both", expand=True, padx=1, pady=1)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self._listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self._listbox.configure(yscrollcommand=scrollbar.set)

        # Progress Section
        self._batch_progress_var = tk.DoubleVar(value=0)
        self._batch_pb = ttk.Progressbar(
            container,
            orient="horizontal",
            mode="determinate",
            variable=self._batch_progress_var,
            style="Batch.Horizontal.TProgressbar",
        )
        self._batch_pb.pack(fill="x", pady=(8, 2))

        self._file_progress_var = tk.DoubleVar(value=0)
        self._file_pb = ttk.Progressbar(
            container,
            orient="horizontal",
            mode="determinate",
            variable=self._file_progress_var,
            style="File.Horizontal.TProgressbar",
        )
        self._file_pb.pack(fill="x", pady=(0, 6))

        # Bottom Bar: Status + Action Buttons
        bottom_bar = tk.Frame(container, bg=BG_PRIMARY)
        bottom_bar.pack(fill="x", pady=(4, 0))

        self._status_label = ttk.Label(bottom_bar, text="Ready. Choose or drop a folder.", style="Status.TLabel")
        self._status_label.pack(side="left", fill="x", expand=True)

        self._btn_cancel = tk.Button(
            bottom_bar,
            text="Cancel",
            font=("Segoe UI", 10, "bold"),
            bg="#3a1c22",
            fg=ERROR,
            activebackground="#4a202a",
            relief="flat",
            padx=14,
            pady=4,
            cursor="hand2",
            command=self._cancel_conversion,
        )

        self._btn_convert = tk.Button(
            bottom_bar,
            text="Convert to PDF",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT,
            fg="#ffffff",
            activebackground=ACCENT_HOVER,
            relief="flat",
            padx=18,
            pady=5,
            cursor="hand2",
            command=self._start_conversion,
        )
        self._btn_convert.pack(side="right")

    # GUI Event Handlers
    def _on_drop(self, event):
        self._drop_frame.configure(bg=DROP_ZONE_BG)
        raw_data = event.data
        if not raw_data:
            return

        paths = []
        pattern = r"\{([^}]+)\}|(\S+)"
        for match in re.finditer(pattern, raw_data):
            p_str = match.group(1) or match.group(2)
            if p_str:
                paths.append(Path(p_str))

        self._process_incoming_paths(paths)

    def _choose_directory(self):
        folder = filedialog.askdirectory(title="Select Folder Containing ZIP Files")
        if folder:
            self._process_incoming_paths([Path(folder)])

    def _choose_output_dir(self):
        folder = filedialog.askdirectory(title="Select Output Folder for PDFs")
        if folder:
            self._output_dir = Path(folder)
            self._out_dir_label.configure(text=str(self._output_dir))

    def _reset_output_dir(self):
        self._output_dir = None
        self._out_dir_label.configure(text="Same as source ZIPs")

    def _process_incoming_paths(self, paths: List[Path]):
        found_zips = []
        for p in paths:
            if p.is_dir():
                found_zips.extend(collect_zip_files(p, recursive=False))
            elif p.is_file() and p.suffix.lower() == ".zip":
                found_zips.append(p)

        new_count = 0
        existing = set(self._pending_zips)
        for z in found_zips:
            if z not in existing:
                self._pending_zips.append(z)
                existing.add(z)
                new_count += 1

        self._refresh_listbox()
        self._set_status(f"Added {new_count} archive(s). Total: {len(self._pending_zips)}")

    def _refresh_listbox(self):
        self._listbox.delete(0, tk.END)
        for z in self._pending_zips:
            size_str = _human_size(z.stat().st_size) if z.exists() else "?"
            self._listbox.insert(tk.END, f"  📦  {z.name}  ({size_str})")
        self._list_title.configure(text=f"Discovered ZIP Archives ({len(self._pending_zips)})")

    def _clear_list(self):
        if self._is_converting:
            return
        self._pending_zips.clear()
        self._refresh_listbox()
        self._set_status("List cleared.")

    def _set_status(self, text: str, success: bool = False, error: bool = False, warning: bool = False):
        if success:
            self._status_label.configure(text=text, style="Success.TLabel")
        elif error:
            self._status_label.configure(text=text, style="Error.TLabel")
        elif warning:
            self._status_label.configure(text=text, style="Warning.TLabel")
        else:
            self._status_label.configure(text=text, style="Status.TLabel")

    def _start_conversion(self):
        if not self._pending_zips:
            messagebox.showinfo("No ZIPs", "Please drop or select a folder containing .zip files first.")
            return

        self._is_converting = True
        self._cancel_event.clear()
        self._btn_convert.pack_forget()
        self._btn_cancel.pack(side="right")

        thread = threading.Thread(target=self._worker_thread, daemon=True)
        thread.start()

    def _cancel_conversion(self):
        if self._is_converting:
            self._cancel_event.set()
            self._set_status("Cancelling batch conversion...", warning=True)

    def _worker_thread(self):
        total_zips = len(self._pending_zips)
        success_count = 0
        fail_count = 0
        start_t = time.time()

        for idx, zip_p in enumerate(self._pending_zips):
            if self._cancel_event.is_set():
                break

            batch_pct = (idx / total_zips) * 100
            self.root.after(0, self._batch_progress_var.set, batch_pct)
            self.root.after(0, self._set_status, f"Converting [{idx + 1}/{total_zips}]: {zip_p.name}...")

            def inner_prog(curr, total, name):
                if total > 0:
                    self.root.after(0, self._file_progress_var.set, (curr / total) * 100)

            res = convert_single_zip_to_pdf(
                zip_p,
                output_dir=self._output_dir,
                overwrite=True,
                progress_cb=inner_prog,
                cancel_flag=self._cancel_event,
            )

            if res.status == "success":
                success_count += 1
                self.root.after(0, self._listbox.itemconfig, idx, {"fg": SUCCESS})
            else:
                fail_count += 1
                self.root.after(0, self._listbox.itemconfig, idx, {"fg": ERROR})

        elapsed = time.time() - start_t
        self.root.after(0, self._finish_batch, success_count, fail_count, elapsed)

    def _finish_batch(self, success_count: int, fail_count: int, elapsed: float):
        self._is_converting = False
        self._btn_cancel.pack_forget()
        self._btn_convert.pack(side="right")

        if self._cancel_event.is_set():
            self._batch_progress_var.set(0)
            self._file_progress_var.set(0)
            self._set_status(f"Cancelled — {success_count} converted before stop.", warning=True)
        else:
            self._batch_progress_var.set(100)
            self._file_progress_var.set(100)
            if fail_count == 0:
                self._set_status(f"Done! {success_count} ZIP(s) converted in {elapsed:.1f}s.", success=True)
            else:
                self._set_status(f"Completed with issues: {success_count} OK, {fail_count} failed ({elapsed:.1f}s).", warning=True)

    def mainloop(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# App Launchers / Entry Points
# ---------------------------------------------------------------------------
def run_gui():
    """Launch the Tkinter GUI interface."""
    app = ZipToPdfApp()
    app.mainloop()


def run():
    """Entry point for the project's central menu launcher."""
    run_interactive_tui()


def main():
    """CLI & Direct execution entry point."""
    parser = argparse.ArgumentParser(
        description="Convert every ZIP archive in a directory to a PDF with its respective name."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=None,
        help="Path to directory containing .zip files.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="Optional destination folder for the generated PDFs.",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Search for .zip files recursively in subdirectories.",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Skip conversion if target PDF already exists.",
    )
    parser.add_argument(
        "--delete-zip",
        action="store_true",
        help="Delete source .zip file after successful conversion.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch the modern graphical GUI.",
    )

    args = parser.parse_args()

    if args.gui:
        run_gui()
    elif args.directory:
        target = Path(args.directory)
        out = Path(args.output_dir) if args.output_dir else None
        run_cli_batch(
            directory=target,
            output_dir=out,
            recursive=args.recursive,
            overwrite=not args.no_overwrite,
            delete_zip=args.delete_zip,
        )
    else:
        run_interactive_tui()


if __name__ == "__main__":
    main()
