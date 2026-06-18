"""
Instagram Downloader Module
Downloads posts, reels, stories, and full profiles using instaloader.
Supports single URLs, usernames, and bulk downloads from ig_links.txt.
"""

import os
import re
import time
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import instaloader


class ThreadSafeInstaloader(instaloader.Instaloader):
    def __init__(self, *args, **kwargs):
        self._thread_local = threading.local()
        self._shared_dirname_pattern = kwargs.get("dirname_pattern", "")
        self._thread_local.dirname_pattern = self._shared_dirname_pattern
        super().__init__(*args, **kwargs)

    @property
    def dirname_pattern(self) -> str:
        if not hasattr(self._thread_local, "dirname_pattern"):
            return self._shared_dirname_pattern
        return self._thread_local.dirname_pattern

    @dirname_pattern.setter
    def dirname_pattern(self, value: str):
        self._thread_local.dirname_pattern = value
        self._shared_dirname_pattern = value


from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt

from .utils import (
    console,
    print_banner,
    print_success,
    print_error,
    print_warning,
    print_info,
    get_download_dir,
    get_downloader_dir,
    read_links_file,
    get_env,
    get_bulk_workers,
)


# ---------------------------------------------------------------------------
# URL parsing helpers
# ---------------------------------------------------------------------------
_POST_PATTERN = re.compile(
    r"instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)"
)
_STORY_PATTERN = re.compile(
    r"instagram\.com/stories/([^/]+)"
)
_PROFILE_PATTERN = re.compile(
    r"instagram\.com/([A-Za-z0-9_.]+)/?$"
)


def _parse_input(text: str) -> tuple[str, str]:
    """
    Parse user input and return (type, identifier).
    type: 'post', 'reel', 'story', 'profile', 'username'
    """
    text = text.strip().rstrip("/")

    # Direct post/reel link
    match = _POST_PATTERN.search(text)
    if match:
        return ("post", match.group(1))

    # Story link
    match = _STORY_PATTERN.search(text)
    if match:
        return ("story", match.group(1))

    # Profile link
    match = _PROFILE_PATTERN.search(text)
    if match:
        return ("profile", match.group(1))

    # Bare username (with or without @)
    if text.startswith("@"):
        text = text[1:]
    if re.match(r"^[A-Za-z0-9_.]+$", text):
        return ("username", text)

    return ("unknown", text)


# ---------------------------------------------------------------------------
# Instaloader instance management
# ---------------------------------------------------------------------------
_loader_instance = None


def _get_loader(download_dir: Path) -> instaloader.Instaloader:
    """Get or create a configured Instaloader instance."""
    global _loader_instance

    if _loader_instance is not None:
        _loader_instance.dirname_pattern = str(download_dir / "{target}")
        return _loader_instance

    L = ThreadSafeInstaloader(
        dirname_pattern=str(download_dir / "{target}"),
        filename_pattern="{date_utc}__{shortcode}",
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
    )

    # Try to login
    username = get_env("IG_USERNAME")
    password = get_env("IG_PASSWORD")

    if username and password:
        session_file = get_downloader_dir() / f".{username}_session"
        try:
            # Try loading saved session first
            if session_file.exists():
                L.load_session_from_file(username, str(session_file))
                print_success(f"Loaded saved session for @{username}")
            else:
                L.login(username, password)
                L.save_session_to_file(str(session_file))
                print_success(f"Logged in as @{username}")
        except instaloader.exceptions.ConnectionException as e:
            print_warning(f"Login failed: {e}")
            print_info("Continuing without login (limited access).")
        except Exception as e:
            print_warning(f"Session error: {e}")
            print_info("Continuing without login.")
    else:
        print_info("No IG credentials in .env - stories and private content unavailable.")

    _loader_instance = L
    return L


