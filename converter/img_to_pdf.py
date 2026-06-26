"""
Image → PDF Converter
======================
A polished python utility to convert a directory of images (PNG, JPG, JPEG, WEBP, etc.)
into a single PDF file named after the directory.

Features:
    - High-performance PyMuPDF (fitz) core engine
    - Memory-optimized: streams images from disk, peeks dimensions, and collects garbage
      to handle large inputs (1GB+, 500+ images) easily
    - Natural sorting algorithm for correct page ordering
    - Dual Interface: Rich CLI/TUI and premium Tkinter GUI
"""

import gc
import os
import re
import sys
import time
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# Try to import rich components
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.prompt import Prompt
    from rich.theme import Theme
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

# Try to import PyMuPDF
try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] PyMuPDF (pymupdf) is required. Install with: pip install pymupdf")
    sys.exit(1)

# Try to import tkinterdnd2 for drag-and-drop support
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _HAS_DND = True
except ImportError:
    _HAS_DND = False

# Constants
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".gif"}
GC_INTERVAL = 15  # Garbage collect every N pages

# GUI Aesthetics
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

# Setup Rich console if available
if _HAS_RICH:
    custom_theme = Theme({
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "title": "bold magenta",
        "highlight": "bold cyan",
        "muted": "dim",
    })
    console = Console(theme=custom_theme)
else:
    class DummyConsole:
        def print(self, *args, **kwargs):
            print(*args)
    console = DummyConsole()


# ---------------------------------------------------------------------------
# Core Helper Functions
# ---------------------------------------------------------------------------
def _natural_sort_key(s: str):
    """Sort key that handles numbers naturally (e.g., img2.png before img10.png)."""
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


