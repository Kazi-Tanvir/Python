"""
Phone Lookup Orchestrator
==========================
Central coordinator that runs all OSINT lookup modules against a
phone number, aggregates results, and produces a unified report.
"""

import time
import phonenumbers

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Prompt

from shared.console import console, print_error, print_success, print_info, print_warning

from osint.report import OsintReport, ModuleResult, render_terminal, save_json

# Import all lookup modules
from osint.modules import (
    basic_info,
    numverify,
    social_media,
    messaging_apps,
    search_engines,
    data_breaches,
    caller_id,
    reputation,
)


# All modules in execution order
MODULES = [
    ("basic_info", "📱 Basic Phone Information", basic_info),
    ("numverify", "🌐 API Validation & Carrier", numverify),
    ("social_media", "📘 Social Media Profiles", social_media),
    ("messaging_apps", "💬 Messaging Applications", messaging_apps),
    ("search_engines", "🔍 Search Engine Intelligence", search_engines),
    ("data_breaches", "💀 Data Breach Exposure", data_breaches),
    ("caller_id", "☎️  Caller ID & Directories", caller_id),
    ("reputation", "⚠️  Reputation & Risk Score", reputation),
]


def parse_phone_number(raw_input: str) -> phonenumbers.PhoneNumber | None:
    """
    Parse a raw phone number string into a PhoneNumber object.
    Tries multiple parsing strategies:
    1. Direct parse (if country code is present, e.g., +1...)
    2. Parse with common default regions (US, GB, IN, BD, etc.)
    """
    raw_input = raw_input.strip()

    # If the number starts with +, parse directly
    if raw_input.startswith("+"):
        try:
            parsed = phonenumbers.parse(raw_input, None)
            if phonenumbers.is_possible_number(parsed):
                return parsed
        except phonenumbers.NumberParseException:
            pass

    # Try common regions
    for region in ["US", "GB", "IN", "BD", "CA", "AU", "DE", "FR", "JP", "BR", "PH"]:
        try:
            parsed = phonenumbers.parse(raw_input, region)
            if phonenumbers.is_valid_number(parsed):
                return parsed
        except phonenumbers.NumberParseException:
            continue

    # Last resort: try without region
    try:
        parsed = phonenumbers.parse(raw_input, None)
        return parsed
    except phonenumbers.NumberParseException:
        return None


def run_scan(phone_raw: str) -> OsintReport | None:
    """
    Run the full OSINT scan on a phone number.

    Args:
        phone_raw: Raw phone number string (any format).

    Returns:
        OsintReport with all gathered intelligence, or None on failure.
    """
    # Parse the phone number
    parsed = parse_phone_number(phone_raw)
    if parsed is None:
        print_error(
            f"Could not parse phone number: {phone_raw}\n"
            "  Try including the country code (e.g., +1 555 123 4567)"
        )
        return None

    # Format for display
    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    international = phonenumbers.format_number(
        parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
    )
    country = phonenumbers.geocoder.description_for_number(parsed, "en") or "Unknown"

    console.print()
    print_success(f"Phone number parsed: [bold]{international}[/bold]")
    print_info(f"E.164: {e164}  |  Region: {country}")
    console.print()

    # Create report
    report = OsintReport(
        phone_number=phone_raw,
        phone_e164=e164,
        country=country,
    )

    # Run all modules with progress tracking
    with Progress(
        SpinnerColumn(style="bright_magenta"),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        BarColumn(bar_width=30, style="bright_magenta", complete_style="green"),
        TextColumn("[dim]{task.fields[status]}[/dim]"),
        console=console,
        transient=False,
    ) as progress:

        overall = progress.add_task(
            "OSINT Scan Progress",
            total=len(MODULES),
            status="Starting...",
        )

        for module_key, module_name, module in MODULES:
            progress.update(overall, status=f"Running: {module_name}")

            try:
                result = module.lookup(phone_raw, parsed)
                report.add_module_result(result)

                if result.success:
                    status = f"✅ {module_name}"
                else:
                    status = f"⚠️ {module_name} (partial)"

            except Exception as e:
                error_result = ModuleResult(
                    module_name=module_key,
                    success=False,
                    errors=[f"Module crashed: {str(e)}"],
                )
                report.add_module_result(error_result)
                status = f"❌ {module_name} (failed)"

            progress.update(overall, advance=1, status=status)

        progress.update(overall, status="✅ Scan complete!")

    return report


def run_interactive() -> None:
    """
    Interactive phone lookup — prompts for a number and runs the full scan.
    """
    console.print()
    phone_raw = Prompt.ask(
        "  [bold cyan]Enter phone number[/bold cyan] (with country code, e.g. +1 555 123 4567)"
    )

    if not phone_raw.strip():
        print_error("No phone number entered.")
        return

    console.print()
    console.rule("[bold bright_magenta]Starting OSINT Scan[/bold bright_magenta]")
    console.print()

    start_time = time.time()
    report = run_scan(phone_raw)
    elapsed = time.time() - start_time

    if report is None:
        return

    # Render the report
    render_terminal(report)

    # Save JSON
    json_path = save_json(report)
    console.print()
    print_success(f"Report saved to: [bold]{json_path}[/bold]")
    print_info(f"Scan completed in {elapsed:.1f} seconds")
    console.print()
