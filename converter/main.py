"""
PDF & PPT Converters Submenu
Centralized entry point for CBZ → PDF, Image → PDF, PPT → PDF, PPT → README,
PPT → ZIP, and PPT → CBZ converters.
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
import converter.ppt_to_pdf as ppt_pdf_conv
import converter.ppt_to_readme as ppt_readme_conv
import converter.ppt_to_zip as ppt_zip_conv
import converter.ppt_to_cbz as ppt_cbz_conv
import converter.zip_to_pdf as zip_conv

from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt

def run() -> None:
    """Main interactive menu for Converters."""
    # Banner
    banner_text = Text(justify="center")
    banner_text.append("CONVERTERS", style="bold bright_magenta")
    banner_text.append("\n")
    banner_text.append("v1.2.0", style="dim")
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
                "[bold cyan]1[/]  CBZ → PDF Converter\n"
                "[bold cyan]2[/]  Image → PDF Converter\n"
                "[bold cyan]3[/]  PPT → PDF Converter\n"
                "[bold cyan]4[/]  PPT → README Converter\n"
                "[bold cyan]5[/]  PPT → ZIP Converter\n"
                "[bold cyan]6[/]  PPT → CBZ Converter\n"
                "[bold cyan]7[/]  ZIP → PDF Converter\n"
                "[bold cyan]0[/]  Back to Main Menu",
                title="[bold]Converters Menu[/bold]",
                border_style="bright_magenta",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask("  Choice", choices=["0", "1", "2", "3", "4", "5", "6", "7"], default="1")

        if choice == "0":
            console.print()
            print_info("Returning to main toolkit...")
            break
        elif choice == "1":
            cbz_conv.run()
        elif choice == "2":
            img_conv.run()
        elif choice == "3":
            ppt_pdf_conv.run()
        elif choice == "4":
            ppt_readme_conv.run()
        elif choice == "5":
            ppt_zip_conv.run()
        elif choice == "6":
            ppt_cbz_conv.run()
        elif choice == "7":
            zip_conv.run()


def main() -> None:
    """Alternative entry point."""
    run()


if __name__ == "__main__":
    run()

