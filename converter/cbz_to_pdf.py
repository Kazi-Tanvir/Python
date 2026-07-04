"""
CBZ → PDF Converter
====================
A polished Tkinter GUI with native drag-and-drop support for converting
Comic Book ZIP (.cbz) archives to PDF files.

Features:
    - Drag-and-drop single .cbz files or entire directories
    - File / folder browser dialogs as fallback
    - Batch conversion with a live progress bar
    - Natural filename sorting for correct page order
    - Memory-efficient: streams images through temp files for 1GB+ archives
    - Powered by PyMuPDF (fitz) — fast, dependency-light

Entry points:
    run()   — launched from the project's main.py Rich menu
    main()  — direct CLI usage:  python cbz_to_pdf.py
"""

import gc
import os
import re
import sys
import time
import shutil
import zipfile
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] PyMuPDF is required.  Install with:  pip install pymupdf")
    sys.exit(1)

# Optional: tkinterdnd2 for native drag-and-drop
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES

    _HAS_DND = True
except ImportError:
    _HAS_DND = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
WINDOW_WIDTH = 720
WINDOW_HEIGHT = 620

# How many pages between forced garbage collections (lower = less RAM, tiny overhead)
GC_INTERVAL = 10

# ---------------------------------------------------------------------------
# Colour palette — dark, premium aesthetic
# ---------------------------------------------------------------------------
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
def _natural_sort_key(s: str):
    """Sort key that handles embedded numbers naturally (e.g. page2 < page10)."""
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


