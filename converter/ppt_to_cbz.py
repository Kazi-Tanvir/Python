"""
PPT → CBZ Converter
====================
Converts PowerPoint (.pptx) presentations into CBZ (Comic Book ZIP) archives.

Each slide is rendered as a high-resolution image and packed into a CBZ file
with proper ordering. CBZ files are ZIP archives containing sequentially
named image files, readable by most comic book readers and image viewers.

Supports two modes:
    1. Single file  — Convert one .pptx to .cbz
    2. Directory     — Convert all .pptx files in a directory to .cbz files

Entry points:
    run()   — launched from the project's converter/main.py submenu
    main()  — direct CLI usage:  python ppt_to_cbz.py /path/to/dir_or_file
"""

import gc
import os
import sys
import time
import shutil
import zipfile
import tempfile
from pathlib import Path

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.enum.text import PP_ALIGN
except ImportError:
    print("[ERROR] python-pptx is required. Install with: pip install python-pptx")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

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
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Prompt

# Re-use the slide rendering engine from ppt_to_pdf
from converter.ppt_to_pdf import _render_slide_to_image, _human_size


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RENDER_DPI = 200
GC_INTERVAL = 10


# ---------------------------------------------------------------------------
# Core Conversion Engine
# ---------------------------------------------------------------------------
def convert_pptx_to_cbz(
    pptx_path: Path,
    output_cbz_path: Path | None = None,
    dpi: int = RENDER_DPI,
    image_format: str = "JPEG",
    image_quality: int = 90,
    progress_cb=None,
) -> Path:
    """
    Convert a .pptx file to CBZ by rendering each slide as an image.

    The CBZ format is a ZIP archive containing sequentially named image files.
    Each slide becomes one page image in the archive.

    Parameters
    ----------
    pptx_path : Path
        Path to the .pptx file.
    output_cbz_path : Path, optional
        Where to save the CBZ. Defaults to [pptx_stem].cbz next to the source.
    dpi : int
        Rendering resolution. Higher = sharper but larger.
    image_format : str
        Output image format: "JPEG" or "PNG".
    image_quality : int
        JPEG quality (1-100). Ignored for PNG.
    progress_cb : callable, optional
        Called as progress_cb(current_slide, total_slides).

    Returns
    -------
    Path
        The path to the generated CBZ file.
    """
    if not _HAS_PIL:
        raise ImportError("Pillow is required for PPT → CBZ conversion. Install with: pip install Pillow")

    pptx_path = Path(pptx_path).resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(f"File not found: {pptx_path}")
    if pptx_path.suffix.lower() not in (".pptx",):
        raise ValueError(f"Not a PowerPoint file: {pptx_path.name}")

    if output_cbz_path is None:
        output_cbz_path = pptx_path.parent / f"{pptx_path.stem}.cbz"

    prs = Presentation(str(pptx_path))
    slide_width = prs.slide_width
    slide_height = prs.slide_height
    slides = list(prs.slides)
    total_slides = len(slides)

    if total_slides == 0:
        raise ValueError("Presentation has no slides.")

    # Determine file extension for images inside the CBZ
    ext = ".jpg" if image_format.upper() == "JPEG" else ".png"

    # Create temporary directory for slide images
    tmp_dir = tempfile.mkdtemp(prefix="ppt2cbz_")

    try:
        image_paths = []

        for idx, slide in enumerate(slides):
            # Render slide to image
            slide_img = _render_slide_to_image(slide, slide_width, slide_height, dpi)

            # Save to temp file with sequential naming for proper ordering
            # Zero-padded numbering ensures correct sort order in CBZ readers
            tmp_path = os.path.join(tmp_dir, f"page_{idx + 1:04d}{ext}")

            if image_format.upper() == "JPEG":
                # Convert RGBA to RGB for JPEG
                if slide_img.mode == "RGBA":
                    slide_img = slide_img.convert("RGB")
                slide_img.save(tmp_path, "JPEG", quality=image_quality, optimize=True)
            else:
                slide_img.save(tmp_path, "PNG", optimize=True)

            image_paths.append(tmp_path)
            del slide_img

            if progress_cb:
                progress_cb(idx + 1, total_slides)

            if idx % GC_INTERVAL == 0:
                gc.collect()

        # Create CBZ archive (ZIP with images)
        with zipfile.ZipFile(output_cbz_path, "w", zipfile.ZIP_STORED) as cbz:
            for img_path in image_paths:
                cbz.write(img_path, arcname=os.path.basename(img_path))

        gc.collect()

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_cbz_path


