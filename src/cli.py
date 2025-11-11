"""Command-line interface for the orchestrator."""

import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .core.config import ConfigManager
from .core.orchestrator import Orchestrator

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
        from .core.config import ConfigManager
        from .core.logger import setup_logging
        from .cycles.roadmap_cycle import RoadmapCycle
        from .integrations.github_client import GitHubClient
        from .integrations.multi_agent_coder_client import MultiAgentCoderClient

        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load()
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
        from .core.config import ConfigManager
        from .core.logger import setup_logging
        from .cycles.roadmap_cycle import RoadmapCycle
        from .integrations.github_client import GitHubClient
        from .integrations.multi_agent_coder_client import MultiAgentCoderClient

        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load()
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
        from .core.config import ConfigManager
        from .core.logger import setup_logging
        from .cycles.roadmap_cycle import RoadmapCycle
        from .integrations.github_client import GitHubClient
        from .integrations.multi_agent_coder_client import MultiAgentCoderClient

        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load()
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


@cli.command("usage-report")
@click.option(
    "--detailed",
    is_flag=True,
    help="Show detailed per-provider breakdown",
)
@click.pass_context
def usage_report(ctx, detailed: bool):
    """Show API usage and cost report.

    Displays current usage statistics including:
    - Daily cost and remaining budget
    - Token usage by provider
    - Rate limit status
    - Request counts
    """
    try:
        from .core.logger import setup_logging
        from .integrations.github_client import GitHubClient
        from .safety.cost_tracker import CostTracker
        from .safety.rate_limiter import RateLimiter

        console.print(Panel.fit("📊 API Usage Report", style="bold blue"))
        console.print()

        # Load configuration
        config_manager = ConfigManager(ctx.obj["config_path"])
        config = config_manager.load()
        logger = setup_logging(log_level="INFO")

        # Initialize cost tracker
        max_daily_cost = config.safety.max_api_cost_per_day
        cost_tracker = CostTracker(
            max_daily_cost=max_daily_cost,
            logger=logger,
        )

        # Get usage report
        usage = cost_tracker.get_usage_report()

        # Display summary
        console.print("[bold]Cost Summary[/bold]")
        console.print(f"  Date: {usage['date']}")
        console.print(f"  Daily Limit: ${usage['daily_limit']:.2f}")
        console.print(
            f"  Total Cost: [{'red' if usage['status'] == 'EXCEEDED' else 'yellow' if usage['status'] in ['WARNING', 'CRITICAL'] else 'green'}]${usage['total_cost']:.4f}[/]"
        )
        console.print(f"  Remaining Budget: ${usage['remaining_budget']:.2f}")
        console.print(f"  Percentage Used: {usage['percentage_used']:.1f}%")
        console.print(
            f"  Status: [{_get_status_color(usage['status'])}]{usage['status']}[/]"
        )
        console.print()

        # Display request stats
        console.print("[bold]Request Statistics[/bold]")
        console.print(f"  Total Requests: {usage['total_requests']}")
        console.print(f"  Total Tokens: {usage['total_tokens']:,}")
        console.print()

        # Display per-provider breakdown
        if detailed and usage["provider_breakdown"]:
            console.print("[bold]Provider Breakdown[/bold]")

            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Provider", style="cyan")
            table.add_column("Requests", justify="right")
            table.add_column("Tokens (In)", justify="right")
            table.add_column("Tokens (Out)", justify="right")
            table.add_column("Total Tokens", justify="right")
            table.add_column("Cost", justify="right")
            table.add_column("% of Total", justify="right")

            for provider, stats in sorted(
                usage["provider_breakdown"].items(),
                key=lambda x: x[1]["cost"],
                reverse=True,
            ):
                table.add_row(
                    provider.upper(),
                    str(stats["requests"]),
                    f"{stats['tokens_input']:,}",
                    f"{stats['tokens_output']:,}",
                    f"{stats['tokens_total']:,}",
                    f"${stats['cost']:.4f}",
                    f"{stats['cost_percentage']:.1f}%",
                )

            console.print(table)
            console.print()

        # Display rate limit status
        console.print("[bold]Rate Limit Status[/bold]")

        rate_limiter = RateLimiter(logger=logger, enable_throttling=False)
        rate_status = rate_limiter.get_status()

        if rate_status.get("apis"):
            for api, info in rate_status["apis"].items():
                status_color = _get_status_color(info["status"])
                console.print(f"  {api.upper()}:")
                console.print(
                    f"    Status: [{status_color}]{info['status'].upper()}[/]"
                )

                if info["info"]:
                    api_info = info["info"]
                    console.print(f"    Limit: {api_info['limit']}")
                    console.print(f"    Remaining: {api_info['remaining']}")
                    console.print(
                        f"    Used: {api_info['used']} ({api_info['percentage_used']:.1f}%)"
                    )
                    console.print(
                        f"    Reset in: {api_info['seconds_until_reset']:.0f}s"
                    )
        else:
            console.print("  [dim]No rate limit data available[/dim]")

    except Exception as e:
        console.print(
            f"[red]✗ Error generating usage report: {e}[/red]", style="bold red"
        )
        import traceback

        traceback.print_exc()
        sys.exit(1)