# ---------------------------------------------------------------------------
# Download functions
# ---------------------------------------------------------------------------
def _download_post(shortcode: str, download_dir: Path) -> bool:
    """Download a single post or reel by shortcode."""
    L = _get_loader(download_dir)
    L.dirname_pattern = str(download_dir)

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        print_info(f"Post by @{post.owner_username} ({post.date_utc.strftime('%Y-%m-%d')})")

        with console.status("[cyan]Downloading post...[/cyan]"):
            L.download_post(post, target=post.owner_username)

        print_success(f"Downloaded post {shortcode}")
        return True
    except instaloader.exceptions.QueryReturnedNotFoundException:
        print_error(f"Post not found: {shortcode}")
        return False
    except instaloader.exceptions.LoginRequiredException:
        print_error("Login required. Set IG_USERNAME and IG_PASSWORD in .env")
        return False
    except instaloader.exceptions.ConnectionException as e:
        if "429" in str(e):
            print_warning("Rate limited by Instagram. Waiting 60 seconds...")
            time.sleep(60)
            return _download_post(shortcode, download_dir)  # Retry once
        print_error(f"Connection error: {e}")
        return False
    except Exception as e:
        print_error(f"Failed to download post: {e}")
        return False


def _download_stories(username: str, download_dir: Path) -> bool:
    """Download all current stories for a user."""
    L = _get_loader(download_dir)
    L.dirname_pattern = str(download_dir)

    ig_user = get_env("IG_USERNAME")
    if not ig_user:
        print_error("Login required for stories. Set IG_USERNAME and IG_PASSWORD in .env")
        return False

    try:
        profile = instaloader.Profile.from_username(L.context, username)
        print_info(f"Fetching stories for @{username}...")

        with console.status(f"[cyan]Downloading stories for @{username}...[/cyan]"):
            L.download_stories(userids=[profile.userid])

        print_success(f"Downloaded stories for @{username}")
        return True
    except instaloader.exceptions.QueryReturnedNotFoundException:
        print_error(f"User not found: @{username}")
        return False
    except instaloader.exceptions.LoginRequiredException:
        print_error("Login required for stories. Set IG_USERNAME and IG_PASSWORD in .env")
        return False
    except instaloader.exceptions.ConnectionException as e:
        if "429" in str(e):
            print_warning("Rate limited by Instagram. Waiting 60 seconds...")
            time.sleep(60)
            return _download_stories(username, download_dir)
        print_error(f"Connection error: {e}")
        return False
    except Exception as e:
        print_error(f"Failed to download stories: {e}")
        return False


def _download_profile(username: str, download_dir: Path) -> bool:
    """Download all content from a profile (posts, reels, tagged)."""
    L = _get_loader(download_dir)
    L.dirname_pattern = str(download_dir / "{target}")

    try:
        profile = instaloader.Profile.from_username(L.context, username)
        print_info(f"Profile: @{username}")
        print_info(f"Posts: {profile.mediacount} | Followers: {profile.followers}")

        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  All posts\n"
                "[bold cyan]2[/]  All posts + stories\n"
                "[bold cyan]3[/]  All posts + stories + tagged\n"
                "[bold cyan]4[/]  Stories only\n"
                "[bold cyan]0[/]  Cancel",
                title=f"[bold]Download Options for @{username}[/bold]",
                border_style="cyan",
                padding=(1, 3),
            )
        )
        choice = Prompt.ask("  Choice", choices=["0", "1", "2", "3", "4"], default="1")

        if choice == "0":
            return False

        with console.status(f"[cyan]Downloading @{username}...[/cyan]"):
            if choice in ("1", "2", "3"):
                # Download posts
                posts = profile.get_posts()
                for post in posts:
                    try:
                        L.download_post(post, target=username)
                    except Exception as e:
                        print_warning(f"Skipped post: {e}")

            if choice in ("2", "3"):
                # Download stories
                try:
                    L.download_stories(userids=[profile.userid], filename_target=username)
                except Exception as e:
                    print_warning(f"Stories failed: {e}")

            if choice == "3":
                # Download tagged posts
                try:
                    tagged = profile.get_tagged_posts()
                    for post in tagged:
                        try:
                            L.download_post(post, target=f"{username}_tagged")
                        except Exception as e:
                            print_warning(f"Skipped tagged post: {e}")
                except Exception as e:
                    print_warning(f"Tagged posts failed: {e}")

            if choice == "4":
                try:
                    L.download_stories(userids=[profile.userid], filename_target=username)
                except Exception as e:
                    print_error(f"Stories failed: {e}")
                    return False

        print_success(f"Download complete for @{username}")
        return True

    except instaloader.exceptions.QueryReturnedNotFoundException:
        print_error(f"User not found: @{username}")
        return False
    except instaloader.exceptions.ConnectionException as e:
        if "429" in str(e):
            print_warning("Rate limited by Instagram. Waiting 60 seconds...")
            time.sleep(60)
            return _download_profile(username, download_dir)
        print_error(f"Connection error: {e}")
        return False
    except Exception as e:
        print_error(f"Failed: {e}")
        return False


