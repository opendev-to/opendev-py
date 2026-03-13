"""Config subcommand handlers for OpenDev CLI."""

import json
import sys

from rich.console import Console

from opendev.ui_textual.style_tokens import ERROR, WARNING
from opendev.setup import run_setup_wizard


def _handle_config_command(args) -> None:
    """Handle config subcommands.

    Args:
        args: Parsed command-line arguments
    """
    console = Console()

    if not args.config_command:
        console.print(
            f"[{WARNING}]No config subcommand specified. Use --help for available commands.[/{WARNING}]"
        )
        sys.exit(1)

    if args.config_command == "setup":
        # Run setup wizard (can be used to reconfigure)
        if not run_setup_wizard():
            console.print(f"[{WARNING}]Setup cancelled.[/{WARNING}]")
            sys.exit(0)

    elif args.config_command == "show":
        # Display current configuration
        from opendev.core.paths import get_paths

        config_file = get_paths().global_settings

        if not config_file.exists():
            console.print(
                f"[{WARNING}]No configuration found. Run 'swecli config setup' first.[/{WARNING}]"
            )
            sys.exit(1)

        try:
            with open(config_file, "r") as f:
                config = json.load(f)

            from rich.table import Table

            table = Table(title="Current Configuration", show_header=True, header_style="bold cyan")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="white")

            # Display non-sensitive config values
            for key, value in config.items():
                if key == "api_key":
                    # Mask API key
                    if value:
                        masked = (
                            value[:8] + "*" * (len(value) - 12) + value[-4:]
                            if len(value) > 12
                            else "*" * len(value)
                        )
                        table.add_row(key, masked)
                    else:
                        table.add_row(key, "[dim]Not set[/dim]")
                else:
                    table.add_row(key, str(value))

            console.print()
            console.print(table)
            console.print()
            console.print(f"[dim]Config file: {config_file}[/dim]")

        except json.JSONDecodeError:
            console.print(
                f"[{ERROR}]Error: Invalid JSON in configuration file: {config_file}[/{ERROR}]"
            )
            sys.exit(1)
        except Exception as e:
            console.print(f"[{ERROR}]Error reading configuration: {e}[/{ERROR}]")
            sys.exit(1)