# ---------------------------------------------------------------------------
# Single-file mode with Rich progress
# ---------------------------------------------------------------------------
def run_single_file_to_cbz(pptx_path: Path) -> None:
    """Convert a single .pptx to .cbz with a rich progress display."""
    pptx_path = Path(pptx_path).resolve()

    if not pptx_path.exists():
        print_error(f"File not found: {pptx_path}")
        return
    if pptx_path.suffix.lower() != ".pptx":
        print_error(f"Not a PPTX file: {pptx_path.name}")
        return

    file_size = _human_size(pptx_path.stat().st_size)
    cbz_output = pptx_path.parent / f"{pptx_path.stem}.cbz"

    console.print()
    console.print(
        Panel(
            f"[bold info]PPT → CBZ Converter[/bold info]\n"
            f"File: [yellow]{pptx_path.name}[/yellow]  ({file_size})\n"
            f"Output: [yellow]{cbz_output.name}[/yellow]",
            border_style="cyan",
        )
    )

    start = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40, complete_style="cyan", finished_style="green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Rendering slides...", total=100)

        def rich_progress(curr, total):
            pct = (curr / total) * 100 if total else 0
            progress.update(
                task,
                completed=pct,
                description=f"[cyan]Slide {curr}/{total}",
            )

        try:
            result = convert_pptx_to_cbz(pptx_path, cbz_output, progress_cb=rich_progress)
            elapsed = time.time() - start
            cbz_size = _human_size(result.stat().st_size) if result.exists() else "Unknown"

            console.print()
            console.print(
                Panel(
                    f"[success][+][/success] [bold green]CBZ created![/bold green]\n\n"
                    f"  • [info]Output CBZ:[/] {result}\n"
                    f"  • [info]CBZ Size:[/]   {cbz_size}\n"
                    f"  • [info]Time Taken:[/] {elapsed:.2f} seconds",
                    border_style="green",
                )
            )
        except KeyboardInterrupt:
            console.print("\n  [warning][*][/warning] Conversion interrupted.")
        except Exception as e:
            console.print(f"\n  [error][!][/error] Failed to convert: {e}")