def _get_status_color(status: str) -> str:
    """Get color for status."""
    status_upper = status.upper()
    if status_upper == "OK":
        return "green"
    elif status_upper == "WARNING":
        return "yellow"
    elif status_upper in ["CRITICAL", "EXCEEDED"]:
        return "red"
    else:
        return "white"


@cli.command("rollback")
@click.argument("target")
@click.option(
    "--type",
    "rollback_type",
    type=click.Choice(["pr", "tag", "commit"]),
    default="tag",
    help="Type of rollback target (pr number, tag name, or commit SHA)",
)
@click.option(
    "--reason",
    help="Reason for rollback (required for PR rollbacks)",
)
@click.option(
    "--no-cleanup",
    is_flag=True,
    help="Skip branch cleanup after rollback",
)
@click.option(
    "--hard-reset",
    is_flag=True,
    help="Use hard reset instead of revert commits (dangerous, loses history)",
)
@click.option(
    "--create-revert-pr",
    is_flag=True,
    help="Create a revert PR instead of direct revert (for PR rollbacks)",
)
@click.pass_context
def rollback(
    ctx,
    target: str,
    rollback_type: str,
    reason: Optional[str],
    no_cleanup: bool,
    hard_reset: bool,
    create_revert_pr: bool,
):
    """Rollback failed changes or merged PRs.

    TARGET: The rollback target (PR number, tag name, or commit SHA)

    Examples:
      orchestrator rollback 123 --type pr --reason "Tests failing"
      orchestrator rollback rollback-point-20240115-143022 --type tag
      orchestrator rollback abc123def --type commit
      orchestrator rollback --list-tags
    """
    try:
        from .core.config import ConfigManager
        from .core.logger import setup_logging
        from .integrations.github_client import GitHubClient
        from .safety.rollback import RollbackManager

        console.print(Panel.fit("🔄 Rollback Operation", style="bold blue"))

        # Load configuration
        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load()
        logger = setup_logging()

        # Initialize GitHub client
        github_client = GitHubClient(
            token=config.github.token,
            repository=config.github.repository,
            logger=logger,
        )

        # Initialize rollback manager
        rollback_manager = RollbackManager(
            repository_path=str(Path.cwd()),
            github_client=github_client,
            logger=logger,
            auto_cleanup_branches=not no_cleanup,
        )

        # Handle different rollback types
        if rollback_type == "pr":
            # Rollback a merged PR
            if not reason:
                console.print(
                    "[red]✗[/red] --reason is required for PR rollbacks",
                    style="bold red",
                )
                sys.exit(1)

            try:
                pr_number = int(target)
            except ValueError:
                console.print(
                    f"[red]✗[/red] Invalid PR number: {target}", style="bold red"
                )
                sys.exit(1)

            console.print(f"[cyan]→[/cyan] Rolling back PR #{pr_number}...")
            console.print(f"[dim]Reason: {reason}[/dim]")

            result = rollback_manager.rollback_pr(
                pr_number=pr_number,
                reason=reason,
                create_revert_pr=create_revert_pr,
            )

        else:
            # Rollback to a tag or commit
            console.print(
                f"[cyan]→[/cyan] Rolling back to {rollback_type}: {target}..."
            )

            # For tag rollback, find the rollback point
            if rollback_type == "tag":
                rollback_points = rollback_manager.list_rollback_points()
                rollback_point = None

                for rp in rollback_points:
                    if rp.tag_name == target:
                        rollback_point = rp
                        break

                if not rollback_point:
                    console.print(
                        f"[red]✗[/red] Rollback point not found: {target}",
                        style="bold red",
                    )
                    console.print("\nAvailable rollback points:")
                    for rp in rollback_points:
                        console.print(f"  • {rp.tag_name} ({rp.description})")
                    sys.exit(1)

            else:  # commit
                # Create temporary rollback point for commit
                from datetime import datetime, timezone

                from .safety.rollback import RollbackPoint

                rollback_point = RollbackPoint(
                    commit_sha=target,
                    tag_name=f"rollback-to-{target[:8]}",
                    description=f"Rollback to commit {target[:8]}",
                    created_at=datetime.now(timezone.utc),
                    branch_name=rollback_manager._get_current_branch(),
                )

            # Perform rollback
            result = rollback_manager.rollback(
                rollback_point=rollback_point,
                cleanup_branches=not no_cleanup,
                create_revert_commit=not hard_reset,
            )

        # Display results
        if result.success:
            console.print("\n[green]✅ Rollback completed successfully![/green]\n")

            # Results table
            results_table = Table(show_header=False)
            results_table.add_column("Metric", style="cyan")
            results_table.add_column("Value")

            results_table.add_row("Target", result.rollback_point.tag_name)
            results_table.add_row("Commits Reverted", str(len(result.reverted_commits)))
            results_table.add_row("Branches Cleaned", str(len(result.cleaned_branches)))

            if result.revert_commit_sha:
                results_table.add_row(
                    "Revert Commit", result.revert_commit_sha[:8] + "..."
                )

            console.print(results_table)

            if result.reverted_commits:
                console.print("\n[bold]Reverted Commits:[/bold]")
                for commit_sha in result.reverted_commits[:5]:
                    console.print(f"  • {commit_sha[:8]}")
                if len(result.reverted_commits) > 5:
                    console.print(f"  ... and {len(result.reverted_commits) - 5} more")

            if result.cleaned_branches:
                console.print("\n[bold]Cleaned Branches:[/bold]")
                for branch in result.cleaned_branches:
                    console.print(f"  • {branch}")

        else:
            console.print("\n[red]✗ Rollback failed[/red]\n", style="bold red")
            console.print(f"Error: {result.error}")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]✗ Rollback error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("list-rollback-points")