def _collect_cbz_files(path: str) -> list[Path]:
    """Return a list of .cbz Paths from a file or directory."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".cbz":
        return [p]
    if p.is_dir():
        return sorted(p.rglob("*.cbz"), key=lambda x: _natural_sort_key(x.name))
    return []


def _convert_cbz_to_pdf(
    cbz_path: Path,
    output_dir: Path | None = None,
    progress_cb=None,
    cancel_flag=None,
) -> Path:
    """
    Convert a single .cbz file to a PDF — memory-efficient version.

    Images are extracted to a temp directory one at a time and inserted
    into the PDF via filename reference so MuPDF handles I/O directly
    without inflating Python's heap.

    Parameters
    ----------
    cbz_path : Path
        Path to the .cbz file.
    output_dir : Path, optional
        Directory for the output PDF.  Defaults to the same directory as
        the source .cbz.
    progress_cb : callable, optional
        Called as ``progress_cb(current_page, total_pages)`` after each page.
    cancel_flag : threading.Event, optional
        If set, the conversion aborts early.

    Returns
    -------
    Path
        Path to the generated PDF.
    """
    if output_dir is None:
        output_dir = cbz_path.parent

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / (cbz_path.stem + ".pdf")

    # Create a temp dir for extracted images (auto-cleaned at the end)
    tmp_dir = tempfile.mkdtemp(prefix="cbz2pdf_")

    try:
        with zipfile.ZipFile(cbz_path, "r") as zf:
            # Filter to image files, sort naturally
            image_names = sorted(
                [
                    n
                    for n in zf.namelist()
                    if Path(n).suffix.lower() in IMAGE_EXTENSIONS
                    and not Path(n).name.startswith(".")  # skip hidden/macOS junk
                ],
                key=_natural_sort_key,
            )

            if not image_names:
                raise ValueError(f"No images found in '{cbz_path.name}'")

            total_pages = len(image_names)
            pdf_doc = fitz.open()
            pages_added = 0

            for idx, img_name in enumerate(image_names):
                # --- Check for cancellation ---
                if cancel_flag and cancel_flag.is_set():
                    pdf_doc.close()
                    raise InterruptedError("Conversion cancelled")

                # --- Extract single image to temp file ---
                safe_name = f"page_{idx:06d}{Path(img_name).suffix.lower()}"
                tmp_path = os.path.join(tmp_dir, safe_name)
                try:
                    img_data = zf.read(img_name)
                    with open(tmp_path, "wb") as f:
                        f.write(img_data)
                    del img_data  # free Python memory immediately
                except Exception:
                    continue  # skip corrupt entries

                # --- Get image dimensions via fitz (fast, C-level) ---
                try:
                    img_doc = fitz.open(tmp_path)
                    rect = img_doc[0].rect
                    img_doc.close()
                    del img_doc
                except Exception:
                    # Unreadable image — clean up and skip
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                    continue

                # --- Insert into PDF (fitz reads from file, not Python RAM) ---
                page = pdf_doc.new_page(width=rect.width, height=rect.height)
                page.insert_image(rect, filename=tmp_path)
                pages_added += 1

                # --- Clean up the temp file immediately ---
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

                # --- Progress callback ---
                if progress_cb:
                    progress_cb(idx + 1, total_pages)

                # --- Periodic garbage collection ---
                if idx % GC_INTERVAL == 0:
                    gc.collect()

            if pages_added == 0:
                pdf_doc.close()
                raise ValueError(f"All images in '{cbz_path.name}' were unreadable")

            pdf_doc.save(str(pdf_path), deflate=True, garbage=4)
            pdf_doc.close()
            del pdf_doc
            gc.collect()

    finally:
        # Always clean up temp dir
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return pdf_path


# ---------------------------------------------------------------------------
# GUI Application
# ---------------------------------------------------------------------------
class CbzToPdfApp:
    """
    Premium-look Tkinter GUI for CBZ → PDF conversion.

    Supports:
    - Native drag-and-drop (via tkinterdnd2 if installed)
    - File/folder picker dialogs
    - Per-page progress for large files
    - Cancel button during conversion
    """

    def __init__(self, root: tk.Tk | None = None):
        if root is None:
            if _HAS_DND:
                self.root = TkinterDnD.Tk()
            else:
                self.root = tk.Tk()
        else:
            self.root = root

        self.root.title("CBZ → PDF Converter")
        self.root.configure(bg=BG_PRIMARY)
        self.root.resizable(False, False)

        # Centre on screen
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - WINDOW_WIDTH) // 2
        y = (screen_h - WINDOW_HEIGHT) // 2
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x}+{y}")

        # State
        self._pending_files: list[Path] = []
        self._is_converting = False
        self._cancel_event = threading.Event()
        self._start_time: float = 0

        # Build the UI
        self._setup_styles()
        self._build_ui()

    # ---- Styles -----------------------------------------------------------
    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure("TFrame", background=BG_PRIMARY)
        style.configure(
            "Card.TFrame",
            background=BG_CARD,
            relief="flat",
        )
        style.configure(
            "TLabel",
            background=BG_PRIMARY,
            foreground=FG_PRIMARY,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Title.TLabel",
            background=BG_PRIMARY,
            foreground=FG_PRIMARY,
            font=("Segoe UI", 18, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=BG_PRIMARY,
            foreground=FG_SECONDARY,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Card.TLabel",
            background=BG_CARD,
            foreground=FG_PRIMARY,
            font=("Segoe UI", 10),
        )
        style.configure(
            "CardDim.TLabel",
            background=BG_CARD,
            foreground=FG_MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            background=BG_PRIMARY,
            foreground=FG_SECONDARY,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Success.TLabel",
            background=BG_PRIMARY,
            foreground=SUCCESS,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "Error.TLabel",
            background=BG_PRIMARY,
            foreground=ERROR,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "Warning.TLabel",
            background=BG_PRIMARY,
            foreground=WARNING_CLR,
            font=("Segoe UI", 9),
        )

        # Progress bars
        style.configure(
            "Accent.Horizontal.TProgressbar",
            troughcolor=BG_INPUT,
            background=ACCENT,
            darkcolor=ACCENT,
            lightcolor=ACCENT_HOVER,
            bordercolor=BG_PRIMARY,
            thickness=8,
        )
        style.configure(
            "Page.Horizontal.TProgressbar",
            troughcolor=BG_INPUT,
            background=ACCENT_GLOW,
            darkcolor=ACCENT_GLOW,
            lightcolor=ACCENT,
            bordercolor=BG_PRIMARY,
            thickness=5,
        )

    # ---- UI construction --------------------------------------------------
    def _build_ui(self):
        # Main container with padding
        container = ttk.Frame(self.root, style="TFrame")
        container.pack(fill="both", expand=True, padx=28, pady=20)

        # ── Title ──
        ttk.Label(container, text="CBZ → PDF", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            container,
            text="Convert comic book archives to PDF. Drag-and-drop or browse.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(0, 16))

        # ── Drop zone ──
        self._drop_frame = tk.Frame(
            container,
            bg=DROP_ZONE_BG,
            highlightbackground=BORDER,
            highlightthickness=2,
            cursor="hand2",
        )
        self._drop_frame.pack(fill="x", ipady=32)

        self._drop_icon = tk.Label(
            self._drop_frame,
            text="📂",
            font=("Segoe UI Emoji", 28),
            bg=DROP_ZONE_BG,
            fg=FG_PRIMARY,
        )
        self._drop_icon.pack(pady=(12, 2))

        self._drop_label = tk.Label(
            self._drop_frame,
            text="Drop .cbz files or folders here",
            font=("Segoe UI", 11, "bold"),
            bg=DROP_ZONE_BG,
            fg=FG_PRIMARY,
        )
        self._drop_label.pack()

        self._drop_hint = tk.Label(
            self._drop_frame,
            text="or click to browse" + ("" if _HAS_DND else "  (install tkinterdnd2 for drag-and-drop)"),
            font=("Segoe UI", 9),
            bg=DROP_ZONE_BG,
            fg=FG_MUTED,
        )
        self._drop_hint.pack(pady=(2, 8))

        # Click-to-browse on the whole drop area
        for widget in (self._drop_frame, self._drop_icon, self._drop_label, self._drop_hint):
            widget.bind("<Button-1>", self._on_drop_click)

        # Register DnD if available
        if _HAS_DND:
            self._drop_frame.drop_target_register(DND_FILES)
            self._drop_frame.dnd_bind("<<DropEnter>>", self._on_drag_enter)
            self._drop_frame.dnd_bind("<<DropLeave>>", self._on_drag_leave)
            self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)

        # ── Browse buttons row ──
        btn_row = ttk.Frame(container, style="TFrame")
        btn_row.pack(fill="x", pady=(12, 0))

        self._btn_file = tk.Button(
            btn_row,
            text="📄  Select Files",
            font=("Segoe UI", 10),
            bg=BG_CARD,
            fg=FG_PRIMARY,
            activebackground=BG_INPUT,
            activeforeground=FG_PRIMARY,
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=self._browse_files,
        )
        self._btn_file.pack(side="left", padx=(0, 8))

        self._btn_folder = tk.Button(
            btn_row,
            text="📁  Select Folder",
            font=("Segoe UI", 10),
            bg=BG_CARD,
            fg=FG_PRIMARY,
            activebackground=BG_INPUT,
            activeforeground=FG_PRIMARY,
            relief="flat",
            padx=18,
            pady=8,
            cursor="hand2",
            command=self._browse_folder,
        )
        self._btn_folder.pack(side="left", padx=(0, 8))

        # Spacer
        ttk.Frame(btn_row, style="TFrame").pack(side="left", fill="x", expand=True)

        # Cancel button (hidden until conversion starts)
        self._btn_cancel = tk.Button(
            btn_row,
            text="✕  Cancel",
            font=("Segoe UI", 10),
            bg="#442233",
            fg=ERROR,
            activebackground="#553344",
            activeforeground=ERROR,
            relief="flat",
            padx=14,
            pady=8,
            cursor="hand2",
            command=self._cancel_conversion,
        )
        # Not packed yet — shown only during conversion

        self._btn_convert = tk.Button(
            btn_row,
            text="⚡  Convert",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT,
            fg="#ffffff",
            activebackground=ACCENT_HOVER,
            activeforeground="#ffffff",
            relief="flat",
            padx=22,
            pady=8,
            cursor="hand2",
            command=self._start_conversion,
            state="disabled",
        )
        self._btn_convert.pack(side="right")

        # ── File list (card) ──
        card = tk.Frame(container, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, pady=(14, 0))

        card_header = tk.Frame(card, bg=BG_CARD)
        card_header.pack(fill="x", padx=14, pady=(10, 4))

        self._file_count_label = tk.Label(
            card_header,
            text="No files selected",
            font=("Segoe UI", 9, "bold"),
            bg=BG_CARD,
            fg=FG_SECONDARY,
        )
        self._file_count_label.pack(side="left")

        self._btn_clear = tk.Label(
            card_header,
            text="✕ Clear",
            font=("Segoe UI", 9),
            bg=BG_CARD,
            fg=FG_MUTED,
            cursor="hand2",
        )
        self._btn_clear.pack(side="right")
        self._btn_clear.bind("<Button-1>", lambda _: self._clear_files())

        # Scrollable listbox
        list_frame = tk.Frame(card, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        scrollbar = tk.Scrollbar(list_frame, orient="vertical", troughcolor=BG_CARD, bg=BG_INPUT)
        scrollbar.pack(side="right", fill="y")

        self._file_listbox = tk.Listbox(
            list_frame,
            bg=BG_INPUT,
            fg=FG_PRIMARY,
            selectbackground=ACCENT,
            selectforeground="#ffffff",
            font=("Consolas", 9),
            borderwidth=0,
            highlightthickness=0,
            yscrollcommand=scrollbar.set,
            activestyle="none",
        )
        self._file_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self._file_listbox.yview)

        # ── Progress area ──
        progress_frame = ttk.Frame(container, style="TFrame")
        progress_frame.pack(fill="x", pady=(10, 0))

        # File-level progress (primary bar)
        self._progress_var = tk.DoubleVar(value=0)
        self._progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self._progress_var,
            maximum=100,
            style="Accent.Horizontal.TProgressbar",
        )
        self._progress_bar.pack(fill="x")

        # Page-level progress (secondary, thinner bar)
        self._page_progress_var = tk.DoubleVar(value=0)
        self._page_progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self._page_progress_var,
            maximum=100,
            style="Page.Horizontal.TProgressbar",
        )
        self._page_progress_bar.pack(fill="x", pady=(3, 0))

        # Status line: main status
        self._status_label = ttk.Label(
            progress_frame,
            text="Ready",
            style="Status.TLabel",
        )
        self._status_label.pack(anchor="w", pady=(4, 0))

        # Detail line: page progress + elapsed time
        self._detail_label = ttk.Label(
            progress_frame,
            text="",
            style="Status.TLabel",
        )
        self._detail_label.pack(anchor="w", pady=(1, 0))

    # ---- Drag-and-drop callbacks ------------------------------------------
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
        # Parse the dropped data (handles paths with spaces wrapped in {})
        raw = event.data
        paths = []
        i = 0
        while i < len(raw):
            if raw[i] == "{":
                end = raw.index("}", i)
                paths.append(raw[i + 1 : end])
                i = end + 2  # skip } and space
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
        """Show a small context menu: pick files or folder."""
        menu = tk.Menu(self.root, tearoff=0, bg=BG_CARD, fg=FG_PRIMARY,
                       activebackground=ACCENT, activeforeground="#ffffff",
                       font=("Segoe UI", 10))
        menu.add_command(label="📄  Select CBZ Files…", command=self._browse_files)
        menu.add_command(label="📁  Select Folder…", command=self._browse_folder)
        menu.tk_popup(event.x_root, event.y_root)

    # ---- File picking -----------------------------------------------------
    def _browse_files(self):
        files = filedialog.askopenfilenames(
            title="Select CBZ files",
            filetypes=[("CBZ files", "*.cbz"), ("All files", "*.*")],
        )
        for f in files:
            self._add_path(f)

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing CBZ files")
        if folder:
            self._add_path(folder)

    def _add_path(self, path: str):
        cbzs = _collect_cbz_files(path)
        new_count = 0
        for cbz in cbzs:
            if cbz not in self._pending_files:
                self._pending_files.append(cbz)
                new_count += 1
        self._refresh_file_list()
        if new_count == 0 and not cbzs:
            self._set_status(f"No .cbz files found in: {Path(path).name}", error=True)

    def _clear_files(self):
        if self._is_converting:
            return
        self._pending_files.clear()
        self._refresh_file_list()
        self._progress_var.set(0)
        self._page_progress_var.set(0)
        self._set_status("Ready")
        self._detail_label.configure(text="")

    def _refresh_file_list(self):
        self._file_listbox.delete(0, tk.END)
        for f in self._pending_files:
            size = _human_size(f.stat().st_size) if f.exists() else "?"
            self._file_listbox.insert(tk.END, f"  {f.name}   [{size}]   ({f.parent})")
        count = len(self._pending_files)
        if count == 0:
            self._file_count_label.configure(text="No files selected")
            self._btn_convert.configure(state="disabled")
        else:
            total_size = sum(f.stat().st_size for f in self._pending_files if f.exists())
            self._file_count_label.configure(
                text=f"{count} file{'s' if count != 1 else ''} queued  •  {_human_size(total_size)} total"
            )
            self._btn_convert.configure(state="normal")

    # ---- Conversion -------------------------------------------------------
    def _start_conversion(self):
        if self._is_converting or not self._pending_files:
            return
        self._is_converting = True
        self._cancel_event.clear()
        self._start_time = time.time()

        # Swap Convert → Cancel
        self._btn_convert.pack_forget()
        self._btn_cancel.pack(side="right")
        self._btn_file.configure(state="disabled")
        self._btn_folder.configure(state="disabled")

        threading.Thread(target=self._conversion_worker, daemon=True).start()

    def _cancel_conversion(self):
        """Signal the worker thread to stop."""
        self._cancel_event.set()
        self.root.after(0, self._set_status, "Cancelling…", False, False)

    def _conversion_worker(self):
        total_files = len(self._pending_files)
        success_count = 0
        fail_count = 0

        for file_idx, cbz in enumerate(self._pending_files, 1):
            if self._cancel_event.is_set():
                break

            cbz_size = _human_size(cbz.stat().st_size) if cbz.exists() else "?"
            self.root.after(
                0,
                self._set_status,
                f"[{file_idx}/{total_files}]  {cbz.name}  ({cbz_size})",
            )
            self.root.after(0, self._page_progress_var.set, 0)

            # Page-level progress callback (called from conversion thread)
            def _page_cb(current_page, total_pages, _fi=file_idx, _tf=total_files):
                pct = (current_page / total_pages) * 100
                elapsed = time.time() - self._start_time
                elapsed_str = time.strftime("%M:%S", time.gmtime(elapsed))

                # Estimate remaining time based on pages done so far
                if current_page > 0:
                    # Weighted: files done + fraction of current file
                    done_fraction = ((_fi - 1) + current_page / total_pages) / _tf
                    if done_fraction > 0:
                        eta = elapsed / done_fraction - elapsed
                        eta_str = time.strftime("%M:%S", time.gmtime(eta))
                    else:
                        eta_str = "—"
                else:
                    eta_str = "—"

                self.root.after(0, self._page_progress_var.set, pct)
                self.root.after(
                    0,
                    self._update_detail,
                    f"Page {current_page}/{total_pages}   •   Elapsed {elapsed_str}   •   ETA ~{eta_str}",
                )

            try:
                pdf_path = _convert_cbz_to_pdf(
                    cbz,
                    progress_cb=_page_cb,
                    cancel_flag=self._cancel_event,
                )
                success_count += 1
                self.root.after(0, self._mark_item_done, file_idx - 1, pdf_path)
            except InterruptedError:
                self.root.after(0, self._mark_item_cancelled, file_idx - 1)
                break
            except Exception as e:
                fail_count += 1
                self.root.after(0, self._mark_item_error, file_idx - 1, str(e))

            # Update file-level progress
            file_progress = (file_idx / total_files) * 100
            self.root.after(0, self._progress_var.set, file_progress)

        # Done
        cancelled = self._cancel_event.is_set()
        elapsed = time.time() - self._start_time
        self.root.after(0, self._conversion_done, success_count, fail_count, cancelled, elapsed)

    def _update_detail(self, text: str):
        self._detail_label.configure(text=text, style="Status.TLabel")

    def _mark_item_done(self, idx: int, pdf_path: Path):
        current = self._file_listbox.get(idx)
        pdf_size = _human_size(pdf_path.stat().st_size) if pdf_path.exists() else ""
        self._file_listbox.delete(idx)
        self._file_listbox.insert(idx, f"  ✅ {current.strip()}  →  {pdf_size}")
        self._file_listbox.itemconfig(idx, fg=SUCCESS)
        self._file_listbox.see(idx)  # auto-scroll to current

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

    def _conversion_done(self, ok: int, fail: int, cancelled: bool, elapsed: float):
        self._is_converting = False

        # Swap Cancel → Convert
        self._btn_cancel.pack_forget()
        self._btn_convert.pack(side="right")
        self._btn_convert.configure(state="normal")
        self._btn_file.configure(state="normal")
        self._btn_folder.configure(state="normal")

        elapsed_str = time.strftime("%M:%S", time.gmtime(elapsed))

        if cancelled:
            self._set_status(f"Cancelled — {ok} converted before stop  ({elapsed_str})", warning=True)
        elif fail == 0:
            self._set_status(
                f"✅  All done — {ok} file{'s' if ok != 1 else ''} converted  ({elapsed_str})",
                success=True,
            )
        else:
            self._set_status(
                f"Done — {ok} converted, {fail} failed  ({elapsed_str})",
                error=fail > 0,
            )

        self._page_progress_var.set(100 if not cancelled else 0)
        self._detail_label.configure(text="")

    # ---- Status -----------------------------------------------------------
    def _set_status(self, text: str, success: bool = False, error: bool = False, warning: bool = False):
        if success:
            self._status_label.configure(text=text, style="Success.TLabel")
        elif error:
            self._status_label.configure(text=text, style="Error.TLabel")
        elif warning:
            self._status_label.configure(text=text, style="Warning.TLabel")
        else:
            self._status_label.configure(text=text, style="Status.TLabel")

    # ---- Run --------------------------------------------------------------
    def mainloop(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# CLI / Terminal Mode (Rich TUI)
# ---------------------------------------------------------------------------
def run_cli_conversion(cbz_path: Path):
    """Run CBZ → PDF conversion in terminal mode with rich progress display."""
    cbz_path = Path(cbz_path).resolve()

    if not cbz_path.exists():
        print(f"[ERROR] File not found: {cbz_path}")
        return
    if cbz_path.suffix.lower() != ".cbz":
        print(f"[ERROR] Not a CBZ file: {cbz_path}")
        return

    # Try to import Rich for pretty output
    try:
        from rich.console import Console as _RichConsole
        from rich.panel import Panel as _RichPanel
        from rich.progress import (
            Progress as _RichProgress,
            SpinnerColumn,
            BarColumn,
            TextColumn,
            TimeElapsedColumn,
        )
        from rich.theme import Theme as _RichTheme

        _cli_theme = _RichTheme({
            "info": "cyan",
            "success": "bold green",
            "warning": "bold yellow",
            "error": "bold red",
        })
        _cli_console = _RichConsole(theme=_cli_theme)
        _has_rich = True
    except ImportError:
        _has_rich = False

    cbz_size = _human_size(cbz_path.stat().st_size) if cbz_path.exists() else "?"
    output_pdf = cbz_path.parent / (cbz_path.stem + ".pdf")

    if not _has_rich:
        print(f"[*] Converting: {cbz_path.name} ({cbz_size})")
        start = time.time()

        def simple_progress(curr, total):
            print(f"  [{curr}/{total}] Processing pages...", end="\r")

        try:
            _convert_cbz_to_pdf(cbz_path, progress_cb=simple_progress)
            elapsed = time.time() - start
            print(f"\n[+] PDF generated: {output_pdf.name} ({elapsed:.1f}s)")
        except Exception as e:
            print(f"\n[ERROR] Conversion failed: {e}")
        return

    # Rich version
    _cli_console.print()
    _cli_console.print(_RichPanel(
        f"[bold info]CBZ → PDF Converter[/bold info]\n"
        f"File: [yellow]{cbz_path.name}[/yellow]  ({cbz_size})",
        border_style="cyan",
    ))

    start = time.time()

    with _RichProgress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40, complete_style="cyan", finished_style="green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=_cli_console,
    ) as progress:
        task = progress.add_task("[cyan]Converting pages...", total=100)

        def rich_progress(curr, total):
            pct = (curr / total) * 100 if total else 0
            progress.update(task, completed=pct, description=f"[cyan]Page {curr}/{total}")

        try:
            _convert_cbz_to_pdf(cbz_path, progress_cb=rich_progress)
            elapsed = time.time() - start
            pdf_size = _human_size(output_pdf.stat().st_size) if output_pdf.exists() else "Unknown"

            _cli_console.print()
            _cli_console.print(_RichPanel(
                f"[success][+][/success] [bold green]Conversion completed![/bold green]\n\n"
                f"  • [info]Output PDF:[/] {output_pdf}\n"
                f"  • [info]Output Size:[/] {pdf_size}\n"
                f"  • [info]Time Taken:[/] {elapsed:.2f} seconds",
                border_style="green",
            ))
        except KeyboardInterrupt:
            _cli_console.print("\n  [warning][*][/warning] Conversion interrupted.")
        except Exception as e:
            _cli_console.print(f"\n  [error][!][/error] Failed to convert: {e}")


# ---------------------------------------------------------------------------
# Interactive TUI / Launcher Mode
# ---------------------------------------------------------------------------
def run_interactive_tui():
    """Terminal UI prompted launcher for CBZ → PDF."""
    try:
        from rich.console import Console as _RichConsole
        from rich.panel import Panel as _RichPanel
        from rich.prompt import Prompt as _RichPrompt
        from rich.theme import Theme as _RichTheme

        _cli_theme = _RichTheme({
            "info": "cyan",
            "success": "bold green",
            "warning": "bold yellow",
            "error": "bold red",
        })
        _cli_console = _RichConsole(theme=_cli_theme)
        _has_rich = True
    except ImportError:
        _has_rich = False

    if not _has_rich:
        path_str = input("Enter CBZ file/folder path (or press Enter to launch GUI): ").strip()
        if not path_str:
            app = CbzToPdfApp()
            app.mainloop()
        else:
            p = Path(path_str)
            if p.is_file() and p.suffix.lower() == ".cbz":
                run_cli_conversion(p)
            elif p.is_dir():
                cbz_files = _collect_cbz_files(str(p))
                if not cbz_files:
                    print("[ERROR] No .cbz files found in directory.")
                else:
                    for cbz in cbz_files:
                        run_cli_conversion(cbz)
            else:
                print(f"[ERROR] Invalid path: {path_str}")
        return

    _cli_console.print(
        _RichPanel(
            "[bold info]CBZ → PDF Converter[/bold info]\n\n"
            "  1. Convert CBZ file via CLI\n"
            "  2. Convert all CBZ files in a folder (CLI)\n"
            "  3. Launch graphical GUI (Drag-and-Drop)\n"
            "  0. Back / Exit",
            title="[bold]CBZ → PDF[/bold]",
            border_style="magenta",
            padding=(1, 3),
        )
    )

    choice = _RichPrompt.ask("  Choice", choices=["0", "1", "2", "3"], default="1")
    if choice == "0":
        return
    elif choice == "3":
        app = CbzToPdfApp()
        app.mainloop()
    elif choice == "1":
        path_str = _RichPrompt.ask("  Enter CBZ file path").strip()
        if path_str:
            p = Path(path_str)
            if p.is_file() and p.suffix.lower() == ".cbz":
                run_cli_conversion(p)
            else:
                _cli_console.print(f"  [error][!][/error] Not a valid CBZ file: '{path_str}'")
        else:
            _cli_console.print("  [warning][*][/warning] Empty path, returning.")
    elif choice == "2":
        path_str = _RichPrompt.ask("  Enter folder path containing CBZ files").strip()
        if path_str:
            p = Path(path_str)
            if p.is_dir():
                cbz_files = _collect_cbz_files(str(p))
                if not cbz_files:
                    _cli_console.print(f"  [error][!][/error] No .cbz files found in: '{path_str}'")
                else:
                    _cli_console.print(f"  [info][>][/info] Found [bold]{len(cbz_files)}[/bold] CBZ file(s).\n")
                    for cbz in cbz_files:
                        run_cli_conversion(cbz)
                        _cli_console.print()
            else:
                _cli_console.print(f"  [error][!][/error] Folder not found: '{path_str}'")
        else:
            _cli_console.print("  [warning][*][/warning] Empty path, returning.")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def run():
    """Entry point for the project's Rich-based main.py launcher."""
    run_interactive_tui()


def main():
    """Direct CLI entry point — supports argument or interactive mode."""
    if len(sys.argv) > 1:
        path_arg = Path(sys.argv[1])
        if path_arg.is_file() and path_arg.suffix.lower() == ".cbz":
            run_cli_conversion(path_arg)
        elif path_arg.is_dir():
            cbz_files = _collect_cbz_files(str(path_arg))
            if cbz_files:
                for cbz in cbz_files:
                    run_cli_conversion(cbz)
            else:
                print(f"[ERROR] No .cbz files found in: {sys.argv[1]}")
        else:
            print(f"[ERROR] Invalid path: {sys.argv[1]}")
    else:
        run_interactive_tui()


if __name__ == "__main__":
    main()

