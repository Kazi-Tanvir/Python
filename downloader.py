"""
Media Downloader v1.0
Centralized entry point for YouTube, Facebook, and Instagram downloaders.
Supports a plugin system for registering custom downloaders.
"""

import os
import sys
import json
import importlib
import importlib.util
from pathlib import Path

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Register 01_Downloader as an importable package.
# Python module names can't start with digits, so we load the package
# manually via importlib and register it under the alias "_01_Downloader".
# This allows all relative imports inside the sub-modules to work.
# ---------------------------------------------------------------------------
_PKG_DIR = PROJECT_ROOT / "01_Downloader"
_PKG_INIT = _PKG_DIR / "__init__.py"
_PKG_ALIAS = "_01_Downloader"

if _PKG_ALIAS not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        _PKG_ALIAS, str(_PKG_INIT),
        submodule_search_locations=[str(_PKG_DIR)],
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[_PKG_ALIAS] = pkg
    spec.loader.exec_module(pkg)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt
from rich.theme import Theme

import _01_Downloader.utils as dl_utils

# Re-use the shared console
console = dl_utils.console

# ---------------------------------------------------------------------------
# Plugin Registry
# ---------------------------------------------------------------------------
PLUGINS_FILE = PROJECT_ROOT / "01_Downloader" / "plugins.json"

# Built-in downloaders (always available)
BUILTIN_DOWNLOADERS = {
    "youtube": {
        "name": "YouTube Downloader",
        "module": "_01_Downloader.yt_downloader",
        "description": "Download videos and playlists from YouTube",
        "builtin": True,
    },
    "facebook": {
        "name": "Facebook Downloader",
        "module": "_01_Downloader.fb_downloader",
        "description": "Download videos from Facebook in HD",
        "builtin": True,
    },
    "instagram": {
        "name": "Instagram Downloader",
        "module": "_01_Downloader.ig_downloader",
        "description": "Download posts, reels, stories, and profiles",
        "builtin": True,
    },
}


def _load_plugins() -> dict:
    """Load custom plugins from plugins.json, merged with builtins."""
    plugins = dict(BUILTIN_DOWNLOADERS)

    if PLUGINS_FILE.exists():
        try:
            with open(PLUGINS_FILE, "r", encoding="utf-8") as f:
                custom = json.load(f)
            for key, entry in custom.items():
                entry["builtin"] = False
                plugins[key] = entry
        except (json.JSONDecodeError, KeyError) as e:
            dl_utils.print_warning(f"Failed to load plugins.json: {e}")

    return plugins


def _save_custom_plugins(plugins: dict) -> None:
    """Save only custom (non-builtin) plugins to plugins.json."""
    custom = {k: v for k, v in plugins.items() if not v.get("builtin", False)}
    with open(PLUGINS_FILE, "w", encoding="utf-8") as f:
        json.dump(custom, f, indent=2)


def _run_downloader(entry: dict) -> None:
    """Dynamically import and run a downloader module."""
    module_path = entry["module"]
    try:
        import importlib
        mod = importlib.import_module(module_path)
        if hasattr(mod, "run"):
            mod.run()
        else:
            dl_utils.print_error(f"Module '{module_path}' has no run() function.")
    except ImportError as e:
        dl_utils.print_error(f"Could not import '{module_path}': {e}")
    except Exception as e:
        dl_utils.print_error(f"Error running '{entry['name']}': {e}")


# ---------------------------------------------------------------------------
# Plugin management UI
# ---------------------------------------------------------------------------
def _add_plugin(plugins: dict) -> None:
    """Interactively add a new custom downloader plugin."""
    console.print()
    dl_utils.print_info("Register a new downloader plugin")
    console.print()
    console.print(
        Panel(
            "To add a custom downloader, you need:\n\n"
            "  1. A short key (e.g. 'twitter', 'tiktok')\n"
            "  2. A display name (e.g. 'Twitter/X Downloader')\n"
            "  3. The Python module path relative to 98_PYTHON/\n"
            "     (e.g. '01_Downloader.x_downloader')\n"
            "  4. Your module must have a run() function as entry point",
            title="[bold]Plugin Requirements[/bold]",
            border_style="dim",
            padding=(1, 3),
        )
    )
    console.print()

    key = Prompt.ask("  Plugin key (short, lowercase)").strip().lower()
    if not key:
        dl_utils.print_error("Key cannot be empty.")
        return
    if key in plugins:
        dl_utils.print_error(f"Key '{key}' already exists.")
        return

    name = Prompt.ask("  Display name").strip()
    if not name:
        dl_utils.print_error("Name cannot be empty.")
        return

    module = Prompt.ask("  Module path (e.g. 01_Downloader.x_downloader)").strip()
    if not module:
        dl_utils.print_error("Module path cannot be empty.")
        return

    # Fix module path: replace folder names that start with digits
    # Python modules can't start with digits, we use _ prefix convention
    module_fixed = module
    parts = module.split(".")
    fixed_parts = []
    for part in parts:
        if part and part[0].isdigit():
            fixed_parts.append(f"_{part}")
        else:
            fixed_parts.append(part)
    module_fixed = ".".join(fixed_parts)

    description = Prompt.ask("  Description (optional)", default="Custom downloader").strip()

    plugins[key] = {
        "name": name,
        "module": module_fixed,
        "description": description,
        "builtin": False,
    }

    _save_custom_plugins(plugins)
    dl_utils.print_success(f"Plugin '{name}' registered with key '{key}'.")
    dl_utils.print_info(f"Module path: {module_fixed}")
    dl_utils.print_info("Make sure the module exists and has a run() function.")