def _collect_images_from_dir(dir_path: Path) -> list[Path]:
    """Collect and naturally sort all image files directly within a directory."""
    if not dir_path.is_dir():
        return []
    images = [
        p for p in dir_path.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(images, key=lambda x: _natural_sort_key(x.name))


# ---------------------------------------------------------------------------
# Core Conversion Engine
# ---------------------------------------------------------------------------
def convert_images_to_pdf(
    dir_path: Path,
    output_pdf_path: Path | None = None,
    progress_cb=None,
    cancel_flag=None,
) -> Path:
    """
    Convert a folder of images into a single large PDF.
    Highly memory-efficient: streams pages and performs garbage collection.
    
    Parameters
    ----------
    dir_path : Path
        The directory containing the images.
    output_pdf_path : Path, optional
        The destination path. Defaults to [dir_path].pdf placed next to the folder.
    progress_cb : callable, optional
        Called as `progress_cb(current_page, total_pages, current_image_path)`
    cancel_flag : threading.Event, optional
        Used to signal cancellation from GUI or CLI.
        
    Returns
    -------
    Path
        The path of the created PDF file.
    """
    if not dir_path.exists() or not dir_path.is_dir():
        raise FileNotFoundError(f"Input directory does not exist: {dir_path}")

    # Find and naturally sort images
    images = _collect_images_from_dir(dir_path)
    if not images:
        raise ValueError(f"No image files (PNG, JPG, etc.) found in: {dir_path.name}")

    if output_pdf_path is None:
        output_pdf_path = dir_path.parent / f"{dir_path.name}.pdf"

    total_pages = len(images)
    pdf_doc = fitz.open()
    pages_added = 0

    try:
        for idx, img_path in enumerate(images):
            # Check for cancellation
            if cancel_flag and cancel_flag.is_set():
                pdf_doc.close()
                raise InterruptedError("Conversion cancelled")

            # Peek image dimensions (MuPDF fast opening)
            try:
                img_doc = fitz.open(str(img_path))
                rect = img_doc[0].rect
                img_doc.close()
                del img_doc
            except Exception:
                # Skip unreadable images
                continue

            # Add page of correct size and insert image
            page = pdf_doc.new_page(width=rect.width, height=rect.height)
            page.insert_image(rect, filename=str(img_path))
            pages_added += 1

            if progress_cb:
                progress_cb(pages_added, total_pages, img_path)

            # Keep memory usage minimal
            if idx % GC_INTERVAL == 0:
                gc.collect()

        if pages_added == 0:
            pdf_doc.close()
            raise ValueError(f"All images in '{dir_path.name}' were unreadable.")

        # Save with optimized compression flags
        pdf_doc.save(str(output_pdf_path), deflate=True, garbage=4)
        pdf_doc.close()
        del pdf_doc
        gc.collect()

    except Exception as e:
        # Delete partial file if an error occurs
        if output_pdf_path.exists():
            try:
                os.remove(output_pdf_path)
            except OSError:
                pass
        raise e

    return output_pdf_path


# ---------------------------------------------------------------------------
# CLI / Terminal Mode (Rich TUI)
# ---------------------------------------------------------------------------
def run_cli_conversion(dir_path: Path):
    """Run directory image conversion in terminal mode with rich progress display."""
    dir_path = Path(dir_path).resolve()
    
    if not _HAS_RICH:
        print(f"[*] Scanning images in {dir_path.name}...")
        images = _collect_images_from_dir(dir_path)
        print(f"[*] Found {len(images)} images.")
        output_pdf = dir_path.parent / f"{dir_path.name}.pdf"
        
        def simple_progress(curr, total, img_p):
            print(f"  [{curr}/{total}] Appending: {img_p.name}", end="\r")
            
        try:
            convert_images_to_pdf(dir_path, output_pdf, progress_cb=simple_progress)
            print(f"\n[+] PDF generated: {output_pdf.name}")
        except Exception as e:
            print(f"\n[ERROR] Conversion failed: {e}")
        return

    # Rich version
    console.print()
    console.print(Panel(f"[bold info]Image -> PDF Converter[/bold info]\nScanning: [yellow]{dir_path}[/yellow]", border_style="cyan"))
    
    images = _collect_images_from_dir(dir_path)
    if not images:
        console.print(f"  [error][!][/error] No images found in {dir_path}")
        return
        
    total_size = sum(img.stat().st_size for img in images if img.exists())
    output_pdf = dir_path.parent / f"{dir_path.name}.pdf"
    
    console.print(f"  [info][>][/info] Found [highlight]{len(images)}[/highlight] images (Total size: {_human_size(total_size)})")
    console.print(f"  [info][>][/info] Target file: [highlight]{output_pdf.name}[/highlight]")
    console.print()

    start_time = time.time()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40, complete_style="cyan", finished_style="green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Converting images...", total=len(images))
        
        def rich_progress(curr, total, img_p):
            progress.update(task, completed=curr, description=f"[cyan]Adding {img_p.name} ({curr}/{total})")
            
        try:
            convert_images_to_pdf(dir_path, output_pdf, progress_cb=rich_progress)
            elapsed = time.time() - start_time
            pdf_size = _human_size(output_pdf.stat().st_size) if output_pdf.exists() else "Unknown"
            
            console.print()
            console.print(Panel(
                f"[success][+][/success] [bold green]Conversion completed successfully![/bold green]\n\n"
                f"  • [info]Output PDF:[/] {output_pdf}\n"
                f"  • [info]Total Pages:[/] {len(images)}\n"
                f"  • [info]Output Size:[/] {pdf_size}\n"
                f"  • [info]Time Taken:[/] {elapsed:.2f} seconds",
                border_style="green"
            ))
        except KeyboardInterrupt:
            console.print("\n  [warning][*][/warning] Conversion interrupted.")
        except Exception as e:
            console.print(f"\n  [error][!][/error] Failed to convert: {e}")


# ---------------------------------------------------------------------------
# Interactive TUI / Launcher Mode
# ---------------------------------------------------------------------------
def run_interactive_tui():
    """Terminal UI prompted launcher."""
    if not _HAS_RICH:
        dir_str = input("Enter directory path (or press Enter to launch GUI): ").strip()
        if not dir_str:
            run_gui()
        else:
            run_cli_conversion(Path(dir_str))
        return

    console.print(
        Panel(
            "[bold info]Image -> PDF Toolkit[/bold info]\n\n"
            "  1. Convert folder via CLI\n"
            "  2. Launch graphical GUI (Drag-and-Drop)\n"
            "  0. Back / Exit",
            title="[bold]Image -> PDF[/bold]",
            border_style="magenta",
            padding=(1, 3),
        )
    )

    choice = Prompt.ask("  Choice", choices=["0", "1", "2"], default="1")
    if choice == "0":
        return
    elif choice == "2":
        run_gui()
    elif choice == "1":
        path_str = Prompt.ask("  Enter image folder path").strip()
        if path_str:
            p = Path(path_str)
            if p.is_dir():
                run_cli_conversion(p)
            else:
                console.print(f"  [error][!][/error] Folder not found: '{path_str}'")
        else:
            console.print("  [warning][*][/warning] Empty path, returning.")