# ---------------------------------------------------------------------------
# Directory batch mode
# ---------------------------------------------------------------------------
def run_directory_to_cbz(directory: Path) -> None:
    """
    Convert all .pptx files in a directory to individual .cbz files.

    Each .pptx becomes its own .cbz:
        slide_deck_1.pptx → slide_deck_1.cbz
        slide_deck_2.pptx → slide_deck_2.cbz
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        print_error(f"Not a valid directory: {directory}")
        return

    pptx_files = sorted(directory.glob("*.pptx"))
    if not pptx_files:
        print_warning(f"No .pptx files found in: {directory}")
        return

    console.print()
    console.print(
        Panel(
            f"[bold info]PPT → CBZ Converter (Batch)[/bold info]\n\n"
            f"  Directory: [yellow]{directory}[/yellow]\n"
            f"  Files:     [bold]{len(pptx_files)}[/bold] PPTX file(s)\n"
            f"  Output:    Each .pptx → individual .cbz",
            border_style="cyan",
        )
    )

    print_info(f"Found [bold]{len(pptx_files)}[/bold] PPTX file(s). Converting...")
    console.print()

    results = []  # (filename, status_str, detail)
    overall_start = time.time()

    for i, pptx_path in enumerate(pptx_files, 1):
        file_size = _human_size(pptx_path.stat().st_size)
        cbz_output = pptx_path.parent / f"{pptx_path.stem}.cbz"
        console.rule(
            f"[cyan]{i}/{len(pptx_files)}[/cyan]  {pptx_path.name}  ({file_size})",
            style="dim",
        )

        start = time.time()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=40, complete_style="cyan", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Rendering slides...", total=100)

            def rich_progress(curr, total, _task=task, _progress=progress):
                pct = (curr / total) * 100 if total else 0
                _progress.update(
                    _task,
                    completed=pct,
                    description=f"[cyan]Slide {curr}/{total}",
                )

            try:
                result_path = convert_pptx_to_cbz(
                    pptx_path, cbz_output, progress_cb=rich_progress
                )
                elapsed = time.time() - start
                cbz_size = _human_size(result_path.stat().st_size)
                results.append((pptx_path.name, "✓ Success", f"{cbz_size} in {elapsed:.1f}s"))
                print_success(f"{pptx_path.name} → {result_path.name}")
            except KeyboardInterrupt:
                results.append((pptx_path.name, "⚠ Interrupted", "User cancelled"))
                print_warning("Batch interrupted by user.")
                break
            except Exception as e:
                results.append((pptx_path.name, "✗ Failed", str(e)[:60]))
                print_error(f"Failed: {pptx_path.name} — {e}")

        console.print()

    # Summary table
    overall_elapsed = time.time() - overall_start
    table = Table(
        title=f"PPT → CBZ Summary  ({overall_elapsed:.1f}s total)",
        border_style="bright_cyan",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("File", style="bold white")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    for idx, (fname, status, detail) in enumerate(results, 1):
        status_style = (
            "[green]" if "Success" in status
            else "[yellow]" if "Interrupted" in status
            else "[red]"
        )
        table.add_row(str(idx), fname, f"{status_style}{status}", detail)

    console.print()
    console.print(table)
    console.print()

    success_count = sum(1 for _, s, _ in results if "Success" in s)
    print_info(
        f"Converted [bold]{success_count}[/bold] / {len(pptx_files)} file(s) successfully."
    )


# ---------------------------------------------------------------------------
# Interactive TUI
# ---------------------------------------------------------------------------
def run_interactive_tui():
    """Terminal UI prompted launcher for PPT → CBZ."""
    console.print(
        Panel(
            "[bold info]PPT → CBZ Converter[/bold info]\n\n"
            "  Renders each slide as a high-resolution image and\n"
            "  packages them into a CBZ (Comic Book ZIP) archive.\n\n"
            "  1. Single PPTX file → CBZ\n"
            "  2. All PPTX in a directory → individual CBZs\n"
            "  0. Back / Exit",
            title="[bold]PPT → CBZ[/bold]",
            border_style="magenta",
            padding=(1, 3),
        )
    )

    choice = Prompt.ask("  Choice", choices=["0", "1", "2"], default="1")
    if choice == "0":
        return
    elif choice == "1":
        path_str = Prompt.ask("  Enter PPTX file path").strip()
        if path_str:
            p = Path(path_str)
            if p.is_file() and p.suffix.lower() == ".pptx":
                run_single_file_to_cbz(p)
            else:
                print_error(f"Not a valid PPTX file: '{path_str}'")
        else:
            print_warning("Empty path, returning.")
    elif choice == "2":
        dir_str = Prompt.ask("  Enter directory path containing PPTX files").strip()
        if dir_str:
            d = Path(dir_str)
            if d.is_dir():
                run_directory_to_cbz(d)
            else:
                print_error(f"Not a valid directory: '{dir_str}'")
        else:
            print_warning("Empty path, returning.")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------
def run():
    """Entry point for the project's converter/main.py submenu."""
    run_interactive_tui()


def main():
    """Direct CLI entry point."""
    if len(sys.argv) > 1:
        path_arg = Path(sys.argv[1])
        if path_arg.is_file() and path_arg.suffix.lower() == ".pptx":
            run_single_file_to_cbz(path_arg)
        elif path_arg.is_dir():
            run_directory_to_cbz(path_arg)
        else:
            print(f"[ERROR] Not a valid PPTX file or directory: {sys.argv[1]}")
    else:
        run_interactive_tui()


if __name__ == "__main__":
    main()