def _remove_plugin(plugins: dict) -> None:
    """Remove a custom plugin."""
    custom = {k: v for k, v in plugins.items() if not v.get("builtin", False)}
    if not custom:
        dl_utils.print_warning("No custom plugins to remove.")
        return

    console.print()
    table = Table(title="Custom Plugins", border_style="bright_cyan")
    table.add_column("Key", style="bold cyan")
    table.add_column("Name")
    table.add_column("Module", style="dim")

    for key, entry in custom.items():
        table.add_row(key, entry["name"], entry["module"])

    console.print(table)
    console.print()

    key = Prompt.ask("  Enter key to remove").strip().lower()
    if key in custom:
        del plugins[key]
        _save_custom_plugins(plugins)
        dl_utils.print_success(f"Removed plugin '{key}'.")
    else:
        dl_utils.print_error(f"Plugin '{key}' not found.")


def _list_plugins(plugins: dict) -> None:
    """Show all registered plugins."""
    console.print()
    table = Table(title="Registered Downloaders", border_style="bright_magenta", show_lines=True)
    table.add_column("Key", style="bold cyan", min_width=12)
    table.add_column("Name", style="bold white")
    table.add_column("Type", justify="center")
    table.add_column("Module", style="dim")
    table.add_column("Description", style="dim")

    for key, entry in plugins.items():
        ptype = "[dim]Built-in[/dim]" if entry.get("builtin") else "[yellow]Custom[/yellow]"
        table.add_row(key, entry["name"], ptype, entry["module"], entry.get("description", ""))

    console.print(table)


# ---------------------------------------------------------------------------
# Settings menu
# ---------------------------------------------------------------------------
def _settings_menu(plugins: dict) -> None:
    """Settings and system status submenu."""
    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  System Status\n"
                "[bold cyan]2[/]  List All Downloaders\n"
                "[bold cyan]3[/]  Add Custom Downloader\n"
                "[bold cyan]4[/]  Remove Custom Downloader\n"
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
            dl_utils.show_system_status()
        elif choice == "2":
            _list_plugins(plugins)
        elif choice == "3":
            _add_plugin(plugins)
        elif choice == "4":
            _remove_plugin(plugins)


# ---------------------------------------------------------------------------
# Bulk download all
# ---------------------------------------------------------------------------
def _run_bulk_all() -> None:
    """Run bulk download for all three built-in downloaders."""
    dl_utils.print_info("Running bulk download for all platforms...")
    console.print()

    for key, entry in BUILTIN_DOWNLOADERS.items():
        console.rule(f"[bold cyan]{entry['name']}[/bold cyan]", style="bright_magenta")
        try:
            import importlib
            mod = importlib.import_module(entry["module"])
            if hasattr(mod, "run_bulk_download"):
                mod.run_bulk_download()
            else:
                dl_utils.print_warning(f"{entry['name']} has no bulk download function.")
        except ImportError as e:
            dl_utils.print_error(f"Could not import {entry['module']}: {e}")
        except Exception as e:
            dl_utils.print_error(f"Error in {entry['name']}: {e}")
        console.print()


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------
def main() -> None:
    """Main interactive menu."""
    plugins = _load_plugins()

    # Banner
    banner_text = Text(justify="center")
    banner_text.append("MEDIA DOWNLOADER", style="bold bright_magenta")
    banner_text.append("\n")
    banner_text.append("v1.0", style="dim")
    console.print(
        Panel(
            banner_text,
            border_style="bright_magenta",
            padding=(1, 4),
        )
    )

    while True:
        console.print()

        # Build menu dynamically from plugins
        menu_lines = []
        menu_keys = []
        idx = 1

        for key, entry in plugins.items():
            menu_lines.append(f"[bold cyan]{idx}[/]  {entry['name']}")
            menu_keys.append((str(idx), key))
            idx += 1

        menu_lines.append(f"[bold cyan]{idx}[/]  Bulk Download (All Platforms)")
        bulk_key = str(idx)
        idx += 1

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
            dl_utils.print_info("Goodbye!")
            break
        elif choice == bulk_key:
            _run_bulk_all()
        elif choice == settings_key:
            _settings_menu(plugins)
            # Reload in case plugins changed
            plugins = _load_plugins()
        else:
            # Find which downloader was selected
            for menu_idx, key in menu_keys:
                if choice == menu_idx:
                    _run_downloader(plugins[key])
                    break


if __name__ == "__main__":
    main()
