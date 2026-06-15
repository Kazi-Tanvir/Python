"""
Shared utilities for the Media Downloader suite.
Provides sanitization, Rich helpers, file readers, and environment helpers.
"""

import os
import re
import sys
import shutil
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Load .env from project root (98_PYTHON)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Rich Theme & Console
# ---------------------------------------------------------------------------
CUSTOM_THEME = Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "title": "bold magenta",
    "subtitle": "dim white",
    "highlight": "bold cyan",
    "muted": "dim",
})

console = Console(theme=CUSTOM_THEME)


# ---------------------------------------------------------------------------
# Styled output helpers
# ---------------------------------------------------------------------------
def print_banner(title: str, subtitle: str = "") -> None:
    """Print a styled banner panel."""
    content = Text(title, style="title", justify="center")
    if subtitle:
        content.append(f"\n{subtitle}", style="subtitle")
    console.print(
        Panel(
            content,
            border_style="bright_magenta",
            padding=(1, 4),
        )
    )


def print_success(msg: str) -> None:
    console.print(f"  [success][+][/success] {msg}")


def print_error(msg: str) -> None:
    console.print(f"  [error][!][/error] {msg}")


def print_warning(msg: str) -> None:
    console.print(f"  [warning][*][/warning] {msg}")


def print_info(msg: str) -> None:
    console.print(f"  [info][>][/info] {msg}")


# ---------------------------------------------------------------------------
# Filename sanitisation (Windows-safe)
# ---------------------------------------------------------------------------
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Remove characters illegal in Windows filenames and trim length."""
    name = _INVALID_CHARS.sub("_", name)
    name = name.strip(". ")
    if len(name) > max_length:
        name = name[:max_length]
    return name or "untitled"


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------
def get_project_root() -> Path:
    return _PROJECT_ROOT


def get_downloader_dir() -> Path:
    return _PROJECT_ROOT / "01_Downloader"


def get_download_dir(platform: str) -> Path:
    """
    Return the download directory for a given platform.
    Uses DOWNLOAD_DIR from .env if set, else defaults to 01_Downloader/downloads/<platform>/.
    """
    base = os.getenv("DOWNLOAD_DIR", "").strip()
    if base:
        path = Path(base) / platform
    else:
        path = get_downloader_dir() / "downloads" / platform
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Links file reader
# ---------------------------------------------------------------------------
def read_links_file(filepath: str | Path) -> list[str]:
    """
    Read a links file, returning a list of non-empty, non-comment lines.
    Supports # comments and blank lines.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        print_warning(f"Links file not found: {filepath}")
        return []

    links = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                links.append(line)

    if not links:
        print_warning(f"Links file is empty: {filepath}")
    else:
        print_info(f"Loaded {len(links)} link(s) from {filepath.name}")

    return links


# ---------------------------------------------------------------------------
# FFmpeg & aria2c checks
# ---------------------------------------------------------------------------
def check_ffmpeg() -> str | None:
    """
    Check if FFmpeg is available. Returns the path to the executable
    or None if not found. Prints a warning but never crashes.
    """
    # Check .env first
    env_path = os.getenv("FFMPEG_PATH", "").strip()
    if env_path and Path(env_path).is_file():
        return env_path

    # Check system PATH
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    return None


def check_aria2c() -> str | None:
    """
    Check if aria2c is available. Returns the path to the executable
    or None if not found.
    """
    env_path = os.getenv("ARIA2C_PATH", "").strip()
    if env_path and Path(env_path).is_file():
        return env_path

    aria2c = shutil.which("aria2c")
    if aria2c:
        return aria2c

    return None


def get_bulk_workers() -> int:
    """Return the number of parallel workers for bulk downloads (default 4, max 8)."""
    try:
        workers = int(os.getenv("BULK_WORKERS", "4"))
        return max(1, min(workers, 8))
    except ValueError:
        return 4


# ---------------------------------------------------------------------------
# Environment helper
# ---------------------------------------------------------------------------
def get_env(key: str, default: str = "") -> str:
    """Get an environment variable, with a default."""
    return os.getenv(key, default).strip()


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------
def show_system_status() -> None:
    """Display a table showing the status of all dependencies and config."""
    table = Table(
        title="System Status",
        border_style="bright_magenta",
        show_lines=True,
    )
    table.add_column("Component", style="bold cyan", min_width=20)
    table.add_column("Status", min_width=15)
    table.add_column("Details", style="dim")

    # FFmpeg
    ffmpeg = check_ffmpeg()
    if ffmpeg:
        table.add_row("FFmpeg", "[green]Available[/green]", ffmpeg)
    else:
        table.add_row("FFmpeg", "[yellow]Not Found[/yellow]", "Video+audio merging disabled")

    # aria2c
    aria2c = check_aria2c()
    if aria2c:
        table.add_row("aria2c", "[green]Available[/green]", aria2c)
    else:
        table.add_row("aria2c", "[yellow]Not Found[/yellow]", "Using built-in downloader")

    # Instagram credentials
    ig_user = get_env("IG_USERNAME")
    if ig_user:
        table.add_row("IG Login", "[green]Configured[/green]", f"User: {ig_user}")
    else:
        table.add_row("IG Login", "[yellow]Not Set[/yellow]", "Stories/private content unavailable")

    # FB cookies
    fb_cookies = get_env("FB_COOKIES_FILE")
    if fb_cookies and Path(fb_cookies).exists():
        table.add_row("FB Cookies", "[green]Available[/green]", fb_cookies)
    elif fb_cookies:
        table.add_row("FB Cookies", "[red]File Missing[/red]", fb_cookies)
    else:
        table.add_row("FB Cookies", "[yellow]Not Set[/yellow]", "Private videos unavailable")

    # Download directory
    dl_dir = get_env("DOWNLOAD_DIR") or str(get_downloader_dir() / "downloads")
    table.add_row("Download Dir", "[green]Set[/green]", dl_dir)

    # Bulk workers
    workers = get_bulk_workers()
    table.add_row("Bulk Workers", "[green]Set[/green]", str(workers))

    console.print()
    console.print(table)
    console.print()