# ---------------------------------------------------------------------------
# GUI Application Interface
# ---------------------------------------------------------------------------
class ImageToPdfApp:
    def __init__(self, root: tk.Tk | None = None):
        if root is None:
            if _HAS_DND:
                self.root = TkinterDnD.Tk()
            else:
                self.root = tk.Tk()
        else:
            self.root = root

        self.root.title("Image → PDF Converter")
        self.root.configure(bg=BG_PRIMARY)
        self.root.resizable(False, False)

        # Dimension and centering
        width, height = 720, 620
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # States
        self._pending_dirs: list[Path] = []
        self._is_converting = False
        self._cancel_event = threading.Event()
        self._start_time = 0.0

        # Build GUI
        self._setup_styles()
        self._build_ui()

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=BG_PRIMARY)
        style.configure("Card.TFrame", background=BG_CARD, relief="flat")
        style.configure("TLabel", background=BG_PRIMARY, foreground=FG_PRIMARY, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=BG_PRIMARY, foreground=FG_PRIMARY, font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background=BG_PRIMARY, foreground=FG_SECONDARY, font=("Segoe UI", 9))
        style.configure("Card.TLabel", background=BG_CARD, foreground=FG_PRIMARY, font=("Segoe UI", 10))
        style.configure("Status.TLabel", background=BG_PRIMARY, foreground=FG_SECONDARY, font=("Segoe UI", 9))
        style.configure("Success.TLabel", background=BG_PRIMARY, foreground=SUCCESS, font=("Segoe UI", 9, "bold"))
        style.configure("Error.TLabel", background=BG_PRIMARY, foreground=ERROR, font=("Segoe UI", 9, "bold"))
        style.configure("Warning.TLabel", background=BG_PRIMARY, foreground=WARNING_CLR, font=("Segoe UI", 9))

        style.configure("Accent.Horizontal.TProgressbar", troughcolor=BG_INPUT, background=ACCENT, darkcolor=ACCENT, lightcolor=ACCENT_HOVER, bordercolor=BG_PRIMARY, thickness=8)
        style.configure("Page.Horizontal.TProgressbar", troughcolor=BG_INPUT, background=ACCENT_GLOW, darkcolor=ACCENT_GLOW, lightcolor=ACCENT, bordercolor=BG_PRIMARY, thickness=5)

    def _build_ui(self):
        container = ttk.Frame(self.root, style="TFrame")
        container.pack(fill="both", expand=True, padx=28, pady=20)

        # Title Section
        ttk.Label(container, text="Image → PDF Converter", style="Title.TLabel").pack(anchor="w")
        ttk.Label(container, text="Convert directories of images to single PDF files. Drag-and-drop or select folders.", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 16))

        # Drop Zone
        self._drop_frame = tk.Frame(container, bg=DROP_ZONE_BG, highlightbackground=BORDER, highlightthickness=2, cursor="hand2")
        self._drop_frame.pack(fill="x", ipady=32)

        self._drop_icon = tk.Label(self._drop_frame, text="📁", font=("Segoe UI Emoji", 28), bg=DROP_ZONE_BG, fg=FG_PRIMARY)
        self._drop_icon.pack(pady=(12, 2))

        self._drop_label = tk.Label(self._drop_frame, text="Drop Image Folders Here", font=("Segoe UI", 11, "bold"), bg=DROP_ZONE_BG, fg=FG_PRIMARY)
        self._drop_label.pack()

        hint_text = "or click to browse folder" + ("" if _HAS_DND else " (DND disabled, install tkinterdnd2)")
        self._drop_hint = tk.Label(self._drop_frame, text=hint_text, font=("Segoe UI", 9), bg=DROP_ZONE_BG, fg=FG_MUTED)
        self._drop_hint.pack(pady=(2, 8))

        # Setup drag and drop binding if available
        if _HAS_DND:
            self._drop_frame.drop_target_register(DND_FILES)
            self._drop_frame.dnd_bind("<<DropEnter>>", self._on_drag_enter)
            self._drop_frame.dnd_bind("<<DropLeave>>", self._on_drag_leave)
            self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)

        for w in (self._drop_frame, self._drop_icon, self._drop_label, self._drop_hint):
            w.bind("<Button-1>", self._on_drop_click)

        # Buttons
        btn_row = ttk.Frame(container, style="TFrame")
        btn_row.pack(fill="x", pady=(12, 0))

        self._btn_folder = tk.Button(btn_row, text="📁  Select Folders", font=("Segoe UI", 10), bg=BG_CARD, fg=FG_PRIMARY, activebackground=BG_INPUT, activeforeground=FG_PRIMARY, relief="flat", padx=18, pady=8, cursor="hand2", command=self._browse_folder)
        self._btn_folder.pack(side="left")

        # Spacer
        ttk.Frame(btn_row, style="TFrame").pack(side="left", fill="x", expand=True)

        self._btn_cancel = tk.Button(btn_row, text="✕  Cancel", font=("Segoe UI", 10), bg="#442233", fg=ERROR, activebackground="#553344", activeforeground=ERROR, relief="flat", padx=14, pady=8, cursor="hand2", command=self._cancel_conversion)
        # Hidden by default

        self._btn_convert = tk.Button(btn_row, text="⚡  Convert Folders", font=("Segoe UI", 10, "bold"), bg=ACCENT, fg="#ffffff", activebackground=ACCENT_HOVER, activeforeground="#ffffff", relief="flat", padx=22, pady=8, cursor="hand2", command=self._start_conversion, state="disabled")
        self._btn_convert.pack(side="right")

        # File List Card View
        card = tk.Frame(container, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, pady=(14, 0))

        card_header = tk.Frame(card, bg=BG_CARD)
        card_header.pack(fill="x", padx=14, pady=(10, 4))

        self._file_count_label = tk.Label(card_header, text="No directories selected", font=("Segoe UI", 9, "bold"), bg=BG_CARD, fg=FG_SECONDARY)
        self._file_count_label.pack(side="left")

        self._btn_clear = tk.Label(card_header, text="✕ Clear All", font=("Segoe UI", 9), bg=BG_CARD, fg=FG_MUTED, cursor="hand2")
        self._btn_clear.pack(side="right")
        self._btn_clear.bind("<Button-1>", lambda _: self._clear_directories())

        list_frame = tk.Frame(card, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", troughcolor=BG_CARD, bg=BG_INPUT)
        scrollbar.pack(side="right", fill="y")

        self._file_listbox = tk.Listbox(
            list_frame, bg=BG_INPUT, fg=FG_PRIMARY, selectbackground=ACCENT, selectforeground="#ffffff", font=("Consolas", 9), borderwidth=0, highlightthickness=0, yscrollcommand=scrollbar.set, activestyle="none"
        )
        self._file_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self._file_listbox.yview)

        # Progress Section
        progress_frame = ttk.Frame(container, style="TFrame")
        progress_frame.pack(fill="x", pady=(10, 0))

        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(progress_frame, variable=self._progress_var, maximum=100, style="Accent.Horizontal.TProgressbar")
        self._progress_bar.pack(fill="x")

        self._page_progress_var = tk.DoubleVar(value=0)
        self._page_progress_bar = ttk.Progressbar(progress_frame, variable=self._page_progress_var, maximum=100, style="Page.Horizontal.TProgressbar")
        self._page_progress_bar.pack(fill="x", pady=(3, 0))

        self._status_label = ttk.Label(progress_frame, text="Ready", style="Status.TLabel")
        self._status_label.pack(anchor="w", pady=(4, 0))

        self._detail_label = ttk.Label(progress_frame, text="", style="Status.TLabel")
        self._detail_label.pack(anchor="w", pady=(1, 0))

    # ---- Drag and drop handlers ----
    def _on_drag_enter(self, event):
        self._drop_frame.configure(bg=DROP_ZONE_ACTIVE, highlightbackground=ACCENT)
        for w in (self._drop_icon, self._drop_label, self._drop_hint):
            w.configure(bg=DROP_ZONE_ACTIVE)

    def _on_drag_leave(self, event):
        self._drop_frame.configure(bg=DROP_ZONE_BG, highlightbackground=BORDER)
        for w in (self._drop_icon, self._drop_label, self._drop_hint):
            w.configure(bg=DROP_ZONE_BG)

    def _on_drop(self, event):
        self._on_drag_leave(event)
        raw = event.data
        paths = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                end = raw.index("}", i)
                paths.append(raw[i + 1 : end])
                i = end + 2
            elif raw[i] == " ":
                i += 1
            else:
                end = raw.find(" ", i)
                if end == -1:
                    end = len(raw)
                paths.append(raw[i:end])
                i = end + 1

        for p in paths:
            self._add_path(p)

    def _on_drop_click(self, event):
        self._browse_folder()

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing images")
        if folder:
            self._add_path(folder)

    def _add_path(self, path: str):
        p = Path(path).resolve()
        if p.is_dir() and p not in self._pending_dirs:
            self._pending_dirs.append(p)
            self._refresh_list()
        elif p.is_file():
            # If a file was dropped/selected, check if its parent can be added
            parent = p.parent
            if parent not in self._pending_dirs:
                self._pending_dirs.append(parent)
                self._refresh_list()
        else:
            self._set_status(f"Not a valid directory: {p.name}", error=True)

    def _clear_directories(self):
        if self._is_converting:
            return
        self._pending_dirs.clear()
        self._refresh_list()
        self._progress_var.set(0)
        self._page_progress_var.set(0)
        self._set_status("Ready")
        self._detail_label.configure(text="")

    def _refresh_list(self):
        self._file_listbox.delete(0, tk.END)
        for d in self._pending_dirs:
            images = _collect_images_from_dir(d)
            count = len(images)
            size = sum(i.stat().st_size for i in images if i.exists())
            size_str = _human_size(size)
            self._file_listbox.insert(tk.END, f"  📁 {d.name}   [{count} image{'s' if count != 1 else ''} • {size_str}]   ({d.parent})")

        total_dirs = len(self._pending_dirs)
        if total_dirs == 0:
            self._file_count_label.configure(text="No directories selected")
            self._btn_convert.configure(state="disabled")
        else:
            self._file_count_label.configure(text=f"{total_dirs} folder{'s' if total_dirs != 1 else ''} queued")
            self._btn_convert.configure(state="normal")

    # ---- Conversion worker thread trigger ----
    def _start_conversion(self):
        if self._is_converting or not self._pending_dirs:
            return
        self._is_converting = True
        self._cancel_event.clear()
        self._start_time = time.time()

        self._btn_convert.pack_forget()
        self._btn_cancel.pack(side="right")
        self._btn_folder.configure(state="disabled")

        threading.Thread(target=self._conversion_thread, daemon=True).start()

    def _cancel_conversion(self):
        self._cancel_event.set()
        self.root.after(0, self._set_status, "Cancelling...", False, False, True)

    def _conversion_thread(self):
        total_dirs = len(self._pending_dirs)
        success_count = 0
        fail_count = 0

        for idx, dir_path in enumerate(self._pending_dirs, 1):
            if self._cancel_event.is_set():
                break

            images = _collect_images_from_dir(dir_path)
            total_images = len(images)
            dir_size = sum(i.stat().st_size for i in images if i.exists())
            dir_size_str = _human_size(dir_size)

            self.root.after(0, self._set_status, f"[{idx}/{total_dirs}] Converting: {dir_path.name} ({dir_size_str})")
            self.root.after(0, self._page_progress_var.set, 0)

            # Progress callback for individual files inside folder
            def _page_cb(curr_p, total_p, img_path, _fi=idx, _td=total_dirs):
                pct = (curr_p / total_p) * 100
                elapsed = time.time() - self._start_time
                elapsed_str = time.strftime("%M:%S", time.gmtime(elapsed))

                # ETA calculation
                done_fraction = ((_fi - 1) + curr_p / total_p) / _td
                if done_fraction > 0:
                    eta = elapsed / done_fraction - elapsed
                    eta_str = time.strftime("%M:%S", time.gmtime(eta))
                else:
                    eta_str = "—"

                self.root.after(0, self._page_progress_var.set, pct)
                self.root.after(0, self._update_detail, f"Page {curr_p}/{total_p} • Elapsed {elapsed_str} • ETA ~{eta_str}")

            try:
                output_pdf = convert_images_to_pdf(
                    dir_path,
                    progress_cb=_page_cb,
                    cancel_flag=self._cancel_event
                )
                success_count += 1
                self.root.after(0, self._mark_item_done, idx - 1, output_pdf)
            except InterruptedError:
                self.root.after(0, self._mark_item_cancelled, idx - 1)
                break
            except Exception as e:
                fail_count += 1
                self.root.after(0, self._mark_item_error, idx - 1, str(e))

            # Update overall progress
            overall_progress = (idx / total_dirs) * 100
            self.root.after(0, self._progress_var.set, overall_progress)

        cancelled = self._cancel_event.is_set()
        elapsed = time.time() - self._start_time
        self.root.after(0, self._conversion_complete, success_count, fail_count, cancelled, elapsed)

    def _update_detail(self, text: str):
        self._detail_label.configure(text=text, style="Status.TLabel")

    def _mark_item_done(self, idx: int, pdf_path: Path):
        current = self._file_listbox.get(idx)
        pdf_size = _human_size(pdf_path.stat().st_size) if pdf_path.exists() else "Unknown size"
        self._file_listbox.delete(idx)
        self._file_listbox.insert(idx, f"  ✅ {current.strip()}  →  {pdf_size}")
        self._file_listbox.itemconfig(idx, fg=SUCCESS)
        self._file_listbox.see(idx)

    def _mark_item_error(self, idx: int, error_msg: str):
        current = self._file_listbox.get(idx)
        self._file_listbox.delete(idx)
        self._file_listbox.insert(idx, f"  ❌ {current.strip()}  —  {error_msg}")
        self._file_listbox.itemconfig(idx, fg=ERROR)
        self._file_listbox.see(idx)

    def _mark_item_cancelled(self, idx: int):
        current = self._file_listbox.get(idx)
        self._file_listbox.delete(idx)
        self._file_listbox.insert(idx, f"  ⏹ {current.strip()}  —  cancelled")
        self._file_listbox.itemconfig(idx, fg=WARNING_CLR)
        self._file_listbox.see(idx)

    def _conversion_complete(self, ok: int, fail: int, cancelled: bool, elapsed: float):
        self._is_converting = False
        self._btn_cancel.pack_forget()
        self._btn_convert.pack(side="right")
        self._btn_convert.configure(state="normal")
        self._btn_folder.configure(state="normal")

        elapsed_str = time.strftime("%M:%S", time.gmtime(elapsed))

        if cancelled:
            self._set_status(f"Cancelled — {ok} folder{'s' if ok != 1 else ''} converted before abort ({elapsed_str})", warning=True)
        elif fail == 0:
            self._set_status(f"✅ All done — {ok} folder{'s' if ok != 1 else ''} converted successfully! ({elapsed_str})", success=True)
        else:
            self._set_status(f"Finished with errors — {ok} converted, {fail} failed ({elapsed_str})", error=True)

        self._page_progress_var.set(100 if not cancelled else 0)
        self._detail_label.configure(text="")

    def _set_status(self, text: str, success: bool = False, error: bool = False, warning: bool = False):
        if success:
            self._status_label.configure(text=text, style="Success.TLabel")
        elif error:
            self._status_label.configure(text=text, style="Error.TLabel")
        elif warning:
            self._status_label.configure(text=text, style="Warning.TLabel")
        else:
            self._status_label.configure(text=text, style="Status.TLabel")

    def mainloop(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# App Launchers / Entry Points
# ---------------------------------------------------------------------------
def run_gui():
    """Launch the GUI window interface."""
    app = ImageToPdfApp()
    app.mainloop()


def run():
    """Entry point for the project's central main.py launcher menu."""
    run_interactive_tui()


def main():
    """CLI/Direct execution entry point."""
    if len(sys.argv) > 1:
        # Check if first arg is a path
        path_arg = Path(sys.argv[1])
        if path_arg.is_dir():
            run_cli_conversion(path_arg)
        else:
            print(f"[ERROR] Directory not found: {sys.argv[1]}")
    else:
        # Prompt option (leads to GUI or CLI input)
        run_interactive_tui()


if __name__ == "__main__":
    main()
