"""MCP subcommand handlers for OpenDev CLI."""

import sys

from rich.console import Console

from opendev.ui_textual.style_tokens import CYAN, ERROR, SUCCESS, WARNING


def _handle_mcp_command(args) -> None:
    """Handle MCP subcommands.

    Args:
        args: Parsed command-line arguments
    """
    from opendev.core.context_engineering.mcp.manager import MCPManager
    from rich.table import Table

    console = Console()
    mcp_manager = MCPManager()

    if not args.mcp_command:
        console.print(
            f"[{WARNING}]No MCP subcommand specified. Use --help for available commands.[/{WARNING}]"
        )
        sys.exit(1)

    try:
        if args.mcp_command == "list":
            servers = mcp_manager.list_servers()

            if not servers:
                console.print(f"[{WARNING}]No MCP servers configured[/{WARNING}]")
                return

            table = Table(title="MCP Servers", show_header=True, header_style="bold cyan")
            table.add_column("Name", style="cyan")
            table.add_column("Command")
            table.add_column("Enabled", justify="center")
            table.add_column("Auto-start", justify="center")

            for name, config in servers.items():
                enabled = f"[{SUCCESS}]✓[/{SUCCESS}]" if config.enabled else f"[{ERROR}]✗[/{ERROR}]"
                auto_start = f"[{SUCCESS}]✓[/{SUCCESS}]" if config.auto_start else "[dim]-[/dim]"
                command = (
                    f"{config.command} {' '.join(config.args[:2])}"
                    if config.args
                    else config.command
                )
                if len(command) > 60:
                    command = command[:57] + "..."

                table.add_row(name, command, enabled, auto_start)

            console.print(table)

        elif args.mcp_command == "get":
            servers = mcp_manager.list_servers()
            if args.name not in servers:
                console.print(f"[{ERROR}]Error: Server '{args.name}' not found[/{ERROR}]")
                sys.exit(1)

            config = servers[args.name]
            console.print(f"\n[bold {CYAN}]{args.name}[/bold {CYAN}]\n")
            console.print(f"Command: {config.command}")
            if config.args:
                console.print(f"Args: {' '.join(config.args)}")
            if config.env:
                console.print("Environment variables:")
                for key, value in config.env.items():
                    console.print(f"  {key}={value}")
            console.print(f"Enabled: {'Yes' if config.enabled else 'No'}")
            console.print(f"Auto-start: {'Yes' if config.auto_start else 'No'}")
            console.print(f"Transport: {config.transport}")

        elif args.mcp_command == "add":
            # Parse environment variables
            env = {}
            if args.env:
                for env_var in args.env:
                    if "=" not in env_var:
                        console.print(
                            f"[{ERROR}]Error: Invalid environment variable format: {env_var}[/{ERROR}]"
                        )
                        console.print("Use KEY=VALUE format")
                        sys.exit(1)
                    key, value = env_var.split("=", 1)
                    env[key] = value

            mcp_manager.add_server(
                name=args.name, command=args.command, args=args.args or [], env=env
            )

            # Update auto_start if specified
            if args.no_auto_start:
                config = mcp_manager.get_config()
                config.mcp_servers[args.name].auto_start = False
                from opendev.core.context_engineering.mcp.config import save_config

                save_config(config)

            console.print(f"[{SUCCESS}]✓[/{SUCCESS}] Added MCP server '{args.name}'")

        elif args.mcp_command == "remove":
            success = mcp_manager.remove_server(args.name)
            if success:
                console.print(f"[{SUCCESS}]✓[/{SUCCESS}] Removed MCP server '{args.name}'")
            else:
                console.print(f"[{ERROR}]Error: Server '{args.name}' not found[/{ERROR}]")
                sys.exit(1)

        elif args.mcp_command == "enable":
            success = mcp_manager.enable_server(args.name)
            if success:
                console.print(f"[{SUCCESS}]✓[/{SUCCESS}] Enabled MCP server '{args.name}'")
            else:
                console.print(f"[{ERROR}]Error: Server '{args.name}' not found[/{ERROR}]")
                sys.exit(1)

        elif args.mcp_command == "disable":
            success = mcp_manager.disable_server(args.name)
            if success:
                console.print(f"[{SUCCESS}]✓[/{SUCCESS}] Disabled MCP server '{args.name}'")
            else:
                console.print(f"[{ERROR}]Error: Server '{args.name}' not found[/{ERROR}]")
                sys.exit(1)

    except Exception as e:
        console.print(f"[{ERROR}]Error: {str(e)}[/{ERROR}]")
        sys.exit(1)
