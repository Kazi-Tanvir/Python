"""
PDF Converters Submenu
Centralized entry point for CBZ -> PDF and Image -> PDF converters.
"""

from shared.console import (
    console,
    print_banner,
    print_success,
    print_error,
    print_warning,
    print_info,
)
import converter.cbz_to_pdf as cbz_conv
import converter.img_to_pdf as img_conv

from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt

def run() -> None:
    """Main interactive menu for PDF Converters."""
    # Banner
    banner_text = Text(justify="center")
    banner_text.append("PDF CONVERTERS", style="bold bright_magenta")
    banner_text.append("\n")
    banner_text.append("v1.0.0", style="dim")
    console.print(
        Panel(
            banner_text,
            border_style="bright_magenta",
            padding=(1, 4),
        )
    )

    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  CBZ -> PDF Converter\n"
                "[bold cyan]2[/]  Image -> PDF Converter\n"
                "[bold cyan]0[/]  Back to Main Menu",
                title="[bold]Converters Menu[/bold]",
                border_style="bright_magenta",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask("  Choice", choices=["0", "1", "2"], default="1")

        if choice == "0":
            console.print()
            print_info("Returning to main toolkit...")
            break
        elif choice == "1":
            cbz_conv.run()
        elif choice == "2":
            img_conv.run()


def main() -> None:
    """Alternative entry point."""
    run()


if __name__ == "__main__":
    run()
