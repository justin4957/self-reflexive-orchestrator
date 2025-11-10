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


@cli.command("generate-roadmap")
@click.option("--force", is_flag=True, help="Force generation regardless of schedule")
@click.option(
    "--goals",
    multiple=True,
    help="Project goals for roadmap context (can specify multiple times)",
)
@click.pass_context
def generate_roadmap(ctx, force: bool, goals: tuple):
    """Generate development roadmap with multi-agent collaboration.

    This command executes the complete roadmap cycle:
    1. Analyzes codebase structure and metrics
    2. Generates feature proposals from multiple AI perspectives
    3. Validates proposals through dialectical method
    4. Creates GitHub issues for approved proposals
    """
    try:
        console.print(Panel.fit("🗺️  Generating Development Roadmap", style="bold blue"))

        # Initialize orchestrator to get clients
        from .cycles.roadmap_cycle import RoadmapCycle
        from .core.logger import setup_logging
        from .integrations.github_client import GitHubClient
        from .integrations.multi_agent_coder_client import MultiAgentCoderClient
        from .core.config import ConfigManager

        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load_config()
        logger = setup_logging()

        # Initialize clients
        github_client = GitHubClient(
            token=config.github.token,
            repository=config.github.repository,
            logger=logger,
        )

        multi_agent_client = MultiAgentCoderClient(
            multi_agent_coder_path=config.multi_agent_coder.executable_path,
            logger=logger,
        )

        # Initialize roadmap cycle
        roadmap_cycle = RoadmapCycle(
            repository_path=str(Path.cwd()),
            github_client=github_client,
            multi_agent_client=multi_agent_client,
            logger=logger,
            scheduler_frequency=config.roadmap.generation_frequency,
            auto_create_issues=config.roadmap.auto_create_issues,
        )

        # Check if should run
        if not force and not roadmap_cycle.should_run_cycle():
            schedule_status = roadmap_cycle.get_schedule_status()
            console.print("[yellow]⚠️  Roadmap generation not due yet[/yellow]")
            console.print(
                f"Last generated: {schedule_status['last_generation_time'] or 'never'}"
            )
            console.print(
                f"Next scheduled: {schedule_status['next_scheduled_time'] or 'N/A'}"
            )
            console.print("\nUse --force to generate anyway")
            return

        # Convert goals tuple to list
        project_goals = list(goals) if goals else None

        if project_goals:
            console.print("\n[bold]Project Goals:[/bold]")
            for goal in project_goals:
                console.print(f"  • {goal}")
            console.print()

        # Execute cycle
        console.print("[cyan]Starting roadmap cycle...[/cyan]\n")
        result = roadmap_cycle.execute_cycle(project_goals=project_goals, force=force)

        # Display results
        console.print("\n[green]✅ Roadmap cycle completed successfully![/green]\n")

        # Summary table
        summary_table = Table(title="Cycle Summary", show_header=False)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value")

        summary_table.add_row("Cycle ID", result.cycle_id)
        summary_table.add_row("Duration", f"{result.duration_seconds:.1f}s")
        summary_table.add_row("Total Cost", f"${result.total_cost:.4f}")
        summary_table.add_row("Total Tokens", f"{result.total_tokens:,}")
        summary_table.add_row("Proposals Generated", str(result.proposals_generated))
        summary_table.add_row("Proposals Approved", str(result.proposals_approved))
        summary_table.add_row("Proposals Rejected", str(result.proposals_rejected))
        summary_table.add_row("Issues Created", str(result.issues_created))

        console.print(summary_table)

        # Display created issues
        if result.issues_created > 0:
            console.print("\n[bold]Created Issues:[/bold]")
            for issue in result.issue_creation.created_issues:
                console.print(f"  • #{issue.issue_number}: {issue.title}")
                console.print(f"    {issue.url}")

        # Roadmap file
        if result.roadmap.file_path:
            console.print(
                f"\n[bold]Roadmap saved to:[/bold] {result.roadmap.file_path}"
            )

    except Exception as e:
        console.print(f"[red]✗ Error generating roadmap: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("roadmap-status")
@click.pass_context
def roadmap_status(ctx):
    """Show roadmap generation schedule status."""
    try:
        from .cycles.roadmap_cycle import RoadmapCycle
        from .core.logger import setup_logging
        from .integrations.github_client import GitHubClient
        from .integrations.multi_agent_coder_client import MultiAgentCoderClient
        from .core.config import ConfigManager

        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load_config()
        logger = setup_logging()

        # Initialize clients
        github_client = GitHubClient(
            token=config.github.token,
            repository=config.github.repository,
            logger=logger,
        )

        multi_agent_client = MultiAgentCoderClient(
            multi_agent_coder_path=config.multi_agent_coder.executable_path,
            logger=logger,
        )

        # Initialize roadmap cycle
        roadmap_cycle = RoadmapCycle(
            repository_path=str(Path.cwd()),
            github_client=github_client,
            multi_agent_client=multi_agent_client,
            logger=logger,
            scheduler_frequency=config.roadmap.generation_frequency,
        )

        status = roadmap_cycle.get_schedule_status()

        # Display status
        console.print(Panel.fit("🗓️  Roadmap Schedule Status", style="bold blue"))

        status_table = Table(show_header=False)
        status_table.add_column("Key", style="cyan")
        status_table.add_column("Value")

        status_table.add_row("Frequency", status["frequency"])
        status_table.add_row(
            "Last Generation", status["last_generation_time"] or "Never"
        )
        status_table.add_row("Last Roadmap ID", status["last_roadmap_id"] or "N/A")
        status_table.add_row("Generation Count", str(status["generation_count"]))
        status_table.add_row("Next Scheduled", status["next_scheduled_time"] or "N/A")

        if status["time_until_next_seconds"] is not None:
            hours = status["time_until_next_seconds"] / 3600
            status_table.add_row("Time Until Next", f"{hours:.1f} hours")

        is_due = status["is_due"]
        status_table.add_row(
            "Is Due", "[green]Yes[/green]" if is_due else "[yellow]No[/yellow]"
        )

        if status["last_error"]:
            status_table.add_row("Last Error", status["last_error"])
            status_table.add_row("Error Time", status["last_error_time"] or "N/A")

        console.print(status_table)

    except Exception as e:
        console.print(f"[red]✗ Error getting status: {e}[/red]", style="bold red")
        sys.exit(1)


@cli.command("show-roadmap")
@click.pass_context
def show_roadmap(ctx):
    """Display the most recently generated roadmap."""
    try:
        from .cycles.roadmap_cycle import RoadmapCycle
        from .core.logger import setup_logging
        from .integrations.github_client import GitHubClient
        from .integrations.multi_agent_coder_client import MultiAgentCoderClient
        from .core.config import ConfigManager

        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load_config()
        logger = setup_logging()

        # Initialize clients
        github_client = GitHubClient(
            token=config.github.token,
            repository=config.github.repository,
            logger=logger,
        )

        multi_agent_client = MultiAgentCoderClient(
            multi_agent_coder_path=config.multi_agent_coder.executable_path,
            logger=logger,
        )

        # Initialize roadmap cycle
        roadmap_cycle = RoadmapCycle(
            repository_path=str(Path.cwd()),
            github_client=github_client,
            multi_agent_client=multi_agent_client,
            logger=logger,
            scheduler_frequency=config.roadmap.generation_frequency,
        )

        roadmap_path = roadmap_cycle.get_last_roadmap_path()

        if not roadmap_path:
            console.print("[yellow]⚠️  No roadmap found[/yellow]")
            console.print("Generate one with: orchestrator generate-roadmap")
            return

        # Read and display roadmap
        with open(roadmap_path, "r") as f:
            content = f.read()

        console.print(Panel.fit(f"📄 Roadmap: {roadmap_path.name}", style="bold blue"))
        console.print()

        # Display with syntax highlighting
        syntax = Syntax(content, "markdown", theme="monokai", line_numbers=False)
        console.print(syntax)

    except Exception as e:
        console.print(f"[red]✗ Error displaying roadmap: {e}[/red]", style="bold red")
        sys.exit(1)


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
