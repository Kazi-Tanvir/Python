"""
PPT → ZIP Converter
====================
Converts PowerPoint (.pptx) files directly into ZIP (.zip) files.

Since .pptx files are already ZIP archives internally, this converter
simply copies each .pptx file to a .zip file with the same stem name.

    1.pptx → 1.zip
    2.pptx → 2.zip

Supports two modes:
    1. Single file  — Convert one .pptx to .zip
    2. Directory     — Convert all .pptx files in a directory to .zip files

Entry points:
    run()   — launched from the project's converter/main.py submenu
    main()  — direct CLI usage:  python ppt_to_zip.py /path/to/dir_or_file
"""

import os
import sys
import time
import shutil
from pathlib import Path

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


def _convert_pptx_to_zip(pptx_path: Path, output_zip: Path) -> Path:
    """
    Convert a .pptx file to .zip by copying it directly.

    PPTX files are already ZIP archives, so this is a straight copy
    with a changed extension.

    Parameters
    ----------
    pptx_path : Path
        Path to the source .pptx file.
    output_zip : Path
        Where to write the output .zip file.

    Returns
    -------
    Path
        The path to the created .zip file.
    """
    shutil.copy2(pptx_path, output_zip)
    return output_zip


# ---------------------------------------------------------------------------
# Single-file mode
# ---------------------------------------------------------------------------
def run_single_file_to_zip(pptx_path: Path) -> None:
    """Convert a single .pptx directly to .zip."""
    pptx_path = Path(pptx_path).resolve()

    if not pptx_path.exists():
        print_error(f"File not found: {pptx_path}")
        return
    if pptx_path.suffix.lower() != ".pptx":
        print_error(f"Not a PPTX file: {pptx_path.name}")
        return

    file_size = _human_size(pptx_path.stat().st_size)
    zip_output = pptx_path.parent / f"{pptx_path.stem}.zip"

    console.print()
    console.print(
        Panel(
            f"[bold info]PPT → ZIP Converter[/bold info]\n"
            f"File: [yellow]{pptx_path.name}[/yellow]  ({file_size})\n"
            f"Output: [yellow]{zip_output.name}[/yellow]",
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
        task = progress.add_task(
            f"[cyan]Converting {pptx_path.name}...", total=1
        )

        try:
            _convert_pptx_to_zip(pptx_path, zip_output)
            progress.update(task, completed=1, description=f"[green]{pptx_path.name} → {zip_output.name}")
        except Exception as e:
            print_error(f"Failed to convert: {e}")
            return

    elapsed = time.time() - start
    zip_size = _human_size(zip_output.stat().st_size) if zip_output.exists() else "Unknown"

    console.print()
    console.print(
        Panel(
            f"[success][+][/success] [bold green]ZIP created![/bold green]\n\n"
            f"  • [info]Output ZIP:[/] {zip_output}\n"
            f"  • [info]ZIP Size:[/]   {zip_size}\n"
            f"  • [info]Time Taken:[/] {elapsed:.2f} seconds",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# Directory batch mode
# ---------------------------------------------------------------------------
def run_directory_to_zip(directory: Path) -> None:
    """
    Convert all .pptx files in a directory to individual .zip files.

    Each .pptx becomes its own .zip:
        slide_deck_1.pptx → slide_deck_1.zip
        slide_deck_2.pptx → slide_deck_2.zip
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
            f"[bold info]PPT → ZIP Converter (Batch)[/bold info]\n\n"
            f"  Directory: [yellow]{directory}[/yellow]\n"
            f"  Files:     [bold]{len(pptx_files)}[/bold] PPTX file(s)\n"
            f"  Output:    Each .pptx → individual .zip",
            border_style="cyan",
        )
    )

    print_info(f"Found [bold]{len(pptx_files)}[/bold] PPTX file(s). Converting...")
    console.print()

    results = []  # (filename, status_str, detail)
    overall_start = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40, complete_style="cyan", finished_style="green"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Converting...", total=len(pptx_files)
        )

        for i, pptx_path in enumerate(pptx_files):
            zip_output = pptx_path.parent / f"{pptx_path.stem}.zip"
            file_size = _human_size(pptx_path.stat().st_size)

            try:
                _convert_pptx_to_zip(pptx_path, zip_output)
                zip_size = _human_size(zip_output.stat().st_size)
                results.append((pptx_path.name, "✓ Success", f"{zip_size}"))
                progress.update(
                    task,
                    completed=i + 1,
                    description=f"[cyan]{pptx_path.name} → {zip_output.name}",
                )
            except KeyboardInterrupt:
                results.append((pptx_path.name, "⚠ Interrupted", "User cancelled"))
                print_warning("Batch interrupted by user.")
                break
            except Exception as e:
                results.append((pptx_path.name, "✗ Failed", str(e)[:60]))

    overall_elapsed = time.time() - overall_start

    # Summary table
    table = Table(
        title=f"PPT → ZIP Summary  ({overall_elapsed:.1f}s total)",
        border_style="bright_cyan",
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("File", style="bold white")
    table.add_column("Status", justify="center")
    table.add_column("ZIP Size", style="dim")

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
    console.print(
        Panel(
            f"[success][+][/success] [bold green]Batch complete![/bold green]\n\n"
            f"  • [info]Converted:[/]  {success_count} / {len(pptx_files)} file(s)\n"
            f"  • [info]Time:[/]       {overall_elapsed:.2f} seconds",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# Interactive TUI
# ---------------------------------------------------------------------------
def run_interactive_tui():
    """Terminal UI prompted launcher for PPT → ZIP."""
    console.print(
        Panel(
            "[bold info]PPT → ZIP Converter[/bold info]\n\n"
            "  Converts each PPTX file directly into a ZIP file.\n"
            "  (PPTX files are already ZIP archives internally.)\n\n"
            "  1. Single PPTX file → ZIP\n"
            "  2. All PPTX in a directory → individual ZIPs\n"
            "  0. Back / Exit",
            title="[bold]PPT → ZIP[/bold]",
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
                run_single_file_to_zip(p)
            else:
                print_error(f"Not a valid PPTX file: '{path_str}'")
        else:
            print_warning("Empty path, returning.")
    elif choice == "2":
        dir_str = Prompt.ask("  Enter directory path containing PPTX files").strip()
        if dir_str:
            d = Path(dir_str)
            if d.is_dir():
                run_directory_to_zip(d)
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
            run_single_file_to_zip(path_arg)
        elif path_arg.is_dir():
            run_directory_to_zip(path_arg)
        else:
            print(f"[ERROR] Not a valid PPTX file or directory: {sys.argv[1]}")
    else:
        run_interactive_tui()


if __name__ == "__main__":
    main()
