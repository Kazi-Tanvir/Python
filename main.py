"""
Python Toolkit v1.0
===================
General-purpose script launcher for the 98_PYTHON project.
Provides a Rich-based interactive menu that can call any script
registered via the built-in registry or the scripts.json plugin file.

Similar architecture to downloader.py, but generalised to launch
any Python script that exposes a run() function.
"""

import os
import sys
import json
import importlib
import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Register digit-prefixed directories as importable Python packages.
# Python module names can't start with digits, so we load each package
# manually via importlib and register it under an "_" prefixed alias.
#
# Currently handles:
#   01_Downloader  → _01_Downloader
#   99_MISCElLLANEOUS → _99_MISCElLLANEOUS
# ---------------------------------------------------------------------------
_DIGIT_DIRS = [
    ("01_Downloader", "_01_Downloader"),
    ("03_Converter", "_03_Converter"),
    ("99_MISCElLLANEOUS", "_99_MISCElLLANEOUS"),
]

for folder_name, alias in _DIGIT_DIRS:
    pkg_dir = PROJECT_ROOT / folder_name
    pkg_init = pkg_dir / "__init__.py"
    if alias not in sys.modules and pkg_init.exists():
        spec = importlib.util.spec_from_file_location(
            alias,
            str(pkg_init),
            submodule_search_locations=[str(pkg_dir)],
        )
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[alias] = pkg
        spec.loader.exec_module(pkg)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Rich Theme & Console  (consistent with project style)
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
def _print_success(msg: str) -> None:
    console.print(f"  [success][+][/success] {msg}")


def _print_error(msg: str) -> None:
    console.print(f"  [error][!][/error] {msg}")


def _print_warning(msg: str) -> None:
    console.print(f"  [warning][*][/warning] {msg}")


def _print_info(msg: str) -> None:
    console.print(f"  [info][>][/info] {msg}")


# ---------------------------------------------------------------------------
# Script Registry
# ---------------------------------------------------------------------------
SCRIPTS_FILE = PROJECT_ROOT / "scripts.json"

# Built-in scripts (always available)
# Each entry must have:
#   - name:        Human-readable name shown in the menu
#   - module:      Importable Python module path (use _XX prefix for digit dirs)
#   - description: Short description shown in settings
#   - entry:       Entry-point function name (default: "run")
#   - builtin:     True for built-in, False for user-added
BUILTIN_SCRIPTS = {
    "downloader": {
        "name": "Media Downloader",
        "module": "downloader",
        "description": "Download videos from YouTube, Facebook & Instagram",
        "entry": "main",
        "builtin": True,
    },
    "book_to_readme": {
        "name": "Book to README",
        "module": "book_to_readme",
        "description": "Convert PDF book chapters to structured Markdown",
        "entry": "main",
        "builtin": True,
    },
    "fb_scraper": {
        "name": "Facebook Tuition Scraper",
        "module": "_99_MISCElLLANEOUS.facebook_web_scraper",
        "description": "Scrape & filter tutoring jobs from Facebook pages",
        "entry": "run",
        "builtin": True,
    },
    "cbz_to_pdf": {
        "name": "CBZ -> PDF Converter",
        "module": "_03_Converter.cbz_to_pdf",
        "description": "Convert comic book archives (.cbz) to PDF",
        "entry": "run",
        "builtin": True,
    },
    "img_to_pdf": {
        "name": "Image -> PDF Converter",
        "module": "_03_Converter.img_to_pdf",
        "description": "Convert a directory of images (PNG, JPG, etc.) into a single PDF",
        "entry": "run",
        "builtin": True,
    },
}


def _load_scripts() -> dict:
    """Load custom scripts from scripts.json, merged with builtins."""
    scripts = dict(BUILTIN_SCRIPTS)

    if SCRIPTS_FILE.exists():
        try:
            with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
                custom = json.load(f)
            for key, entry in custom.items():
                entry["builtin"] = False
                scripts[key] = entry
        except (json.JSONDecodeError, KeyError) as e:
            _print_warning(f"Failed to load scripts.json: {e}")

    return scripts


def _save_custom_scripts(scripts: dict) -> None:
    """Save only custom (non-builtin) scripts to scripts.json."""
    custom = {k: v for k, v in scripts.items() if not v.get("builtin", False)}
    with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(custom, f, indent=2)


