"""
OSINT Phone Lookup — Interactive Menu
=======================================
Rich-based submenu for the OSINT module.
Provides phone lookup, past report viewing, and settings.
"""

import json
from pathlib import Path
from datetime import datetime

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt

from shared.console import (
    console,
    print_banner,
    print_success,
    print_error,
    print_warning,
    print_info,
)
from shared.config import PROJECT_ROOT

from osint.phone_lookup import run_interactive
from osint.report import OUTPUT_DIR


def _view_past_reports() -> None:
    """List and optionally view saved JSON reports."""
    json_files = sorted(OUTPUT_DIR.glob("*.json"), reverse=True)

    if not json_files:
        print_warning("No saved reports found.")
        print_info(f"Reports are saved to: {OUTPUT_DIR}")
        return

    console.print()
    table = Table(
        title="Saved OSINT Reports",
        border_style="bright_cyan",
        show_lines=True,
    )
    table.add_column("#", style="bold cyan", justify="center", min_width=4)
    table.add_column("Phone Number", style="bold white", min_width=18)
    table.add_column("Date", style="dim", min_width=20)
    table.add_column("File", style="dim")

    for i, f in enumerate(json_files[:20], 1):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            phone = data.get("phone_e164", data.get("phone_number", "Unknown"))
            ts = data.get("timestamp", "Unknown")
            # Format timestamp
            try:
                dt = datetime.fromisoformat(ts)
                ts_display = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                ts_display = ts
        except Exception:
            phone = "Error reading"
            ts_display = "—"

        table.add_row(str(i), phone, ts_display, f.name)

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "  Enter report # to view (or 0 to go back)",
        default="0",
    )

    if choice == "0":
        return

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(json_files):
            filepath = json_files[idx]
            with open(filepath, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            # Re-render the report
            from osint.report import OsintReport, ModuleResult, render_terminal

            report = OsintReport(
                phone_number=data.get("phone_number", ""),
                phone_e164=data.get("phone_e164", ""),
                country=data.get("country", ""),
                timestamp=data.get("timestamp", ""),
            )

            for mod_name, mod_data in data.get("modules", {}).items():
                result = ModuleResult(
                    module_name=mod_name,
                    success=mod_data.get("success", False),
                    data=mod_data.get("data", {}),
                    errors=mod_data.get("errors", []),
                    urls=mod_data.get("urls", []),
                )
                report.add_module_result(result)

            render_terminal(report)
        else:
            print_error("Invalid report number.")
    except (ValueError, IndexError):
        print_error("Invalid input.")


def _show_settings() -> None:
    """Show OSINT module settings and API key status."""
    from shared.config import get_env

    console.print()
    table = Table(
        title="OSINT Configuration",
        border_style="bright_magenta",
        show_lines=True,
    )
    table.add_column("Setting", style="bold cyan", min_width=25)
    table.add_column("Status", min_width=15)
    table.add_column("Details", style="dim")

    # API Keys
    api_keys = [
        ("NUMVERIFY_API_KEY", "NumVerify", "Phone validation (100/mo free)"),
        ("ABSTRACT_API_KEY", "AbstractAPI", "Phone validation (100/mo free)"),
        ("IPQUALITYSCORE_API_KEY", "IPQualityScore", "Fraud scoring (200/mo free)"),
        ("GOOGLE_API_KEY", "Google CSE", "Custom Search (100/day free)"),
        ("GOOGLE_CSE_ID", "Google CSE ID", "Custom Search Engine ID"),
    ]

    for key, name, desc in api_keys:
        value = get_env(key)
        if value:
            masked = value[:4] + "•" * (len(value) - 8) + value[-4:] if len(value) > 8 else "•" * len(value)
            table.add_row(name, "[green]Configured[/green]", f"{desc} ({masked})")
        else:
            table.add_row(name, "[yellow]Not Set[/yellow]", f"{desc} — add {key} to .env")

    # Output directory
    report_count = len(list(OUTPUT_DIR.glob("*.json")))
    table.add_row("Output Directory", "[green]Ready[/green]", f"{OUTPUT_DIR} ({report_count} reports)")

    console.print(table)

    console.print()
    console.print(
        Panel(
            "[bold]To add API keys:[/bold]\n\n"
            "  1. Open your [cyan].env[/cyan] file in the project root\n"
            "  2. Add the key in format: [cyan]KEY_NAME=your_api_key[/cyan]\n"
            "  3. Restart the tool\n\n"
            "[dim]All API keys are optional — the tool works without them\n"
            "but provides enhanced results when keys are available.[/dim]",
            title="[bold]API Key Setup[/bold]",
            border_style="dim cyan",
            padding=(1, 3),
        )
    )


def run() -> None:
    """
    Main entry point for the OSINT module.
    Called by the toolkit's script launcher.
    """
    # Banner
    banner = Text(justify="center")
    banner.append("☎  OSINT PHONE LOOKUP", style="bold bright_magenta")
    banner.append("\n", style="dim")
    banner.append("Deep Reverse Phone Number Intelligence", style="dim white")

    console.print(
        Panel(
            banner,
            border_style="bright_magenta",
            padding=(1, 4),
        )
    )

    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  🔍 Phone Number Lookup\n"
                "[bold cyan]2[/]  📂 View Past Reports\n"
                "[bold cyan]3[/]  ⚙️  Settings / API Keys\n"
                "[bold cyan]0[/]  ← Back to Main Menu",
                title="[bold]OSINT Menu[/bold]",
                border_style="bright_magenta",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask("  Choice", choices=["0", "1", "2", "3"], default="1")

        if choice == "0":
            break
        elif choice == "1":
            run_interactive()
        elif choice == "2":
            _view_past_reports()
        elif choice == "3":
            _show_settings()