@click.pass_context
def list_rollback_points(ctx):
    """List available rollback points (tags).

    Shows all rollback points that have been created before risky operations.
    """
    try:
        from .core.config import ConfigManager
        from .core.logger import setup_logging
        from .integrations.github_client import GitHubClient
        from .safety.rollback import RollbackManager

        console.print(Panel.fit("🏷️  Rollback Points", style="bold blue"))

        # Load configuration
        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load()
        logger = setup_logging()

        # Initialize GitHub client
        github_client = GitHubClient(
            token=config.github.token,
            repository=config.github.repository,
            logger=logger,
        )

        # Initialize rollback manager
        rollback_manager = RollbackManager(
            repository_path=str(Path.cwd()),
            github_client=github_client,
            logger=logger,
        )

        # Get rollback points
        rollback_points = rollback_manager.list_rollback_points()

        if not rollback_points:
            console.print("[yellow]No rollback points found[/yellow]")
            console.print(
                "\nRollback points are created automatically before risky operations."
            )
            return

        # Display table
        table = Table(title=f"Available Rollback Points ({len(rollback_points)})")
        table.add_column("Tag Name", style="cyan")
        table.add_column("Commit", style="yellow")
        table.add_column("Description")
        table.add_column("Created At")

        for rp in sorted(rollback_points, key=lambda x: x.created_at, reverse=True):
            table.add_row(
                rp.tag_name,
                rp.commit_sha[:8] + "...",
                (
                    rp.description[:50] + "..."
                    if len(rp.description) > 50
                    else rp.description
                ),
                rp.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            )

        console.print(table)

        console.print(
            "\n[dim]Use 'orchestrator rollback <tag_name> --type tag' to rollback to a point[/dim]"
        )

    except Exception as e:
        console.print(
            f"[red]✗ Error listing rollback points: {e}[/red]", style="bold red"
        )
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("health")
@click.option(
    "--json-output",
    is_flag=True,
    help="Output health report as JSON",
)
@click.pass_context
def health(ctx, json_output: bool):
    """Check orchestrator health status.

    Performs comprehensive health checks including:
    - System resources (memory, disk, CPU)
    - API connectivity (GitHub, Anthropic)
    - Integration availability (git, multi-agent-coder)
    """
    try:
        from .core.config import ConfigManager
        from .core.health import HealthChecker, HealthStatus
        from .core.logger import setup_logging
        from .integrations.github_client import GitHubClient
        from .integrations.multi_agent_coder_client import MultiAgentCoderClient

        # Load configuration
        config_manager = ConfigManager(ctx.obj.get("config_path"))
        config = config_manager.load()
        logger = setup_logging()

        # Initialize clients for API checks
        github_client = None
        try:
            github_client = GitHubClient(
                token=config.github.token,
                repository=config.github.repository,
                logger=logger,
            )
        except Exception as e:
            if not json_output:
                console.print(
                    f"[yellow]Warning: Could not initialize GitHub client: {e}[/yellow]"
                )

        # Initialize health checker
        health_checker = HealthChecker(
            logger=logger,
            github_client=github_client,
            multi_agent_coder_path=config.multi_agent_coder.executable_path,
        )

        # Perform health check
        if not json_output:
            console.print(Panel.fit("🏥 Health Check", style="bold blue"))
            console.print()

        report = health_checker.check_health()

        if json_output:
            # Output as JSON
            import json

            print(json.dumps(report.to_dict(), indent=2))
        else:
            # Display formatted output
            # Overall status
            status_colors = {
                HealthStatus.HEALTHY: "green",
                HealthStatus.DEGRADED: "yellow",
                HealthStatus.UNHEALTHY: "red",
                HealthStatus.UNKNOWN: "white",
            }
            status_color = status_colors.get(report.overall_status, "white")

            console.print(
                f"[bold {status_color}]{report.summary}[/bold {status_color}]"
            )
            console.print()

            # Checks table
            table = Table(title="Health Checks", show_header=True)
            table.add_column("Check", style="cyan")
            table.add_column("Status")
            table.add_column("Message")
            table.add_column("Duration", justify="right")

            for check in report.checks:
                status_symbol = {
                    HealthStatus.HEALTHY: "[green]✓[/green]",
                    HealthStatus.DEGRADED: "[yellow]⚠[/yellow]",
                    HealthStatus.UNHEALTHY: "[red]✗[/red]",
                    HealthStatus.UNKNOWN: "[white]?[/white]",
                }
                symbol = status_symbol.get(check.status, "?")

                status_text = f"{symbol} {check.status.value}"

                table.add_row(
                    check.name,
                    status_text,
                    check.message,
                    f"{check.duration_ms:.1f}ms",
                )

            console.print(table)

            # Details for unhealthy/degraded checks
            problem_checks = [
                c
                for c in report.checks
                if c.status in [HealthStatus.UNHEALTHY, HealthStatus.DEGRADED]
            ]

            if problem_checks:
                console.print("\n[bold]Issues Detected:[/bold]")
                for check in problem_checks:
                    console.print(f"\n[yellow]• {check.name}:[/yellow]")
                    console.print(f"  {check.message}")
                    if check.details:
                        for key, value in check.details.items():
                            if key != "error":
                                console.print(f"  {key}: {value}")

        # Exit with appropriate code
        if report.overall_status == HealthStatus.UNHEALTHY:
            sys.exit(1)
        elif report.overall_status == HealthStatus.DEGRADED:
            sys.exit(2)
        else:
            sys.exit(0)

    except Exception as e:
        console.print(f"[red]✗ Health check failed: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(3)


@cli.command("metrics")
@click.option(
    "--json-output",
    is_flag=True,
    help="Output metrics as JSON",
)
@click.option(
    "--time-window",
    type=int,
    help="Time window in hours (default: all time)",
)
@click.pass_context
def metrics(ctx, json_output: bool, time_window: Optional[int]):
    """Display orchestrator metrics.

    Shows operational metrics including:
    - Work items processed
    - Success/failure rates
    - API call counts
    - Error statistics
    - Response times
    - Cost tracking
    """
    try:
        from .core.metrics import MetricsCollector

        console.print(Panel.fit("📊 Orchestrator Metrics", style="bold blue"))
        console.print()

        # For now, create a sample collector
        # In production, this would load from persistent storage
        collector = MetricsCollector()

        summary = collector.get_summary(time_window_hours=time_window)

        if json_output:
            # Output as JSON
            import json

            print(json.dumps(summary.to_dict(), indent=2))
        else:
            # Display formatted output
            console.print("[bold]Work Items:[/bold]")
            work_table = Table(show_header=False)
            work_table.add_column("Metric", style="cyan")
            work_table.add_column("Value")

            work_table.add_row("Processed", str(summary.work_items_processed))
            work_table.add_row(
                "Succeeded", f"[green]{summary.work_items_succeeded}[/green]"
            )
            work_table.add_row("Failed", f"[red]{summary.work_items_failed}[/red]")
            work_table.add_row("Success Rate", f"{summary.success_rate * 100:.1f}%")

            console.print(work_table)
            console.print()

            # API Calls
            console.print("[bold]API Calls:[/bold]")
            api_table = Table(show_header=False)
            api_table.add_column("Provider", style="cyan")
            api_table.add_column("Calls", justify="right")

            api_table.add_row("Total", str(summary.api_calls_total))
            for provider, count in summary.api_calls_by_provider.items():
                api_table.add_row(f"  {provider}", str(count))

            console.print(api_table)
            console.print()

            # Errors
            if summary.errors_total > 0:
                console.print("[bold]Errors:[/bold]")
                error_table = Table(show_header=False)
                error_table.add_column("Type", style="cyan")
                error_table.add_column("Count", justify="right")

                error_table.add_row("Total", f"[red]{summary.errors_total}[/red]")
                for error_type, count in summary.errors_by_type.items():
                    error_table.add_row(f"  {error_type}", str(count))

                console.print(error_table)
                console.print()

            # Performance
            console.print("[bold]Performance:[/bold]")
            perf_table = Table(show_header=False)
            perf_table.add_column("Metric", style="cyan")
            perf_table.add_column("Value")

            perf_table.add_row(
                "Avg Response Time", f"{summary.avg_response_time_ms:.1f}ms"
            )
            perf_table.add_row("Total Cost", f"${summary.total_cost:.4f}")

            console.print(perf_table)

    except Exception as e:
        console.print(f"[red]✗ Metrics error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("approval-list")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def approval_list(ctx, json_output: bool):
    """List pending approval requests."""
    try:
        from .core.logger import get_logger
        from .safety.approval import ApprovalSystem

        # Initialize approval system
        logger = get_logger()
        approval_system = ApprovalSystem(logger=logger)

        # Get pending approvals
        pending = approval_system.get_pending_approvals()

        if json_output:
            output = [req.to_dict() for req in pending]
            print(json.dumps(output, indent=2))
            return

        if not pending:
            console.print("[yellow]No pending approvals[/yellow]")
            return

        console.print(Panel.fit("Pending Approval Requests", style="bold blue"))

        for request in pending:
            # Risk level color
            risk_colors = {
                "low": "green",
                "medium": "yellow",
                "high": "orange1",
                "critical": "red",
            }
            risk_color = risk_colors.get(request.risk_level.value, "white")

            # Build panel content
            lines = []
            lines.append(f"[bold]Request ID:[/bold] {request.request_id}")
            lines.append(f"[bold]Operation:[/bold] {request.operation}")
            lines.append(
                f"[bold]Risk Level:[/bold] [{risk_color}]{request.risk_level.value.upper()}[/{risk_color}]"
            )
            lines.append(
                f"[bold]Time Remaining:[/bold] {request.time_remaining_hours:.1f} hours"
            )
            lines.append("")
            lines.append("[bold]Concerns:[/bold]")
            for concern in request.concerns:
                lines.append(f"  • {concern}")

            if request.context:
                lines.append("")
                lines.append("[bold]Context:[/bold]")
                for key, value in request.context.items():
                    lines.append(f"  {key}: {value}")

            panel = Panel(
                "\n".join(lines),
                title=f"[{risk_color}]{request.operation}[/{risk_color}]",
                border_style=risk_color,
            )
            console.print(panel)
            console.print()

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("approve")
@click.argument("request_id")
@click.option("--rationale", "-r", help="Reason for approval")
@click.option("--user", "-u", default="cli-user", help="User making the decision")
@click.pass_context
def approve(ctx, request_id: str, rationale: Optional[str], user: str):
    """Approve a pending request.

    REQUEST_ID is the ID of the approval request to approve.
    """
    try:
        from .core.logger import get_logger
        from .safety.approval import ApprovalSystem

        # Initialize approval system
        logger = get_logger()
        approval_system = ApprovalSystem(logger=logger)

        # Approve request
        success = approval_system.approve(
            request_id=request_id,
            decided_by=user,
            rationale=rationale or f"Approved via CLI by {user}",
        )

        if success:
            console.print(f"[green]✓[/green] Approved request: {request_id}")
            console.print(f"[green]✓[/green] Decided by: {user}")
            if rationale:
                console.print(f"[green]✓[/green] Rationale: {rationale}")
        else:
            console.print(
                f"[red]✗[/red] Failed to approve: Request not found or expired"
            )
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("deny")
@click.argument("request_id")
@click.option("--rationale", "-r", required=True, help="Reason for denial")
@click.option("--user", "-u", default="cli-user", help="User making the decision")
@click.pass_context
def deny(ctx, request_id: str, rationale: str, user: str):
    """Deny a pending request.

    REQUEST_ID is the ID of the approval request to deny.
    """
    try:
        from .core.logger import get_logger
        from .safety.approval import ApprovalSystem

        # Initialize approval system
        logger = get_logger()
        approval_system = ApprovalSystem(logger=logger)

        # Deny request
        success = approval_system.deny(
            request_id=request_id, decided_by=user, rationale=rationale
        )

        if success:
            console.print(f"[yellow]✓[/yellow] Denied request: {request_id}")
            console.print(f"[yellow]✓[/yellow] Decided by: {user}")
            console.print(f"[yellow]✓[/yellow] Rationale: {rationale}")
        else:
            console.print(f"[red]✗[/red] Failed to deny: Request not found or expired")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("approval-history")
@click.option("--limit", "-n", type=int, default=10, help="Number of records to show")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def approval_history(ctx, limit: int, json_output: bool):
    """Show approval decision history."""
    try:
        from .core.logger import get_logger
        from .safety.approval import ApprovalSystem

        # Initialize approval system
        logger = get_logger()
        approval_system = ApprovalSystem(logger=logger)

        # Get history
        history = approval_system.get_approval_history(limit=limit)

        if json_output:
            output = [decision.to_dict() for decision in history]
            print(json.dumps(output, indent=2))
            return

        if not history:
            console.print("[yellow]No approval history[/yellow]")
            return

        console.print(
            Panel.fit(f"Recent Approval Decisions (Last {limit})", style="bold blue")
        )

        # Create table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Request ID", style="cyan", width=30)
        table.add_column("Approved", justify="center", width=10)
        table.add_column("Risk", width=10)
        table.add_column("Decided By", width=15)
        table.add_column("Rationale", width=40)
        table.add_column("When", width=20)

        for decision in history:
            # Format approval status
            if decision.approved:
                if decision.auto_approved:
                    approval_text = "[green]✓ Auto[/green]"
                else:
                    approval_text = "[green]✓ Yes[/green]"
            else:
                approval_text = "[red]✗ No[/red]"

            # Format risk level
            risk_colors = {
                "low": "green",
                "medium": "yellow",
                "high": "orange1",
                "critical": "red",
            }
            risk_color = risk_colors.get(decision.risk_level.value, "white")
            risk_text = f"[{risk_color}]{decision.risk_level.value}[/{risk_color}]"

            # Format timestamp
            time_str = decision.decided_at.strftime("%Y-%m-%d %H:%M")

            # Truncate rationale if too long
            rationale = decision.rationale
            if len(rationale) > 40:
                rationale = rationale[:37] + "..."

            table.add_row(
                decision.request_id,
                approval_text,
                risk_text,
                decision.decided_by,
                rationale,
                time_str,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("analytics")
@click.option(
    "--days",
    type=int,
    default=30,
    help="Number of days to analyze (default: 30)",
)
@click.option(
    "--json-output",
    is_flag=True,
    help="Output as JSON",
)
@click.pass_context
def analytics(ctx, days: int, json_output: bool):
    """Display success/failure analytics and insights.

    Shows comprehensive analytics including:
    - Overall success rates
    - Issue processing statistics
    - PR management metrics
    - Cost analysis
    - Common errors and failure patterns
    - Optimization recommendations
    """
    try:
        # Initialize orchestrator to get analytics components
        orchestrator = Orchestrator(ctx.obj["config_path"])

        # Generate insights summary
        summary = orchestrator.insights_generator.generate_summary(days=days)

        if json_output:
            print(json.dumps(summary, indent=2, default=str))
            return

        console.print(
            Panel.fit(f"📈 Analytics Report ({days} days)", style="bold blue")
        )
        console.print()

        # Overall success rate
        console.print("[bold]Overall Performance:[/bold]")
        success_rate = summary["overall_success_rate"]
        success_color = (
            "green" if success_rate >= 80 else "yellow" if success_rate >= 60 else "red"
        )
        console.print(
            f"  Success Rate: [{success_color}]{success_rate:.1f}%[/{success_color}]"
        )
        console.print()

        # Operation counts
        if summary["operation_counts"]:
            console.print("[bold]Operation Counts:[/bold]")
            op_table = Table(show_header=False)
            op_table.add_column("Operation", style="cyan")
            op_table.add_column("Count", justify="right")

            for op_type, count in summary["operation_counts"].items():
                op_table.add_row(op_type, str(count))

            console.print(op_table)
            console.print()

        # Issue processing stats
        issue_stats = summary["issue_processing"]
        if issue_stats["total_issues"] > 0:
            console.print("[bold]Issue Processing:[/bold]")
            issue_table = Table(show_header=False)
            issue_table.add_column("Metric", style="cyan")
            issue_table.add_column("Value")

            issue_table.add_row("Total Issues", str(issue_stats["total_issues"]))
            issue_table.add_row(
                "Success Rate",
                f"[{'green' if issue_stats['success_rate'] >= 80 else 'yellow'}]{issue_stats['success_rate']:.1f}%[/]",
            )
            issue_table.add_row(
                "Avg Complexity", f"{issue_stats['avg_complexity']:.1f}"
            )
            issue_table.add_row(
                "Avg Files Changed", f"{issue_stats['avg_files_changed']:.1f}"
            )
            issue_table.add_row(
                "Avg Lines Added", f"{issue_stats['avg_lines_added']:.0f}"
            )
            issue_table.add_row(
                "Avg Tests Added", f"{issue_stats['avg_tests_added']:.1f}"
            )
            issue_table.add_row(
                "Avg Completion Time",
                f"{issue_stats['avg_completion_time'] / 60:.1f} minutes",
            )

            console.print(issue_table)
            console.print()

        # PR management stats
        pr_stats = summary["pr_management"]
        if pr_stats["total_prs"] > 0:
            console.print("[bold]PR Management:[/bold]")
            pr_table = Table(show_header=False)
            pr_table.add_column("Metric", style="cyan")
            pr_table.add_column("Value")

            pr_table.add_row("Total PRs", str(pr_stats["total_prs"]))
            pr_table.add_row("Merge Rate", f"{pr_stats['merge_rate']:.1f}%")
            pr_table.add_row("CI Pass Rate", f"{pr_stats['ci_pass_rate']:.1f}%")
            pr_table.add_row(
                "Avg Time to Merge",
                f"{pr_stats['avg_time_to_merge'] / 3600:.1f} hours",
            )
            pr_table.add_row("Avg CI Failures", f"{pr_stats['avg_ci_failures']:.1f}")

            console.print(pr_table)
            console.print()

        # Cost analysis
        cost_stats = summary["cost_analysis"]
        if cost_stats["total_cost"] > 0:
            console.print("[bold]Cost Analysis:[/bold]")
            cost_table = Table(show_header=False)
            cost_table.add_column("Metric", style="cyan")
            cost_table.add_column("Value")

            cost_table.add_row("Total Cost", f"${cost_stats['total_cost']:.2f}")
            cost_table.add_row("Total Tokens", f"{cost_stats['total_tokens']:,}")

            console.print(cost_table)

            if cost_stats["by_provider"]:
                console.print()
                provider_table = Table(title="Cost by Provider", show_header=True)
                provider_table.add_column("Provider", style="cyan")
                provider_table.add_column("Model")
                provider_table.add_column("Requests", justify="right")
                provider_table.add_column("Tokens", justify="right")
                provider_table.add_column("Cost", justify="right")

                for prov in cost_stats["by_provider"]:
                    provider_table.add_row(
                        prov["provider"],
                        prov["model"],
                        str(prov["request_count"]),
                        f"{prov['total_tokens']:,}",
                        f"${prov['total_cost']:.4f}",
                    )

                console.print(provider_table)
            console.print()

        # Common errors
        if summary["common_errors"]:
            console.print("[bold]Common Errors:[/bold]")
            error_table = Table(show_header=True)
            error_table.add_column("Error Type", style="red")
            error_table.add_column("Count", justify="right")
            error_table.add_column("Operation")

            for error in summary["common_errors"]:
                error_table.add_row(
                    error["error_type"],
                    str(error["count"]),
                    error["operation_type"],
                )

            console.print(error_table)
            console.print()

        # Get insights and recommendations
        console.print("[bold]Failure Patterns:[/bold]")
        patterns = orchestrator.insights_generator.identify_failure_patterns(days=days)
        if patterns:
            for pattern in patterns:
                console.print(f"  • [yellow]{pattern['pattern']}[/yellow]")
                console.print(f"    Recommendation: {pattern['recommendation']}")
        else:
            console.print("  [green]No significant failure patterns detected[/green]")
        console.print()

        console.print("[bold]Optimization Recommendations:[/bold]")
        recommendations = orchestrator.insights_generator.recommend_optimizations(
            days=days
        )
        if recommendations:
            for rec in recommendations:
                console.print(f"  • {rec}")
        else:
            console.print("  [green]System is operating optimally[/green]")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("db-stats")
@click.pass_context
def db_stats(ctx):
    """Show database statistics.

    Displays row counts for all analytics tables.
    """
    try:
        # Initialize orchestrator to get database
        orchestrator = Orchestrator(ctx.obj["config_path"])

        console.print(Panel.fit("🗄️  Database Statistics", style="bold blue"))
        console.print()

        stats = orchestrator.database.get_table_stats()

        table = Table(show_header=True)
        table.add_column("Table", style="cyan")
        table.add_column("Rows", justify="right")

        for table_name, count in stats.items():
            table.add_row(table_name, f"{count:,}")

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]", style="bold red")
        sys.exit(1)


@cli.command("dashboard")
@click.option(
    "--refresh",
    type=int,
    default=0,
    help="Auto-refresh interval in seconds (0 = no refresh)",
)
@click.pass_context
def dashboard(ctx, refresh: int):
    """Display performance dashboard with real-time metrics.

    Shows overview, activity, performance, costs, and current operations.
    Use --refresh N to auto-refresh every N seconds.
    """
    try:
        from .core.dashboard import Dashboard

        # Initialize orchestrator
        orchestrator = Orchestrator(ctx.obj["config_path"])

        # Create dashboard
        dash = Dashboard(
            database=orchestrator.database,
            analytics=orchestrator.analytics_collector,
            insights=orchestrator.insights_generator,
            cache_manager=getattr(orchestrator, "cache_manager", None),
            logger=orchestrator.logger,
        )

        if refresh > 0:
            import os
            import time

            console.print(
                f"[yellow]Auto-refreshing every {refresh} seconds. Press Ctrl+C to exit.[/yellow]"
            )
            try:
                while True:
                    # Clear screen
                    os.system("clear" if os.name == "posix" else "cls")

                    # Get and display metrics
                    metrics = dash.get_metrics()
                    dashboard_output = dash.format_cli(metrics)
                    console.print(dashboard_output)

                    time.sleep(refresh)
            except KeyboardInterrupt:
                console.print("\n[yellow]Dashboard stopped.[/yellow]")
        else:
            # Single display
            metrics = dash.get_metrics()
            dashboard_output = dash.format_cli(metrics)
            console.print(dashboard_output)

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


@cli.command("report")
@click.option("--days", type=int, default=7, help="Number of days to include in report")
@click.option("--detailed", is_flag=True, help="Generate detailed report")
@click.option(
    "--format",
    type=click.Choice(["json", "markdown"]),
    default="markdown",
    help="Output format",
)
@click.option("--output", type=str, help="Output file path (optional)")
@click.pass_context
def report(ctx, days: int, detailed: bool, format: str, output: str):
    """Generate performance report.

    Creates summary or detailed reports with metrics, costs, and insights.
    Can export to JSON or Markdown format.
    """
    try:
        from .core.reports import ReportGenerator

        # Initialize orchestrator
        orchestrator = Orchestrator(ctx.obj["config_path"])

        # Create report generator
        reporter = ReportGenerator(
            database=orchestrator.database,
            analytics=orchestrator.analytics_collector,
            insights=orchestrator.insights_generator,
            logger=orchestrator.logger,
        )

        console.print(
            f"[cyan]Generating {'detailed' if detailed else 'summary'} report for last {days} days...[/cyan]"
        )

        # Generate report
        if detailed:
            report_data = reporter.generate_detailed_report(days=days)
        else:
            report_data = reporter.generate_summary_report(days=days)

        # Export or display
        if output:
            if format == "json":
                reporter.export_json(report_data, output)
                console.print(f"[green]✓ Report exported to {output}[/green]")
            else:
                reporter.export_markdown(report_data, output)
                console.print(f"[green]✓ Report exported to {output}[/green]")
        else:
            # Display summary in console
            console.print(
                Panel.fit(
                    f"📊 {'Detailed' if detailed else 'Summary'} Report ({days} days)",
                    style="bold blue",
                )
            )
            console.print()

            # Overall metrics
            console.print("[bold]Overall Metrics:[/bold]")
            overall = report_data["overall"]
            console.print(f"  Success Rate: {overall['success_rate']:.1%}")
            console.print(f"  Total Operations: {overall['total_operations']}")
            console.print()

            # Costs
            console.print("[bold]Costs:[/bold]")
            costs = report_data["costs"]
            console.print(f"  Total Cost: ${costs['total_cost']:.2f}")
            console.print(
                f"  Avg per Operation: ${costs['avg_cost_per_operation']:.2f}"
            )
            console.print(f"  Total Tokens: {costs['total_tokens']:,}")
            console.print()

            # Issues
            console.print("[bold]Issues:[/bold]")
            issues = report_data["issues"]
            console.print(f"  Processed: {issues['total_processed']}")
            console.print(f"  Success Rate: {issues['success_rate']:.1%}")
            console.print()

            # PRs
            console.print("[bold]Pull Requests:[/bold]")
            prs = report_data["pull_requests"]
            console.print(f"  Created: {prs['total_created']}")
            console.print(f"  Merged: {prs['total_merged']}")
            console.print(f"  Merge Rate: {prs['merge_rate']:.1%}")
            console.print()

            if detailed and "detailed" in report_data:
                console.print("[bold]Top Issues:[/bold]")
                errors = report_data["detailed"].get("errors_by_type", {})
                for error_type, count in list(errors.items())[:5]:
                    console.print(f"  {error_type}: {count}")

            console.print()
            console.print("[dim]Use --output <file> to export full report[/dim]")

    except Exception as e:
        console.print(f"[red]✗ Error: {e}[/red]", style="bold red")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
