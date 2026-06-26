"""
YouTube Downloader Module
Supports single videos, playlists, and bulk downloads from yt_links.txt.
Uses yt-dlp with optional aria2c acceleration and FFmpeg merging.
"""

import os
import re
import sys
import time
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
from rich.prompt import Prompt, IntPrompt

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
    check_aria2c,
    get_bulk_workers,
)


# ---------------------------------------------------------------------------
# URL classification
# ---------------------------------------------------------------------------
_PLAYLIST_PATTERNS = [
    re.compile(r"[?&]list="),
    re.compile(r"youtube\.com/playlist"),
]


def _is_playlist(url: str) -> bool:
    return any(p.search(url) for p in _PLAYLIST_PATTERNS)


# ---------------------------------------------------------------------------
# Extract video/playlist info
# ---------------------------------------------------------------------------
def _extract_info(url: str, quiet: bool = True) -> dict | None:
    """Extract metadata without downloading."""
    ydl_opts = {
        "quiet": quiet,
        "no_warnings": quiet,
        "extract_flat": False,
    }
    ffmpeg = check_ffmpeg()
    if ffmpeg:
        ydl_opts["ffmpeg_location"] = str(Path(ffmpeg).parent)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        print_error(f"Failed to extract info: {e}")
        return None


def _get_available_qualities(info: dict) -> list[dict]:
    """
    Parse formats and return a deduplicated list of video qualities.
    Returns list of dicts: {height, format_note, fps, vcodec, filesize_approx}
    """
    formats = info.get("formats", [])
    seen = set()
    qualities = []

    for f in formats:
        height = f.get("height")
        if not height or f.get("vcodec") == "none":
            continue
        if height in seen:
            continue
        seen.add(height)
        qualities.append({
            "height": height,
            "format_note": f.get("format_note", ""),
            "fps": f.get("fps", ""),
            "vcodec": (f.get("vcodec") or "unknown").split(".")[0],
            "filesize_approx": f.get("filesize_approx") or f.get("filesize") or 0,
        })

    qualities.sort(key=lambda q: q["height"], reverse=True)
    return qualities


