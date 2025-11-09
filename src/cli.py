"""Command-line interface for the orchestrator."""

import sys
import json
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from .core.orchestrator import Orchestrator
from .core.config import ConfigManager


console = Console()


@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
@click.pass_context
def cli(ctx, config: Optional[str]):
    """Self-Reflexive Coding Orchestrator CLI.

    Autonomous agent for managing GitHub issues, PRs, and development roadmaps.
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


@cli.command()
@click.option(
    "--mode",
    type=click.Choice(["manual", "supervised", "autonomous"]),
    help="Override orchestrator mode",
)
@click.pass_context
def start(ctx, mode: Optional[str]):
    """Start the orchestrator.

    The orchestrator will run according to its configured mode:
    - manual: Wait for explicit CLI commands
    - supervised: Auto-process but require approval for merges
    - autonomous: Fully automated
    """
    try:
        console.print(
            Panel.fit(
                "🤖 Starting Self-Reflexive Coding Orchestrator", style="bold blue"
            )
        )

        # Initialize orchestrator
        orchestrator = Orchestrator(ctx.obj["config_path"])

        # Override mode if specified
        if mode:
            orchestrator.config.orchestrator.mode = mode
            console.print(f"[yellow]Mode overridden to: {mode}[/yellow]")

        console.print(f"[green]✓[/green] Configuration loaded")
        console.print(
            f"[green]✓[/green] Repository: {orchestrator.config.github.repository}"
        )
        console.print(f"[green]✓[/green] Mode: {orchestrator.config.orchestrator.mode}")
        console.print()

        # Start orchestrator
        orchestrator.start()

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}", style="bold red")
        console.print(
            "\n[yellow]Tip:[/yellow] Copy config/orchestrator-config.yaml.example to config/orchestrator-config.yaml"
        )
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]✗[/red] Configuration error:", style="bold red")
        console.print(str(e))
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx):
    """Show orchestrator status."""
    try:
        orchestrator = Orchestrator(ctx.obj["config_path"])
        status_info = orchestrator.get_status()

        # Create status panel
        console.print(Panel.fit("📊 Orchestrator Status", style="bold blue"))

        # Main info
        table = Table(show_header=False, box=None)
        table.add_column("Key", style="cyan")
        table.add_column("Value")

        table.add_row("State", f"[bold]{status_info['state']}[/bold]")
        table.add_row("Mode", status_info["mode"])
        table.add_row("Repository", status_info["repository"])
        table.add_row("Running", "✓ Yes" if status_info["running"] else "✗ No")

        console.print(table)
        console.print()

        # Work summary
        work_summary = status_info["work_summary"]["work_items"]
        console.print("[bold]Work Items:[/bold]")
        work_table = Table(show_header=True)
        work_table.add_column("Status")
        work_table.add_column("Count", justify="right")

        work_table.add_row("Total", str(work_summary["total"]))
        work_table.add_row("Pending", str(work_summary["pending"]))
        work_table.add_row("In Progress", str(work_summary["in_progress"]))
        work_table.add_row("Completed", str(work_summary["completed"]))
        work_table.add_row("Failed", str(work_summary["failed"]))

        console.print(work_table)
        console.print()

        # Phase 2 statistics if available
        if "phase2_stats" in status_info:
            console.print("[bold]Phase 2 Statistics:[/bold]")

            # Issue Monitor stats
            monitor_stats = status_info["phase2_stats"]["issue_monitor"]
            monitor_table = Table(title="Issue Monitor", show_header=True)
            monitor_table.add_column("Metric")
            monitor_table.add_column("Value", justify="right")

            monitor_table.add_row(
                "Issues Found", str(monitor_stats["total_issues_found"])
            )
            monitor_table.add_row(
                "Issues Claimed", str(monitor_stats["issues_claimed"])
            )
            monitor_table.add_row(
                "Skipped (Concurrent Limit)",
                str(monitor_stats["issues_skipped_concurrent_limit"]),
            )
            monitor_table.add_row(
                "Skipped (Already Claimed)",
                str(monitor_stats["issues_skipped_already_claimed"]),
            )
            monitor_table.add_row(
                "Rate Limit Hits", str(monitor_stats["rate_limit_hits"])
            )

            console.print(monitor_table)
            console.print()

            # Issue Processor stats
            processor_stats = status_info["phase2_stats"]["issue_processor"]
            processor_table = Table(title="Issue Processor", show_header=True)
            processor_table.add_column("Metric")
            processor_table.add_column("Value", justify="right")

            processor_table.add_row(
                "Total Processed", str(processor_stats["total_processed"])
            )
            processor_table.add_row("Successful", str(processor_stats["successful"]))
            processor_table.add_row("Failed", str(processor_stats["failed"]))
            processor_table.add_row(
                "Success Rate", f"{processor_stats['success_rate']:.1f}%"
            )

            console.print(processor_table)

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.argument("issue_number", type=int)
@click.pass_context
def process_issue(ctx, issue_number: int):
    """Manually trigger processing of a specific issue.

    ISSUE_NUMBER: The GitHub issue number to process
    """
    try:
        console.print(f"[blue]→[/blue] Processing issue #{issue_number}...")

        orchestrator = Orchestrator(ctx.obj["config_path"])
        success = orchestrator.process_issue_manually(issue_number)

        if success:
            console.print(
                f"[green]✓[/green] Issue #{issue_number} queued for processing"
            )
        else:
            console.print(f"[red]✗[/red] Failed to queue issue #{issue_number}")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.option(
    "--state",
    type=click.Choice(["open", "closed", "all"]),
    default="open",
    help="Issue state filter",
)
@click.option("--labels", help="Comma-separated list of labels to filter by")
@click.pass_context
def list_issues(ctx, state: str, labels: Optional[str]):
    """List GitHub issues."""
    try:
        orchestrator = Orchestrator(ctx.obj["config_path"])

        label_list = labels.split(",") if labels else None
        issues = orchestrator.github.get_issues(labels=label_list, state=state)

        if not issues:
            console.print("[yellow]No issues found[/yellow]")
            return

        # Create table
        table = Table(title=f"GitHub Issues ({state})")
        table.add_column("#", style="cyan", justify="right")
        table.add_column("Title")
        table.add_column("Labels", style="magenta")
        table.add_column("State")

        for issue in issues[:20]:  # Limit to 20
            issue_labels = ", ".join(label.name for label in issue.labels)
            table.add_row(
                str(issue.number),
                issue.title[:60] + "..." if len(issue.title) > 60 else issue.title,
                issue_labels[:40] + "..." if len(issue_labels) > 40 else issue_labels,
                issue.state,
            )

        console.print(table)
        console.print(
            f"\n[dim]Showing {min(len(issues), 20)} of {len(issues)} issues[/dim]"
        )

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.pass_context
def validate_config(ctx):
    """Validate configuration file."""
    try:
        console.print("[blue]→[/blue] Validating configuration...")

        config_manager = ConfigManager(ctx.obj["config_path"])
        config = config_manager.load()

        console.print("[green]✓[/green] Configuration is valid!")
        console.print()

        # Show key settings
        console.print("[bold]Key Settings:[/bold]")
        table = Table(show_header=False, box=None)
        table.add_column("Setting", style="cyan")
        table.add_column("Value")

        table.add_row("Mode", config.orchestrator.mode)
        table.add_row("Repository", config.github.repository)
        table.add_row("Poll Interval", f"{config.orchestrator.poll_interval}s")
        table.add_row(
            "Max Concurrent Issues", str(config.issue_processing.max_concurrent)
        )
        table.add_row("Auto Merge", "Yes" if config.pr_management.auto_merge else "No")
        table.add_row("Roadmap Enabled", "Yes" if config.roadmap.enabled else "No")

        console.print(table)

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}", style="bold red")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]✗[/red] Configuration errors:", style="bold red")
        console.print(str(e))
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.pass_context
def export_state(ctx):
    """Export current orchestrator state as JSON."""
    try:
        orchestrator = Orchestrator(ctx.obj["config_path"])
        state_json = orchestrator.state_manager.export_state()

        syntax = Syntax(state_json, "json", theme="monokai", line_numbers=True)
        console.print(syntax)

    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}", style="bold red")
        sys.exit(1)


@cli.command()
@click.pass_context
def version(ctx):
    """Show version information."""
    console.print(
        Panel.fit(
            "[bold]Self-Reflexive Coding Orchestrator[/bold]\n"
            "Version: 0.1.0 (Phase 1 - Foundation)\n"
            "Autonomous agent for GitHub workflow automation",
            style="blue",
        )
    )


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
