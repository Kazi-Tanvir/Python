"""
Facebook Downloader Module
Downloads Facebook videos at the highest quality using yt-dlp.
Supports single URLs and bulk downloads from fb_links.txt.
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

from .utils import (
    console,
    print_banner,
    print_success,
    print_error,
    print_warning,
    print_info,
    sanitize_filename,
    get_download_dir,
    get_downloader_dir,
    read_links_file,
    check_ffmpeg,
    get_env,
    get_bulk_workers,
)


# ---------------------------------------------------------------------------
# Build yt-dlp options for Facebook (always best quality)
# ---------------------------------------------------------------------------
def _build_ydl_opts(download_dir: Path, progress_hook=None) -> dict:
    """Build yt-dlp options for Facebook downloads (always HD)."""
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
        # Without FFmpeg, fall back to single-stream best
        opts["format"] = "best[ext=mp4]/best"

    # Cookies for restricted content
    cookies_file = get_env("FB_COOKIES_FILE")
    if cookies_file and Path(cookies_file).exists():
        opts["cookiefile"] = cookies_file

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


# ---------------------------------------------------------------------------
# Download a single Facebook video
# ---------------------------------------------------------------------------
def _download_single(url: str, download_dir: Path) -> bool:
    """Download a single Facebook video with Rich progress bar."""
    # Extract info first to show title
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        print_error(f"Failed to extract info: {e}")
        return False

    title = info.get("title", "Facebook Video")
    print_info(f"Title: {title}")

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
            print_success(f"Downloaded: {title}")
            return True
        except yt_dlp.utils.DownloadError as e:
            print_error(f"Download failed: {e}")
            return False


# ---------------------------------------------------------------------------
# Interactive modes
# ---------------------------------------------------------------------------
def run_single_download() -> None:
    """Interactive: download a single Facebook video."""
    console.print()
    url = Prompt.ask("  Enter Facebook video URL")
    if not url.strip():
        print_error("No URL provided.")
        return

    download_dir = get_download_dir("facebook")
    print_info(f"Saving to: {download_dir}")
    print_info("Downloading at highest quality (HD)...")
    console.print()

    _download_single(url, download_dir)


def run_bulk_download() -> None:
    """Bulk download from fb_links.txt with parallel workers."""
    links_file = get_downloader_dir() / "fb_links.txt"
    links = read_links_file(links_file)
    if not links:
        print_error(f"No links found. Add Facebook URLs to: {links_file}")
        return

    download_dir = get_download_dir("facebook")
    workers = get_bulk_workers()
    print_info(f"Downloading {len(links)} video(s) with {workers} parallel worker(s)")
    print_info(f"Saving to: {download_dir}")
    print_info("All videos will be downloaded at highest quality (HD).")
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
    """Facebook Downloader interactive menu."""
    print_banner("FACEBOOK DOWNLOADER", "Download videos from Facebook in HD")

    if not check_ffmpeg():
        print_warning(
            "FFmpeg not found. Videos may download without audio or at lower quality."
        )
        print_info("See 01_Downloader/FFMPEG_SETUP.md for installation instructions.")
        console.print()

    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  Single Video\n"
                "[bold cyan]2[/]  Bulk Download (fb_links.txt)\n"
                "[bold cyan]0[/]  Back to Main Menu",
                title="[bold]Facebook Options[/bold]",
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