def _display_qualities(qualities: list[dict]) -> None:
    """Show available qualities in a Rich table."""
    table = Table(
        title="Available Qualities",
        border_style="bright_cyan",
        show_lines=True,
    )
    table.add_column("#", style="bold cyan", justify="center", width=4)
    table.add_column("Resolution", style="bold white", justify="center")
    table.add_column("FPS", justify="center")
    table.add_column("Codec", style="dim")
    table.add_column("Size (approx)", justify="right", style="dim")

    for i, q in enumerate(qualities, 1):
        size_str = ""
        if q["filesize_approx"]:
            mb = q["filesize_approx"] / (1024 * 1024)
            if mb >= 1024:
                size_str = f"{mb / 1024:.1f} GB"
            else:
                size_str = f"{mb:.1f} MB"

        table.add_row(
            str(i),
            f"{q['height']}p",
            str(q["fps"]) if q["fps"] else "-",
            q["vcodec"],
            size_str or "-",
        )

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Build yt-dlp options
# ---------------------------------------------------------------------------
def _build_ydl_opts(
    target_height: int,
    download_dir: Path,
    progress_hook=None,
) -> dict:
    """Build yt-dlp options dict."""
    # Format selection with fallback:
    # Try target height first, fall back to best available
    format_str = (
        f"bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={target_height}]+bestaudio/"
        f"bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo+bestaudio/"
        f"best"
    )

    opts = {
        "format": format_str,
        "outtmpl": str(download_dir / "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "consoletitle": False,
        "restrictfilenames": False,
        "windowsfilenames": True,
    }

    # FFmpeg
    ffmpeg = check_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
    else:
        # Without ffmpeg, fall back to single-stream best to avoid merge errors
        opts["format"] = f"best[height<={target_height}]/best"

    # Speed: aria2c or concurrent fragments
    aria2c = check_aria2c()
    if aria2c:
        opts["external_downloader"] = "aria2c"
        opts["external_downloader_args"] = {
            "aria2c": ["-x", "16", "-s", "16", "-j", "4", "--min-split-size=1M"]
        }
    else:
        opts["concurrent_fragment_downloads"] = 8

    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


# ---------------------------------------------------------------------------
# Download with Rich progress
# ---------------------------------------------------------------------------
def _download_single(url: str, target_height: int, download_dir: Path) -> bool:
    """Download a single video with a Rich progress bar."""
    info = _extract_info(url)
    if not info:
        return False

    title = info.get("title", "Unknown")
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
        task_id = progress.add_task(
            f"Downloading",
            total=None,
        )

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

        opts = _build_ydl_opts(target_height, download_dir, progress_hook=hook)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            print_success(f"Downloaded: {title}")
            return True
        except yt_dlp.utils.DownloadError as e:
            print_error(f"Download failed: {e}")
            return False


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------
def _ask_quality(info: dict) -> int:
    """Show available qualities and let the user pick. Default 1080p."""
    qualities = _get_available_qualities(info)

    if not qualities:
        print_warning("Could not detect quality options. Defaulting to best.")
        return 9999  # Will resolve to best

    _display_qualities(qualities)

    # Find default (1080p or closest)
    default_idx = 0
    for i, q in enumerate(qualities):
        if q["height"] <= 1080:
            default_idx = i
            break

    console.print()
    choice = Prompt.ask(
        f"  Select quality [1-{len(qualities)}]",
        default=str(default_idx + 1),
    )

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(qualities):
            selected = qualities[idx]["height"]
            print_info(f"Selected: {selected}p")
            return selected
    except ValueError:
        pass

    print_warning("Invalid choice, defaulting to 1080p.")
    return 1080


def run_single_download() -> None:
    """Interactive: download a single YouTube video."""
    console.print()
    url = Prompt.ask("  Enter YouTube video URL")
    if not url.strip():
        print_error("No URL provided.")
        return

    print_info("Fetching video info...")
    info = _extract_info(url)
    if not info:
        return

    target_height = _ask_quality(info)
    download_dir = get_download_dir("youtube")
    print_info(f"Saving to: {download_dir}")
    console.print()

    _download_single(url, target_height, download_dir)


def run_playlist_download() -> None:
    """Interactive: download a YouTube playlist."""
    console.print()
    url = Prompt.ask("  Enter YouTube playlist URL")
    if not url.strip():
        print_error("No URL provided.")
        return

    print_info("Fetching playlist info...")
    info = _extract_info(url)
    if not info:
        return

    entries = info.get("entries", [])
    if not entries:
        print_warning("No videos found in playlist. Trying as single video...")
        run_single_download()
        return

    # Filter out None entries (private/deleted videos)
    entries = [e for e in entries if e is not None]

    playlist_title = info.get("title", "Unknown Playlist")
    print_info(f"Playlist: {playlist_title}")
    print_info(f"Videos: {len(entries)}")

    # Ask for quality preference (will apply with fallback to each video)
    console.print()
    console.print("  Select quality preference for all videos:")
    console.print("  (If unavailable for a video, highest quality will be used)")
    console.print()
    target_height = IntPrompt.ask(
        "  Target height (e.g. 1080, 720, 480)",
        default=1080,
    )

    download_dir = get_download_dir("youtube")
    print_info(f"Saving to: {download_dir}")
    console.print()

    # Download each video
    success_count = 0
    fail_count = 0

    for i, entry in enumerate(entries, 1):
        video_url = entry.get("webpage_url") or entry.get("url", "")
        video_title = entry.get("title", f"Video {i}")
        console.rule(f"[cyan]{i}/{len(entries)}[/cyan] {video_title}", style="dim")

        if _download_single(video_url, target_height, download_dir):
            success_count += 1
        else:
            fail_count += 1
        console.print()

    # Summary
    summary = Table(title="Playlist Download Summary", border_style="bright_cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")
    summary.add_row("Total Videos", str(len(entries)))
    summary.add_row("Successful", f"[green]{success_count}[/green]")
    summary.add_row("Failed", f"[red]{fail_count}[/red]" if fail_count else "[green]0[/green]")
    console.print(summary)


def run_bulk_download() -> None:
    """Bulk download from yt_links.txt with parallel workers."""
    links_file = get_downloader_dir() / "yt_links.txt"
    links = read_links_file(links_file)
    if not links:
        print_error(f"No links found. Add YouTube URLs to: {links_file}")
        return

    console.print()
    target_height = IntPrompt.ask(
        "  Target quality for all videos (e.g. 1080, 720, 480)",
        default=1080,
    )

    download_dir = get_download_dir("youtube")
    workers = get_bulk_workers()
    print_info(f"Downloading {len(links)} video(s) with {workers} parallel worker(s)")
    print_info(f"Saving to: {download_dir}")
    console.print()

    success_count = 0
    fail_count = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i, url in enumerate(links, 1):
            future = executor.submit(_download_single, url, target_height, download_dir)
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
    """YouTube Downloader interactive menu."""
    print_banner("YOUTUBE DOWNLOADER", "Download videos and playlists from YouTube")

    # FFmpeg check
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
                "[bold cyan]2[/]  Playlist\n"
                "[bold cyan]3[/]  Bulk Download (yt_links.txt)\n"
                "[bold cyan]0[/]  Back to Main Menu",
                title="[bold]YouTube Options[/bold]",
                border_style="cyan",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask("  Choice", choices=["0", "1", "2", "3"], default="1")

        if choice == "0":
            break
        elif choice == "1":
            url = Prompt.ask("\n  Enter YouTube URL")
            if not url.strip():
                print_error("No URL provided.")
                continue
            if _is_playlist(url):
                print_info("Playlist URL detected.")
                run_playlist_download_from_url(url)
            else:
                run_single_download_from_url(url)
        elif choice == "2":
            run_playlist_download()
        elif choice == "3":
            run_bulk_download()


def run_single_download_from_url(url: str) -> None:
    """Download a single video when the URL is already provided."""
    print_info("Fetching video info...")
    info = _extract_info(url)
    if not info:
        return

    target_height = _ask_quality(info)
    download_dir = get_download_dir("youtube")
    print_info(f"Saving to: {download_dir}")
    console.print()
    _download_single(url, target_height, download_dir)


def run_playlist_download_from_url(url: str) -> None:
    """Download a playlist when the URL is already provided."""
    print_info("Fetching playlist info...")
    info = _extract_info(url)
    if not info:
        return

    entries = info.get("entries", [])
    if not entries:
        print_warning("No entries found in playlist, trying as single video...")
        run_single_download_from_url(url)
        return

    entries = [e for e in entries if e is not None]
    playlist_title = info.get("title", "Unknown Playlist")
    print_info(f"Playlist: {playlist_title}")
    print_info(f"Videos: {len(entries)}")

    console.print()
    target_height = IntPrompt.ask(
        "  Target quality for all videos (e.g. 1080, 720, 480)",
        default=1080,
    )

    download_dir = get_download_dir("youtube")
    print_info(f"Saving to: {download_dir}")
    console.print()

    success_count = 0
    fail_count = 0

    for i, entry in enumerate(entries, 1):
        video_url = entry.get("webpage_url") or entry.get("url", "")
        video_title = entry.get("title", f"Video {i}")
        console.rule(f"[cyan]{i}/{len(entries)}[/cyan] {video_title}", style="dim")

        if _download_single(video_url, target_height, download_dir):
            success_count += 1
        else:
            fail_count += 1
        console.print()

    summary = Table(title="Playlist Download Summary", border_style="bright_cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")
    summary.add_row("Total Videos", str(len(entries)))
    summary.add_row("Successful", f"[green]{success_count}[/green]")
    summary.add_row("Failed", f"[red]{fail_count}[/red]" if fail_count else "[green]0[/green]")
    console.print(summary)


if __name__ == "__main__":
    run()
