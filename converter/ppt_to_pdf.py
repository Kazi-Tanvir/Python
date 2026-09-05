"""
PPT → PDF Converter
====================
Converts PowerPoint (.pptx) presentations into high-fidelity PDF files.

Uses python-pptx to read slides and PyMuPDF (fitz) to render each slide
as a high-resolution image, then stitches them into a single PDF.

Entry points:
    run()   — launched from the project's converter/main.py submenu
    main()  — direct CLI usage:  python ppt_to_pdf.py /path/to/file.pptx
"""

import gc
import os
import sys
import time
import shutil
import tempfile
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] PyMuPDF (pymupdf) is required. Install with: pip install pymupdf")
    sys.exit(1)

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
from rich.progress import (
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Prompt


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Render DPI — higher = sharper PDF but larger file
RENDER_DPI = 200
GC_INTERVAL = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _human_size(nbytes: int | float) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _emu_to_px(emu: int, dpi: int = RENDER_DPI) -> int:
    """Convert EMU (English Metric Units) to pixels at given DPI."""
    # 1 inch = 914400 EMU
    return int(emu * dpi / 914400)


def _render_slide_to_image(
    slide,
    slide_width_emu: int,
    slide_height_emu: int,
    dpi: int = RENDER_DPI,
) -> Image.Image:
    """
    Render a single PPTX slide to a Pillow Image.

    This renders text and shapes to a reasonable fidelity. For complex
    presentations with advanced transitions, SmartArt, or embedded media,
    results may vary.
    """
    if not _HAS_PIL:
        raise ImportError("Pillow is required for PPT → PDF conversion.")

    width_px = _emu_to_px(slide_width_emu, dpi)
    height_px = _emu_to_px(slide_height_emu, dpi)

    # Create canvas
    img = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(img)

    # Render slide background
    bg = slide.background
    if bg and bg.fill and bg.fill.type is not None:
        try:
            rgb = bg.fill.fore_color.rgb
            img.paste(
                (rgb[0], rgb[1], rgb[2]),
                (0, 0, width_px, height_px),
            )
        except (AttributeError, TypeError, ValueError):
            pass

    # Try to load a decent font
    try:
        font_large = ImageFont.truetype("arial.ttf", _emu_to_px(Pt(24).emu, dpi))
        font_medium = ImageFont.truetype("arial.ttf", _emu_to_px(Pt(18).emu, dpi))
        font_small = ImageFont.truetype("arial.ttf", _emu_to_px(Pt(14).emu, dpi))
    except (OSError, IOError):
        try:
            font_large = ImageFont.truetype("DejaVuSans.ttf", _emu_to_px(Pt(24).emu, dpi))
            font_medium = ImageFont.truetype("DejaVuSans.ttf", _emu_to_px(Pt(18).emu, dpi))
            font_small = ImageFont.truetype("DejaVuSans.ttf", _emu_to_px(Pt(14).emu, dpi))
        except (OSError, IOError):
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()

    for shape in slide.shapes:
        left_px = _emu_to_px(shape.left, dpi) if shape.left else 0
        top_px = _emu_to_px(shape.top, dpi) if shape.top else 0
        w_px = _emu_to_px(shape.width, dpi) if shape.width else 0
        h_px = _emu_to_px(shape.height, dpi) if shape.height else 0

        # Render images
        if shape.shape_type == 13:  # Picture
            try:
                image_stream = shape.image.blob
                pil_img = Image.open(__import__("io").BytesIO(image_stream))
                pil_img = pil_img.convert("RGB")
                pil_img = pil_img.resize((w_px, h_px), Image.LANCZOS)
                img.paste(pil_img, (left_px, top_px))
            except Exception:
                # Draw placeholder
                draw.rectangle(
                    [left_px, top_px, left_px + w_px, top_px + h_px],
                    outline="#cccccc",
                    width=2,
                )
                draw.text(
                    (left_px + 10, top_px + 10),
                    "[Image]",
                    fill="#888888",
                    font=font_small,
                )

        # Render text frames
        elif shape.has_text_frame:
            text_y = top_px
            for para in shape.text_frame.paragraphs:
                text = para.text
                if not text.strip():
                    text_y += _emu_to_px(Pt(8).emu, dpi)
                    continue

                # Pick font size based on runs
                font = font_small
                fill_color = "#333333"
                is_bold = False

                if para.runs:
                    run = para.runs[0]
                    font_size = run.font.size
                    if font_size:
                        pt_size = font_size.pt
                        if pt_size >= 20:
                            font = font_large
                        elif pt_size >= 14:
                            font = font_medium
                        else:
                            font = font_small
                    if run.font.bold:
                        is_bold = True
                    try:
                        if run.font.color and run.font.color.type is not None:
                            rgb = run.font.color.rgb
                            fill_color = f"#{rgb}"
                    except (AttributeError, TypeError, ValueError):
                        pass

                draw.text(
                    (left_px + 5, text_y),
                    text,
                    fill=fill_color,
                    font=font,
                )
                text_y += font.size + _emu_to_px(Pt(4).emu, dpi) if hasattr(font, 'size') else text_y + 20

        # Render tables
        elif shape.has_table:
            table = shape.table
            cell_h = h_px // max(len(table.rows), 1)
            cell_w = w_px // max(len(table.columns), 1)

            for row_idx, row in enumerate(table.rows):
                for col_idx, cell in enumerate(row.cells):
                    cx = left_px + col_idx * cell_w
                    cy = top_px + row_idx * cell_h
                    draw.rectangle(
                        [cx, cy, cx + cell_w, cy + cell_h],
                        outline="#aaaaaa",
                        width=1,
                    )
                    cell_text = cell.text.strip()
                    if cell_text:
                        draw.text(
                            (cx + 4, cy + 4),
                            cell_text[:50],
                            fill="#333333",
                            font=font_small,
                        )

    return img


# ---------------------------------------------------------------------------
# Core Conversion Engine
# ---------------------------------------------------------------------------
def convert_pptx_to_pdf(
    pptx_path: Path,
    output_pdf_path: Path | None = None,
    dpi: int = RENDER_DPI,
    progress_cb=None,
) -> Path:
    """
    Convert a .pptx file to PDF by rendering each slide as an image.

    Parameters
    ----------
    pptx_path : Path
        Path to the .pptx file.
    output_pdf_path : Path, optional
        Where to save the PDF. Defaults to [pptx_stem].pdf next to the source.
    dpi : int
        Rendering resolution. Higher = sharper but larger.
    progress_cb : callable, optional
        Called as progress_cb(current_slide, total_slides).

    Returns
    -------
    Path
        The path to the generated PDF.
    """
    pptx_path = Path(pptx_path).resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(f"File not found: {pptx_path}")
    if pptx_path.suffix.lower() not in (".pptx",):
        raise ValueError(f"Not a PowerPoint file: {pptx_path.name}")

    if output_pdf_path is None:
        output_pdf_path = pptx_path.parent / f"{pptx_path.stem}.pdf"

    prs = Presentation(str(pptx_path))
    slide_width = prs.slide_width
    slide_height = prs.slide_height
    slides = list(prs.slides)
    total_slides = len(slides)

    if total_slides == 0:
        raise ValueError("Presentation has no slides.")

    # Create temporary directory for slide images
    tmp_dir = tempfile.mkdtemp(prefix="ppt2pdf_")

    try:
        pdf_doc = fitz.open()

        for idx, slide in enumerate(slides):
            # Render slide to image
            slide_img = _render_slide_to_image(slide, slide_width, slide_height, dpi)

            # Save to temp file
            tmp_path = os.path.join(tmp_dir, f"slide_{idx:04d}.png")
            slide_img.save(tmp_path, "PNG")
            del slide_img

            # Insert into PDF
            img_doc = fitz.open(tmp_path)
            rect = img_doc[0].rect
            img_doc.close()
            del img_doc

            page = pdf_doc.new_page(width=rect.width, height=rect.height)
            page.insert_image(rect, filename=tmp_path)

            # Clean up temp image
            try:
                os.remove(tmp_path)
            except OSError:
                pass

            if progress_cb:
                progress_cb(idx + 1, total_slides)

            if idx % GC_INTERVAL == 0:
                gc.collect()

        # Save PDF
        pdf_doc.save(str(output_pdf_path), deflate=True, garbage=4)
        pdf_doc.close()
        del pdf_doc
        gc.collect()

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_pdf_path


# ---------------------------------------------------------------------------
# CLI Conversion with Rich progress
# ---------------------------------------------------------------------------
def run_cli_conversion(pptx_path: Path):
    """Run PPT → PDF conversion in terminal mode with rich progress display."""
    pptx_path = Path(pptx_path).resolve()

    if not pptx_path.exists():
        print_error(f"File not found: {pptx_path}")
        return
    if pptx_path.suffix.lower() != ".pptx":
        print_error(f"Not a PPTX file: {pptx_path.name}")
        return

    file_size = _human_size(pptx_path.stat().st_size)
    output_pdf = pptx_path.parent / f"{pptx_path.stem}.pdf"

    console.print()
    console.print(
        Panel(
            f"[bold info]PPT → PDF Converter[/bold info]\n"
            f"File: [yellow]{pptx_path.name}[/yellow]  ({file_size})",
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
            result = convert_pptx_to_pdf(pptx_path, output_pdf, progress_cb=rich_progress)
            elapsed = time.time() - start
            pdf_size = _human_size(result.stat().st_size) if result.exists() else "Unknown"

            console.print()
            console.print(
                Panel(
                    f"[success][+][/success] [bold green]Conversion completed![/bold green]\n\n"
                    f"  • [info]Output PDF:[/] {result}\n"
                    f"  • [info]Output Size:[/] {pdf_size}\n"
                    f"  • [info]Time Taken:[/] {elapsed:.2f} seconds",
                    border_style="green",
                )
            )
        except KeyboardInterrupt:
            console.print("\n  [warning][*][/warning] Conversion interrupted.")
        except Exception as e:
            console.print(f"\n  [error][!][/error] Failed to convert: {e}")


# ---------------------------------------------------------------------------
# Directory Batch Conversion
# ---------------------------------------------------------------------------
def run_directory_conversion(directory: Path) -> None:
    """
    Scan a directory for all .pptx files and convert each to PDF.

    Produces a summary table at the end showing results for every file.
    """
    from rich.table import Table

    directory = Path(directory).resolve()
    if not directory.is_dir():
        print_error(f"Not a valid directory: {directory}")
        return

    pptx_files = sorted(directory.glob("*.pptx"))
    if not pptx_files:
        print_warning(f"No .pptx files found in: {directory}")
        return

    print_info(f"Found [bold]{len(pptx_files)}[/bold] PPTX file(s) in: {directory}")
    console.print()

    results = []  # list of (filename, status, detail)
    overall_start = time.time()

    for i, pptx_path in enumerate(pptx_files, 1):
        file_size = _human_size(pptx_path.stat().st_size)
        output_pdf = pptx_path.parent / f"{pptx_path.stem}.pdf"
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
                result_path = convert_pptx_to_pdf(
                    pptx_path, output_pdf, progress_cb=rich_progress
                )
                elapsed = time.time() - start
                pdf_size = _human_size(result_path.stat().st_size)
                results.append((pptx_path.name, "✓ Success", f"{pdf_size} in {elapsed:.1f}s"))
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
        title=f"Batch Conversion Summary  ({overall_elapsed:.1f}s total)",
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
    """Terminal UI prompted launcher for PPT → PDF."""
    console.print(
        Panel(
            "[bold info]PPT → PDF Converter[/bold info]\n\n"
            "  1. Convert a single PPTX file to PDF\n"
            "  2. Batch convert all PPTX in a directory\n"
            "  0. Back / Exit",
            title="[bold]PPT → PDF[/bold]",
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
                run_cli_conversion(p)
            else:
                print_error(f"Not a valid PPTX file: '{path_str}'")
        else:
            print_warning("Empty path, returning.")
    elif choice == "2":
        dir_str = Prompt.ask("  Enter directory path containing PPTX files").strip()
        if dir_str:
            d = Path(dir_str)
            if d.is_dir():
                run_directory_conversion(d)
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
            run_cli_conversion(path_arg)
        elif path_arg.is_dir():
            run_directory_conversion(path_arg)
        else:
            print(f"[ERROR] Not a valid PPTX file or directory: {sys.argv[1]}")
    else:
        run_interactive_tui()


if __name__ == "__main__":
    main()