def _run_script(entry: dict) -> None:
    """
    Dynamically import and run a registered script.

    Each script must expose a callable entry-point function (default: "run").
    The function name is configurable via the "entry" key in the registry.
    """
    module_path = entry["module"]
    func_name = entry.get("entry", "run")

    try:
        mod = importlib.import_module(module_path)
        # Reload to pick up changes during development
        importlib.reload(mod)

        if hasattr(mod, func_name):
            getattr(mod, func_name)()
        else:
            _print_error(
                f"Module '{module_path}' has no {func_name}() function.\n"
                f"  Expected entry point: {module_path}.{func_name}()"
            )
    except ImportError as e:
        _print_error(f"Could not import '{module_path}': {e}")
    except KeyboardInterrupt:
        console.print()
        _print_warning("Script interrupted by user.")
    except Exception as e:
        _print_error(f"Error running '{entry['name']}': {e}")


# ---------------------------------------------------------------------------
# Plugin management UI
# ---------------------------------------------------------------------------
def _add_script(scripts: dict) -> None:
    """Interactively register a new script."""
    console.print()
    _print_info("Register a new script")
    console.print()
    console.print(
        Panel(
            "To add a custom script, you need:\n\n"
            "  1. A short key (e.g. 'web_scraper', 'data_cleaner')\n"
            "  2. A display name (e.g. 'Web Scraper Tool')\n"
            "  3. The Python module path relative to 98_PYTHON/\n"
            "     (e.g. '99_MISCElLLANEOUS.my_script')\n"
            "     Note: digit-prefixed folders use _ prefix → _99_MISCElLLANEOUS\n"
            "  4. The entry-point function name (default: 'run')\n"
            "  5. Your module must have the entry function as its main logic",
            title="[bold]Script Requirements[/bold]",
            border_style="dim",
            padding=(1, 3),
        )
    )
    console.print()

    key = Prompt.ask("  Script key (short, lowercase)").strip().lower()
    if not key:
        _print_error("Key cannot be empty.")
        return
    if key in scripts:
        _print_error(f"Key '{key}' already exists.")
        return

    name = Prompt.ask("  Display name").strip()
    if not name:
        _print_error("Name cannot be empty.")
        return

    module = Prompt.ask("  Module path (e.g. _99_MISCElLLANEOUS.my_script)").strip()
    if not module:
        _print_error("Module path cannot be empty.")
        return

    # Auto-fix: replace digit-prefixed segments with _ prefix
    parts = module.split(".")
    fixed_parts = []
    for part in parts:
        if part and part[0].isdigit():
            fixed_parts.append(f"_{part}")
        else:
            fixed_parts.append(part)
    module_fixed = ".".join(fixed_parts)

    func_name = Prompt.ask("  Entry function name", default="run").strip()
    description = Prompt.ask("  Description (optional)", default="Custom script").strip()

    scripts[key] = {
        "name": name,
        "module": module_fixed,
        "description": description,
        "entry": func_name,
        "builtin": False,
    }

    _save_custom_scripts(scripts)
    _print_success(f"Script '{name}' registered with key '{key}'.")
    _print_info(f"Module path: {module_fixed}  →  {func_name}()")
    _print_info("Make sure the module exists and has the entry function.")


def _remove_script(scripts: dict) -> None:
    """Remove a custom script registration."""
    custom = {k: v for k, v in scripts.items() if not v.get("builtin", False)}
    if not custom:
        _print_warning("No custom scripts to remove.")
        return

    console.print()
    table = Table(title="Custom Scripts", border_style="bright_cyan")
    table.add_column("Key", style="bold cyan")
    table.add_column("Name")
    table.add_column("Module", style="dim")

    for key, entry in custom.items():
        table.add_row(key, entry["name"], entry["module"])

    console.print(table)
    console.print()

    key = Prompt.ask("  Enter key to remove").strip().lower()
    if key in custom:
        del scripts[key]
        _save_custom_scripts(scripts)
        _print_success(f"Removed script '{key}'.")
    else:
        _print_error(f"Script '{key}' not found.")


