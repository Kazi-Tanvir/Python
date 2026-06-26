"""
X (Twitter) Downloader Module
Downloads videos from X/Twitter at the highest quality using yt-dlp.
Supports single URLs and bulk downloads from x_links.txt.
"""

import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp

from rich.table import Table
from rich.panel import Panel
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    SpinnerColumn,
)
from rich.prompt import Prompt

from shared.console import (
    console,
    print_banner,
    print_success,
    print_error,
    print_warning,
    print_info,
)
from shared.config import PROJECT_ROOT, get_env

from .utils import (
    sanitize_filename,
    get_download_dir,
    read_links_file,
    check_ffmpeg,
    get_bulk_workers,
)


def get_config_dir() -> Path:
    return PROJECT_ROOT / "config"


# ---------------------------------------------------------------------------
# Build yt-dlp options for X/Twitter
# ---------------------------------------------------------------------------
def _build_ydl_opts(download_dir: Path, progress_hook=None) -> dict:
    """Build yt-dlp options for X/Twitter video downloads."""
    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(download_dir / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "consoletitle": False,
        "windowsfilenames": True,
    }

    # FFmpeg
    ffmpeg = check_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
    else:
        # Without FFmpeg, fall back to best single-stream
        opts["format"] = "best[ext=mp4]/best"

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


# ---------------------------------------------------------------------------
# Download a single X/Twitter video
# ---------------------------------------------------------------------------
def _download_single(url: str, download_dir: Path) -> bool:
    """Download a single X/Twitter video with Rich progress bar."""
    if not url.strip():
        return False

    # Extract info first to show title
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        print_error(f"Failed to extract info for {url}: {e}")
        return False

    title = info.get("title", "X Video")
    # Clean up title for logs
    display_title = title if len(title) <= 50 else title[:47] + "..."
    print_info(f"Title: {display_title}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:
        task_id = progress.add_task("Downloading", total=None)

        def hook(d):
            if d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    progress.update(task_id, completed=downloaded, total=total)
                else:
                    progress.update(task_id, completed=downloaded)
            elif d["status"] == "finished":
                progress.update(
                    task_id,
                    description="Merging streams" if check_ffmpeg() else "Finalizing",
                )

        opts = _build_ydl_opts(download_dir, progress_hook=hook)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            print_success(f"Downloaded: {display_title}")
            return True
        except yt_dlp.utils.DownloadError as e:
            print_error(f"Download failed for {url}: {e}")
            return False


# ---------------------------------------------------------------------------
# Interactive modes
# ---------------------------------------------------------------------------
def run_single_download() -> None:
    """Interactive: download a single X/Twitter video."""
    console.print()
    url = Prompt.ask("  Enter X (Twitter) video URL")
    if not url.strip():
        print_error("No URL provided.")
        return

    download_dir = get_download_dir("x")
    print_info(f"Saving to: {download_dir}")
    print_info("Downloading at highest quality...")
    console.print()

    _download_single(url, download_dir)


def run_bulk_download() -> None:
    """Bulk download from x_links.txt with parallel workers."""
    links_file = get_config_dir() / "x_links.txt"
    links = read_links_file(links_file)
    if not links:
        print_error(f"No links found. Add X/Twitter URLs to: {links_file}")
        return

    download_dir = get_download_dir("x")
    workers = get_bulk_workers()
    print_info(f"Downloading {len(links)} video(s) with {workers} parallel worker(s)")
    print_info(f"Saving to: {download_dir}")
    console.print()

    success_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i, url in enumerate(links, 1):
            future = executor.submit(_download_single, url, download_dir)
            futures[future] = (i, url)

        for future in as_completed(futures):
            idx, url = futures[future]
            try:
                if future.result():
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                print_error(f"[{idx}] Unexpected error: {e}")
                fail_count += 1

    # Summary
    console.print()
    summary = Table(title="Bulk Download Summary", border_style="bright_cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")
    summary.add_row("Total", str(len(links)))
    summary.add_row("Successful", f"[green]{success_count}[/green]")
    summary.add_row("Failed", f"[red]{fail_count}[/red]" if fail_count else "[green]0[/green]")
    console.print(summary)


# ---------------------------------------------------------------------------
# Main menu for standalone usage
# ---------------------------------------------------------------------------
def run() -> None:
    """X/Twitter Downloader interactive menu."""
    print_banner("X (TWITTER) DOWNLOADER", "Download videos from X/Twitter at highest quality")

    if not check_ffmpeg():
        print_warning(
            "FFmpeg not found. Videos may download without audio or at lower quality."
        )
        print_info("See downloader/FFMPEG_SETUP.md for installation instructions.")
        console.print()

    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  Single Video\n"
                "[bold cyan]2[/]  Bulk Download (x_links.txt)\n"
                "[bold cyan]0[/]  Back to Main Menu",
                title="[bold]X Options[/bold]",
                border_style="cyan",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask("  Choice", choices=["0", "1", "2"], default="1")

        if choice == "0":
            break
        elif choice == "1":
            run_single_download()
        elif choice == "2":
            run_bulk_download()


if __name__ == "__main__":
    run()
