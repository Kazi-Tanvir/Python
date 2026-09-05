"""
Shared Rich console, theme, and styled output helpers.
Single source of truth for the project's terminal UI.
"""

import sys

# Ensure UTF-8 output on Windows consoles to prevent cp1252 charmap encode errors
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Rich Theme (single definition — used project-wide)
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
    "best": "bold green",
    "good": "bold yellow",
    "low": "dim white",
})

console = Console(theme=CUSTOM_THEME)


# ---------------------------------------------------------------------------
# Styled output helpers
# ---------------------------------------------------------------------------
def print_success(msg: str) -> None:
    console.print(f"  [success][+][/success] {msg}")


def print_error(msg: str) -> None:
    console.print(f"  [error][!][/error] {msg}")


def print_warning(msg: str) -> None:
    console.print(f"  [warning][*][/warning] {msg}")


def print_info(msg: str) -> None:
    console.print(f"  [info][>][/info] {msg}")


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