def _list_scripts(scripts: dict) -> None:
    """Show all registered scripts."""
    console.print()
    table = Table(
        title="Registered Scripts",
        border_style="bright_magenta",
        show_lines=True,
    )
    table.add_column("Key", style="bold cyan", min_width=15)
    table.add_column("Name", style="bold white")
    table.add_column("Type", justify="center")
    table.add_column("Module", style="dim")
    table.add_column("Entry", style="dim")
    table.add_column("Description", style="dim")

    for key, entry in scripts.items():
        stype = "[dim]Built-in[/dim]" if entry.get("builtin") else "[yellow]Custom[/yellow]"
        table.add_row(
            key,
            entry["name"],
            stype,
            entry["module"],
            entry.get("entry", "run"),
            entry.get("description", ""),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# System status
# ---------------------------------------------------------------------------
def _show_system_status() -> None:
    """Display project-wide system status."""
    table = Table(
        title="System Status",
        border_style="bright_magenta",
        show_lines=True,
    )
    table.add_column("Component", style="bold cyan", min_width=20)
    table.add_column("Status", min_width=15)
    table.add_column("Details", style="dim")

    # Python version
    table.add_row(
        "Python",
        "[green]Available[/green]",
        f"{sys.version.split()[0]}",
    )

    # Project root
    table.add_row("Project Root", "[green]Set[/green]", str(PROJECT_ROOT))

    # .env file
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        table.add_row(".env File", "[green]Found[/green]", str(env_file))
    else:
        table.add_row(".env File", "[yellow]Not Found[/yellow]", "Copy .env.example → .env")

    # Check key packages
    for pkg_name, display_name in [
        ("rich", "Rich (TUI)"),
        ("yt_dlp", "yt-dlp"),
        ("playwright", "Playwright"),
        ("apify_client", "Apify Client"),
        ("instaloader", "Instaloader"),
        ("pymupdf", "PyMuPDF"),
    ]:
        try:
            importlib.import_module(pkg_name)
            table.add_row(display_name, "[green]Installed[/green]", "")
        except ImportError:
            table.add_row(display_name, "[yellow]Not Installed[/yellow]", f"pip install {pkg_name}")

    # scripts.json
    if SCRIPTS_FILE.exists():
        try:
            with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
                custom = json.load(f)
            table.add_row("scripts.json", "[green]Found[/green]", f"{len(custom)} custom script(s)")
        except Exception:
            table.add_row("scripts.json", "[yellow]Invalid[/yellow]", "JSON parse error")
    else:
        table.add_row("scripts.json", "[dim]Not Created[/dim]", "Created when you add custom scripts")

    console.print()
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Settings menu
# ---------------------------------------------------------------------------
def _settings_menu(scripts: dict) -> None:
    """Settings and system status submenu."""
    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  System Status\n"
                "[bold cyan]2[/]  List All Scripts\n"
                "[bold cyan]3[/]  Add Custom Script\n"
                "[bold cyan]4[/]  Remove Custom Script\n"
                "[bold cyan]0[/]  Back to Main Menu",
                title="[bold]Settings[/bold]",
                border_style="bright_magenta",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask("  Choice", choices=["0", "1", "2", "3", "4"], default="1")

        if choice == "0":
            break
        elif choice == "1":
            _show_system_status()
        elif choice == "2":
            _list_scripts(scripts)
        elif choice == "3":
            _add_script(scripts)
        elif choice == "4":
            _remove_script(scripts)


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------
def main() -> None:
    """Main interactive menu — the project's central entry point."""
    scripts = _load_scripts()

    # Banner
    banner_text = Text(justify="center")
    banner_text.append("PYTHON TOOLKIT", style="bold bright_magenta")
    banner_text.append("\n")
    banner_text.append("v1.0  •  General Script Launcher", style="dim")
    console.print(
        Panel(
            banner_text,
            border_style="bright_magenta",
            padding=(1, 4),
        )
    )

    while True:
        console.print()

        # Build menu dynamically from registered scripts
        menu_lines = []
        menu_keys = []     # (menu_number_str, script_key)
        idx = 1

        for key, entry in scripts.items():
            label = entry["name"]
            desc = entry.get("description", "")
            tag = ""
            if not entry.get("builtin", False):
                tag = " [yellow](custom)[/yellow]"

            if desc:
                menu_lines.append(f"[bold cyan]{idx}[/]  {label}{tag}  [dim]— {desc}[/dim]")
            else:
                menu_lines.append(f"[bold cyan]{idx}[/]  {label}{tag}")

            menu_keys.append((str(idx), key))
            idx += 1

        # Settings option
        menu_lines.append(f"[bold cyan]{idx}[/]  Settings / Status")
        settings_key = str(idx)

        menu_lines.append("[bold cyan]0[/]  Exit")

        console.print(
            Panel(
                "\n".join(menu_lines),
                title="[bold]Main Menu[/bold]",
                border_style="bright_magenta",
                padding=(1, 3),
            )
        )

        valid_choices = [str(i) for i in range(idx + 1)]
        choice = Prompt.ask("  Choice", choices=valid_choices, default="1")

        if choice == "0":
            console.print()
            _print_info("Goodbye!")
            break
        elif choice == settings_key:
            _settings_menu(scripts)
            # Reload in case scripts changed
            scripts = _load_scripts()
        else:
            # Find which script was selected
            for menu_idx, key in menu_keys:
                if choice == menu_idx:
                    console.print()
                    console.rule(
                        f"[bold cyan]{scripts[key]['name']}[/bold cyan]",
                        style="bright_magenta",
                    )
                    _run_script(scripts[key])
                    break


if __name__ == "__main__":
    main()
