"""
OSINT Report — Data classes and rendering.
==========================================
Holds gathered intelligence in a structured format.
Renders Rich terminal reports and exports to JSON/HTML.
"""

import json
from datetime import datetime
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.tree import Tree
from rich import box

from shared.console import console
from shared.config import PROJECT_ROOT

OUTPUT_DIR = PROJECT_ROOT / "output" / "osint"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class ModuleResult:
    """Result from a single lookup module."""
    module_name: str
    success: bool = False
    data: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    urls: list = field(default_factory=list)  # Actionable URLs for manual checks


@dataclass
class OsintReport:
    """Aggregated OSINT report for a phone number."""
    phone_number: str
    phone_e164: str = ""
    country: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    modules: dict[str, ModuleResult] = field(default_factory=dict)

    def add_module_result(self, result: ModuleResult) -> None:
        self.modules[result.module_name] = result

    def to_dict(self) -> dict:
        """Convert to serializable dictionary."""
        d = {
            "phone_number": self.phone_number,
            "phone_e164": self.phone_e164,
            "country": self.country,
            "timestamp": self.timestamp,
            "modules": {},
        }
        for name, mod in self.modules.items():
            d["modules"][name] = {
                "success": mod.success,
                "data": mod.data,
                "errors": mod.errors,
                "urls": mod.urls,
            }
        return d


# ---------------------------------------------------------------------------
# JSON Export
# ---------------------------------------------------------------------------
def save_json(report: OsintReport) -> Path:
    """Save report as JSON. Returns the file path."""
    safe_number = report.phone_e164.replace("+", "").replace(" ", "_") or "unknown"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_number}_{ts}.json"
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, ensure_ascii=False, default=str)

    return filepath


# ---------------------------------------------------------------------------
# Terminal Report Rendering
# ---------------------------------------------------------------------------
_SECTION_STYLE = "bright_cyan"
_HEADER_STYLE = "bold bright_magenta"
_KEY_STYLE = "bold cyan"
_VAL_STYLE = "white"
_DIM_STYLE = "dim"
_GOOD_STYLE = "bold green"
_WARN_STYLE = "bold yellow"
_BAD_STYLE = "bold red"


def _render_kv_table(data: dict, title: str = "") -> Table:
    """Render a key-value dict as a Rich table."""
    table = Table(
        show_header=False,
        box=box.SIMPLE_HEAVY,
        border_style=_SECTION_STYLE,
        title=title if title else None,
        title_style=_HEADER_STYLE,
        padding=(0, 2),
        expand=True,
    )
    table.add_column("Key", style=_KEY_STYLE, min_width=22, no_wrap=True)
    table.add_column("Value", style=_VAL_STYLE)

    for key, value in data.items():
        if isinstance(value, (list, dict)):
            value = json.dumps(value, indent=2, default=str)
        table.add_row(str(key), str(value) if value else "[dim]—[/dim]")

    return table


def _render_url_list(urls: list[str], title: str) -> Panel:
    """Render a list of URLs as a panel."""
    if not urls:
        return None

    lines = []
    for url in urls:
        lines.append(f"  [link={url}]{url}[/link]")

    return Panel(
        "\n".join(lines),
        title=f"[bold]{title}[/bold]",
        border_style="dim cyan",
        padding=(0, 1),
    )


def render_terminal(report: OsintReport) -> None:
    """Render the full OSINT report to the terminal."""
    console.print()

    # ── Banner ──
    banner = Text(justify="center")
    banner.append("☎  OSINT PHONE INTELLIGENCE REPORT", style="bold bright_magenta")
    banner.append(f"\n\nTarget: ", style="dim")
    banner.append(report.phone_e164 or report.phone_number, style="bold white")
    if report.country:
        banner.append(f"  ({report.country})", style="dim cyan")
    banner.append(f"\n\nGenerated: {report.timestamp}", style="dim")

    console.print(Panel(
        banner,
        border_style="bright_magenta",
        padding=(1, 4),
    ))

    # ── Module Results ──
    module_order = [
        ("basic_info", "📱 Basic Phone Information"),
        ("numverify", "🌐 API Validation & Carrier Data"),
        ("social_media", "📘 Social Media Profiles"),
        ("messaging_apps", "💬 Messaging Applications"),
        ("search_engines", "🔍 Search Engine Intelligence"),
        ("data_breaches", "💀 Data Breach Exposure"),
        ("caller_id", "☎️  Caller ID & Directories"),
        ("reputation", "⚠️  Reputation & Risk Score"),
    ]

    for module_key, module_title in module_order:
        result = report.modules.get(module_key)
        if not result:
            continue

        console.print()
        console.rule(f"[bold]{module_title}[/bold]", style=_SECTION_STYLE)
        console.print()

        if not result.success:
            for err in result.errors:
                console.print(f"  [red][!][/red] {err}")
            continue

        # Render the data as a key-value table
        if result.data:
            # Separate nested dicts from flat values
            flat_data = {}
            nested_data = {}
            for k, v in result.data.items():
                if isinstance(v, dict) and v:
                    nested_data[k] = v
                elif isinstance(v, list) and v and isinstance(v[0], dict):
                    nested_data[k] = v
                else:
                    flat_data[k] = v

            if flat_data:
                console.print(_render_kv_table(flat_data))

            for section_name, section_data in nested_data.items():
                console.print()
                if isinstance(section_data, dict):
                    console.print(_render_kv_table(
                        section_data,
                        title=section_name.replace("_", " ").title(),
                    ))
                elif isinstance(section_data, list):
                    for i, item in enumerate(section_data):
                        if isinstance(item, dict):
                            console.print(_render_kv_table(
                                item,
                                title=f"{section_name.replace('_', ' ').title()} #{i + 1}",
                            ))

        # Render actionable URLs
        if result.urls:
            console.print()
            url_panel = _render_url_list(result.urls, "🔗 Verification Links")
            if url_panel:
                console.print(url_panel)

    # ── Summary Footer ──
    console.print()
    total_modules = len(report.modules)
    successful = sum(1 for m in report.modules.values() if m.success)
    total_urls = sum(len(m.urls) for m in report.modules.values())
    total_data_points = sum(len(m.data) for m in report.modules.values())

    summary = Text(justify="center")
    summary.append("SCAN COMPLETE\n\n", style="bold bright_magenta")
    summary.append(f"Modules: {successful}/{total_modules} successful", style="white")
    summary.append(f"  •  ", style="dim")
    summary.append(f"Data Points: {total_data_points}", style="white")
    summary.append(f"  •  ", style="dim")
    summary.append(f"Links: {total_urls}", style="white")

    console.print(Panel(
        summary,
        border_style="bright_magenta",
        padding=(1, 4),
    ))