def _handle_input(text: str, download_dir: Path) -> bool:
    """Route user input to the appropriate download function."""
    input_type, identifier = _parse_input(text)

    if input_type == "post":
        return _download_post(identifier, download_dir)
    elif input_type == "story":
        return _download_stories(identifier, download_dir)
    elif input_type == "profile":
        # Profile link - ask what to do
        return _download_profile(identifier, download_dir)
    elif input_type == "username":
        # Bare username - ask what to do
        return _download_profile(identifier, download_dir)
    else:
        print_error(f"Could not parse input: {text}")
        print_info("Provide an Instagram URL or @username")
        return False


# ---------------------------------------------------------------------------
# Interactive modes
# ---------------------------------------------------------------------------
def run_single_download() -> None:
    """Interactive: download a single post/reel/story/profile."""
    console.print()
    console.print(
        Panel(
            "Enter an Instagram URL or @username.\n\n"
            "Supported inputs:\n"
            "  - Post URL:    instagram.com/p/ABC123\n"
            "  - Reel URL:    instagram.com/reel/ABC123\n"
            "  - Story URL:   instagram.com/stories/username\n"
            "  - Profile URL: instagram.com/username\n"
            "  - Username:    @username",
            title="[bold]Input Guide[/bold]",
            border_style="dim",
            padding=(1, 3),
        )
    )
    console.print()

    text = Prompt.ask("  Enter URL or @username")
    if not text.strip():
        print_error("No input provided.")
        return

    download_dir = get_download_dir("instagram")
    print_info(f"Saving to: {download_dir}")
    console.print()

    _handle_input(text, download_dir)


def run_bulk_download() -> None:
    """Bulk download from ig_links.txt with parallel workers."""
    links_file = get_downloader_dir() / "ig_links.txt"
    links = read_links_file(links_file)
    if not links:
        print_error(f"No links found. Add Instagram URLs or @usernames to: {links_file}")
        return

    download_dir = get_download_dir("instagram")
    workers = get_bulk_workers()
    print_info(f"Processing {len(links)} item(s) with {workers} parallel worker(s)")
    print_info(f"Saving to: {download_dir}")
    console.print()

    success_count = 0
    fail_count = 0

    # Instagram is sensitive to parallel requests, so we use fewer workers
    # and add delays between downloads
    effective_workers = min(workers, 3)  # Cap at 3 for IG to avoid rate limits
    if effective_workers < workers:
        print_warning(
            f"Using {effective_workers} workers for Instagram (rate limit protection)"
        )

    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = {}
        for i, item in enumerate(links, 1):
            future = executor.submit(_handle_input, item, download_dir)
            futures[future] = (i, item)

        for future in as_completed(futures):
            idx, item = futures[future]
            try:
                if future.result():
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                print_error(f"[{idx}] Unexpected error for '{item}': {e}")
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
    """Instagram Downloader interactive menu."""
    print_banner("INSTAGRAM DOWNLOADER", "Download posts, reels, stories, and profiles")

    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  Download by URL or @username\n"
                "[bold cyan]2[/]  Bulk Download (ig_links.txt)\n"
                "[bold cyan]0[/]  Back to Main Menu",
                title="[bold]Instagram Options[/bold]",
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
