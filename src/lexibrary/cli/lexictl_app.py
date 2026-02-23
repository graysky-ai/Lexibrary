"""Maintenance CLI for Lexibrary — setup, design file generation, and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._shared import console, load_dotenv_if_configured, require_project_root

lexictl_app = typer.Typer(
    name="lexictl",
    help=(
        "Maintenance CLI for Lexibrary. "
        "Provides setup, design file generation, and validation for library management."
    ),
    no_args_is_help=True,
    callback=load_dotenv_if_configured,
)


# ---------------------------------------------------------------------------
# init — wizard-based project initialisation
# ---------------------------------------------------------------------------


@lexictl_app.command()
def init(
    *,
    defaults: Annotated[
        bool,
        typer.Option(
            "--defaults",
            help="Accept all detected defaults without prompting (for CI/scripting).",
        ),
    ] = False,
) -> None:
    """Initialize Lexibrary in a project. Runs the setup wizard."""
    import sys  # noqa: PLC0415

    from lexibrary.init.scaffolder import create_lexibrary_from_wizard  # noqa: PLC0415
    from lexibrary.init.wizard import run_wizard  # noqa: PLC0415

    project_root = Path.cwd()

    # Re-init guard
    if (project_root / ".lexibrary").exists():
        console.print(
            "[red]Project already initialised.[/red]"
            " Use [cyan]lexictl setup --update[/cyan] to modify settings."
        )
        raise typer.Exit(1)

    # Non-TTY detection
    if not defaults and not sys.stdin.isatty():
        console.print(
            "[red]Non-interactive environment detected.[/red]"
            " Use [cyan]lexictl init --defaults[/cyan] to run without prompts."
        )
        raise typer.Exit(1)

    # Show startup banner
    from lexibrary.cli.banner import render_banner  # noqa: PLC0415

    render_banner(console)

    # Run wizard
    answers = run_wizard(project_root, console, use_defaults=defaults)

    if answers is None:
        console.print("[yellow]Init cancelled.[/yellow]")
        raise typer.Exit(1)

    # Create skeleton from wizard answers
    created = create_lexibrary_from_wizard(project_root, answers)
    console.print(f"[green]Created .lexibrary/ skeleton[/green] ({len(created)} items)")

    # Generate agent rule files for selected environments
    if answers.agent_environments:
        from lexibrary.init.rules import generate_rules, supported_environments  # noqa: PLC0415

        # Filter to only supported environments (user may have typed an unsupported name)
        supported = supported_environments()
        valid_envs = [e for e in answers.agent_environments if e in supported]
        if valid_envs:
            results = generate_rules(project_root, valid_envs)
            for env_name, paths in results.items():
                console.print(f"  [green]{env_name}:[/green] {len(paths)} rule file(s) created")
                for p in paths:
                    rel = p.relative_to(project_root)
                    console.print(f"    [dim]{rel}[/dim]")

    console.print("[dim]Run [cyan]lexictl update[/cyan] to generate design files.[/dim]")


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@lexictl_app.command()
def update(
    path: Annotated[
        Path | None,
        typer.Argument(help="File or directory to update. Omit to update entire project."),
    ] = None,
    *,
    changed_only: Annotated[
        list[Path] | None,
        typer.Option(
            "--changed-only",
            help="Only update the specified files (for git hooks / CI).",
        ),
    ] = None,
) -> None:
    """Re-index changed files and regenerate design files."""
    import asyncio  # noqa: PLC0415

    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn  # noqa: PLC0415

    from lexibrary.archivist.pipeline import (  # noqa: PLC0415
        UpdateStats,
        update_file,
        update_files,
        update_project,
    )
    from lexibrary.archivist.service import ArchivistService  # noqa: PLC0415
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

    # Mutual exclusivity check
    if path is not None and changed_only is not None:
        console.print(
            "[red]Error:[/red] [cyan]path[/cyan] and [cyan]--changed-only[/cyan]"
            " are mutually exclusive. Use one or the other."
        )
        raise typer.Exit(1)

    project_root = require_project_root()
    config = load_config(project_root)
    rate_limiter = RateLimiter()
    archivist = ArchivistService(rate_limiter=rate_limiter, config=config.llm)

    # --changed-only: batch update specific files
    if changed_only is not None:
        resolved_paths = [p.resolve() for p in changed_only]
        console.print(f"Updating [cyan]{len(resolved_paths)}[/cyan] changed file(s)...")

        stats = asyncio.run(update_files(resolved_paths, project_root, config, archivist))

        console.print()
        console.print("[bold]Update summary:[/bold]")
        console.print(f"  Files scanned:       {stats.files_scanned}")
        console.print(f"  Files unchanged:     {stats.files_unchanged}")
        console.print(f"  Files created:       {stats.files_created}")
        console.print(f"  Files updated:       {stats.files_updated}")
        console.print(f"  Files agent-updated: {stats.files_agent_updated}")
        if stats.files_failed:
            console.print(f"  [red]Files failed:       {stats.files_failed}[/red]")

        if stats.files_failed:
            raise typer.Exit(1)
        return

    if path is not None:
        target = Path(path).resolve()

        # Validate target exists
        if not target.exists():
            console.print(f"[red]Path not found:[/red] {path}")
            raise typer.Exit(1)

        # Validate target is within project root
        try:
            target.relative_to(project_root)
        except ValueError:
            console.print(
                f"[red]Path is outside the project root:[/red] {path}\nProject root: {project_root}"
            )
            raise typer.Exit(1) from None

        if target.is_file():
            # Single file update
            console.print(f"Updating design file for [cyan]{path}[/cyan]...")
            result = asyncio.run(update_file(target, project_root, config, archivist))
            if result.failed:
                console.print(f"[red]Failed[/red] to update design file for {path}")
                raise typer.Exit(1)
            console.print(f"[green]Done.[/green] Change level: {result.change.value}")
            return

        # Directory update -- update all files in subtree
        # Delegate to update_project but the scope is effectively the whole project;
        # the pipeline already filters by scope_root. We run the full pipeline.
        # For directory-scoped updates we run update_project (it respects scope_root).

    # Project or directory update with progress bar
    stats = UpdateStats()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Updating design files...", total=None)

        def _progress_callback(file_path: Path, change_level: object) -> None:
            progress.update(
                task,
                advance=1,
                description=f"Processing {file_path.name}",
            )

        stats = asyncio.run(
            update_project(project_root, config, archivist, progress_callback=_progress_callback)
        )

    if stats.start_here_failed:
        console.print("[red]Failed to regenerate START_HERE.md.[/red]")
    else:
        console.print("[green]START_HERE.md regenerated.[/green]")

    # Print summary stats
    console.print()
    console.print("[bold]Update summary:[/bold]")
    console.print(f"  Files scanned:       {stats.files_scanned}")
    console.print(f"  Files unchanged:     {stats.files_unchanged}")
    console.print(f"  Files created:       {stats.files_created}")
    console.print(f"  Files updated:       {stats.files_updated}")
    console.print(f"  Files agent-updated: {stats.files_agent_updated}")
    if stats.files_failed:
        console.print(f"  [red]Files failed:       {stats.files_failed}[/red]")
    if stats.aindex_refreshed:
        console.print(f"  .aindex refreshed:   {stats.aindex_refreshed}")
    if stats.token_budget_warnings:
        console.print(f"  [yellow]Token budget warnings: {stats.token_budget_warnings}[/yellow]")

    if stats.files_failed:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@lexictl_app.command()
def validate(
    *,
    severity: Annotated[
        str | None,
        typer.Option(
            "--severity",
            help="Minimum severity to report: error, warning, or info.",
        ),
    ] = None,
    check: Annotated[
        str | None,
        typer.Option(
            "--check",
            help="Run only the named check (see available checks below).",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Output results as JSON instead of Rich tables.",
        ),
    ] = False,
) -> None:
    """Run consistency checks on the library."""
    import json as _json  # noqa: PLC0415

    from lexibrary.validator import AVAILABLE_CHECKS, validate_library  # noqa: PLC0415

    project_root = require_project_root()
    lexibrary_dir = project_root / ".lexibrary"

    try:
        report = validate_library(
            project_root,
            lexibrary_dir,
            severity_filter=severity,
            check_filter=check,
        )
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        # Show available checks if an unknown check was requested
        if check is not None and check not in AVAILABLE_CHECKS:
            console.print("[dim]Available checks:[/dim] " + ", ".join(sorted(AVAILABLE_CHECKS)))
        raise typer.Exit(1) from None

    if json_output:
        console.print(_json.dumps(report.to_dict(), indent=2))
    else:
        report.render(console)

    raise typer.Exit(report.exit_code())


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@lexictl_app.command()
def status(
    path: Annotated[
        Path | None,
        typer.Argument(help="Project directory to check."),
    ] = None,
    *,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Single-line output for hooks/CI."),
    ] = False,
) -> None:
    """Show library health and staleness summary."""
    import hashlib  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file_metadata,
    )
    from lexibrary.linkgraph.health import read_index_health  # noqa: PLC0415
    from lexibrary.stack.parser import parse_stack_post  # noqa: PLC0415
    from lexibrary.validator import validate_library  # noqa: PLC0415
    from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

    project_root = require_project_root()
    lexibrary_dir = project_root / ".lexibrary"

    # --- Artifact counts ---
    # Design files: count .md files in the mirror tree (exclude concepts/ and stack/)
    design_dir = lexibrary_dir
    design_files: list[Path] = []
    stale_count = 0
    latest_generated: datetime | None = None

    for md_path in sorted(design_dir.rglob("*.md")):
        # Skip non-design-file directories
        rel = md_path.relative_to(lexibrary_dir)
        rel_parts = rel.parts
        if rel_parts[0] in ("concepts", "stack"):
            continue
        # Skip known non-design files
        if md_path.name in ("START_HERE.md", "HANDOFF.md"):
            continue
        meta = parse_design_file_metadata(md_path)
        if meta is not None:
            design_files.append(md_path)
            # Check staleness via source hash
            source_path = project_root / meta.source
            if source_path.exists():
                current_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
                if current_hash != meta.source_hash:
                    stale_count += 1
            # Track latest generated timestamp
            if latest_generated is None or meta.generated > latest_generated:
                latest_generated = meta.generated

    total_designs = len(design_files)

    # Concepts: count by status
    concepts_dir = lexibrary_dir / "concepts"
    concept_counts: dict[str, int] = {"active": 0, "deprecated": 0, "draft": 0}
    if concepts_dir.is_dir():
        for md_path in sorted(concepts_dir.glob("*.md")):
            concept = parse_concept_file(md_path)
            if concept is not None:
                s = concept.frontmatter.status
                if s in concept_counts:
                    concept_counts[s] += 1

    # Stack posts: count by status
    stack_dir = lexibrary_dir / "stack"
    stack_counts: dict[str, int] = {"open": 0, "resolved": 0}
    if stack_dir.is_dir():
        for md_path in sorted(stack_dir.glob("ST-*-*.md")):
            post = parse_stack_post(md_path)
            if post is not None:
                st = post.frontmatter.status
                if st in stack_counts:
                    stack_counts[st] += 1
                else:
                    stack_counts[st] = 1

    total_stack = sum(stack_counts.values())

    # --- Lightweight validation (errors + warnings only) ---
    report = validate_library(
        project_root,
        lexibrary_dir,
        severity_filter="warning",
    )
    error_count = report.summary.error_count
    warning_count = report.summary.warning_count

    # --- Quiet mode ---
    if quiet:
        if error_count > 0 and warning_count > 0:
            parts: list[str] = []
            parts.append(f"{error_count} error{'s' if error_count != 1 else ''}")
            parts.append(f"{warning_count} warning{'s' if warning_count != 1 else ''}")
            console.print("lexictl: " + ", ".join(parts) + " \u2014 run `lexictl validate`")
        elif error_count > 0:
            console.print(
                f"lexictl: {error_count} error{'s' if error_count != 1 else ''}"
                " \u2014 run `lexictl validate`"
            )
        elif warning_count > 0:
            console.print(
                f"lexictl: {warning_count} warning{'s' if warning_count != 1 else ''}"
                " \u2014 run `lexictl validate`"
            )
        else:
            console.print("lexictl: library healthy")
        raise typer.Exit(report.exit_code())

    # --- Full dashboard ---
    console.print()
    console.print("[bold]Lexibrary Status[/bold]")
    console.print()

    # Files
    if stale_count > 0:
        console.print(f"  Files: {total_designs} tracked, {stale_count} stale")
    else:
        console.print(f"  Files: {total_designs} tracked")

    # Concepts
    concept_parts: list[str] = []
    if concept_counts["active"] > 0:
        concept_parts.append(f"{concept_counts['active']} active")
    if concept_counts["deprecated"] > 0:
        concept_parts.append(f"{concept_counts['deprecated']} deprecated")
    if concept_counts["draft"] > 0:
        concept_parts.append(f"{concept_counts['draft']} draft")
    if concept_parts:
        console.print("  Concepts: " + ", ".join(concept_parts))
    else:
        console.print("  Concepts: 0")

    # Stack
    if total_stack > 0:
        console.print(
            f"  Stack: {total_stack} post{'s' if total_stack != 1 else ''}"
            f" ({stack_counts.get('resolved', 0)} resolved,"
            f" {stack_counts.get('open', 0)} open)"
        )
    else:
        console.print("  Stack: 0 posts")

    # Link graph health
    index_health = read_index_health(project_root)
    if index_health.artifact_count is not None:
        built_part = f" (built {index_health.built_at})" if index_health.built_at else ""
        console.print(
            f"  Link graph: {index_health.artifact_count} artifact"
            f"{'s' if index_health.artifact_count != 1 else ''}"
            f", {index_health.link_count} link"
            f"{'s' if index_health.link_count != 1 else ''}"
            f"{built_part}"
        )
    else:
        console.print("  Link graph: not built (run lexictl update to create)")

    console.print()

    # Issues
    console.print(
        f"  Issues: {error_count} error{'s' if error_count != 1 else ''},"
        f" {warning_count} warning{'s' if warning_count != 1 else ''}"
    )

    # Last updated
    if latest_generated is not None:
        now = datetime.now(tz=UTC)
        gen = latest_generated
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=UTC)
        delta = now - gen
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            time_str = f"{total_seconds} second{'s' if total_seconds != 1 else ''} ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            time_str = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            time_str = f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = total_seconds // 86400
            time_str = f"{days} day{'s' if days != 1 else ''} ago"
        console.print(f"  Updated: {time_str}")
    else:
        console.print("  Updated: never")

    console.print()

    # Suggest validate if issues exist
    if error_count > 0 or warning_count > 0:
        console.print("Run `lexictl validate` for details.")

    raise typer.Exit(report.exit_code())


# ---------------------------------------------------------------------------
# setup / sweep / daemon
# ---------------------------------------------------------------------------


@lexictl_app.command()
def setup(
    *,
    update_flag: Annotated[
        bool,
        typer.Option("--update", help="Update existing agent rules."),
    ] = False,
    env: Annotated[
        list[str] | None,
        typer.Option("--env", help="Explicit environment(s) to generate rules for."),
    ] = None,
    hooks: Annotated[
        bool,
        typer.Option("--hooks", help="Install the git post-commit hook for automatic updates."),
    ] = False,
) -> None:
    """Install or update agent environment rules."""
    if hooks:
        from lexibrary.hooks.post_commit import install_post_commit_hook  # noqa: PLC0415

        project_root = require_project_root()
        result = install_post_commit_hook(project_root)
        if result.no_git_dir:
            console.print(f"[red]{result.message}[/red]")
            raise typer.Exit(1)
        if result.already_installed:
            console.print(f"[yellow]{result.message}[/yellow]")
        else:
            console.print(f"[green]{result.message}[/green]")
        return

    if not update_flag:
        console.print(
            "Usage:\n"
            "  [cyan]lexictl setup --update[/cyan]  "
            "Update agent rules for configured environments\n"
            "  [cyan]lexictl init[/cyan]             "
            "Initialise a new Lexibrary project"
        )
        raise typer.Exit(0)

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.init.rules import generate_rules, supported_environments  # noqa: PLC0415
    from lexibrary.iwh.gitignore import ensure_iwh_gitignored  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    # Determine which environments to generate for
    environments = list(env) if env else list(config.agent_environment)

    if not environments:
        console.print(
            "[yellow]No agent environments configured.[/yellow]"
            " Run [cyan]lexictl init[/cyan] to set up agent environments."
        )
        raise typer.Exit(1)

    # Validate environment names before generating
    supported = supported_environments()
    unsupported = [e for e in environments if e not in supported]
    if unsupported:
        console.print(
            f"[red]Unsupported environment(s):[/red] {', '.join(sorted(unsupported))}\n"
            f"Supported: {', '.join(supported)}"
        )
        raise typer.Exit(1)

    # Generate rules for each environment
    results = generate_rules(project_root, environments)

    for env_name, paths in results.items():
        console.print(f"  [green]{env_name}:[/green] {len(paths)} file(s) written")
        for p in paths:
            rel = p.relative_to(project_root)
            console.print(f"    [dim]{rel}[/dim]")

    # Ensure IWH files are gitignored
    iwh_modified = ensure_iwh_gitignored(project_root)
    if iwh_modified:
        console.print("  [green].gitignore:[/green] added IWH pattern")

    total_files = sum(len(paths) for paths in results.values())
    console.print(f"\n[green]Setup complete.[/green] {total_files} rule file(s) updated.")


@lexictl_app.command()
def sweep(
    *,
    watch: Annotated[
        bool,
        typer.Option("--watch", help="Run periodic sweeps in the foreground until interrupted."),
    ] = False,
) -> None:
    """Run a library update sweep (one-shot or watch mode)."""
    from lexibrary.daemon.service import DaemonService  # noqa: PLC0415

    project_root = require_project_root()
    svc = DaemonService(project_root)

    if watch:
        svc.run_watch()
    else:
        svc.run_once()


@lexictl_app.command()
def daemon(
    action: Annotated[
        str | None,
        typer.Argument(help="Action to perform: start, stop, or status."),
    ] = None,
) -> None:
    """Manage the watchdog daemon (deprecated -- prefer 'sweep')."""
    import os  # noqa: PLC0415
    import signal as _signal  # noqa: PLC0415

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.daemon.service import DaemonService  # noqa: PLC0415

    project_root = require_project_root()
    resolved_action = action or "start"
    valid_actions = ("start", "stop", "status")

    if resolved_action not in valid_actions:
        console.print(
            f"[red]Unknown action:[/red] {resolved_action}\n"
            f"Valid actions: {', '.join(valid_actions)}"
        )
        raise typer.Exit(1)

    pid_path = project_root / ".lexibrary" / "daemon.pid"

    if resolved_action == "start":
        config = load_config(project_root)
        if not config.daemon.watchdog_enabled:
            console.print(
                "[yellow]Watchdog mode is disabled in config.[/yellow]\n"
                "Use [cyan]lexictl sweep --watch[/cyan] for periodic sweeps, "
                "or set [cyan]daemon.watchdog_enabled: true[/cyan] in config."
            )
            return
        svc = DaemonService(project_root)
        svc.run_watchdog()

    elif resolved_action == "stop":
        if not pid_path.exists():
            console.print("[yellow]No daemon is running (no PID file found).[/yellow]")
            return
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            console.print("[red]Cannot read PID file.[/red]")
            pid_path.unlink(missing_ok=True)
            raise typer.Exit(1) from None

        try:
            os.kill(pid, _signal.SIGTERM)
            console.print(f"[green]Sent SIGTERM to daemon (PID {pid}).[/green]")
        except ProcessLookupError:
            console.print(
                f"[yellow]Process {pid} not found -- cleaning up stale PID file.[/yellow]"
            )
            pid_path.unlink(missing_ok=True)
        except PermissionError:
            console.print(f"[red]Permission denied sending signal to PID {pid}.[/red]")
            raise typer.Exit(1) from None

    elif resolved_action == "status":
        if not pid_path.exists():
            console.print("[dim]No daemon is running.[/dim]")
            return
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            console.print("[red]Cannot read PID file.[/red]")
            pid_path.unlink(missing_ok=True)
            raise typer.Exit(1) from None

        # Check if process is still running
        try:
            os.kill(pid, 0)
            console.print(f"[green]Daemon is running[/green] (PID {pid}).")
        except ProcessLookupError:
            console.print(
                f"[yellow]Stale PID file found (PID {pid} is not running).[/yellow] Cleaning up."
            )
            pid_path.unlink(missing_ok=True)
        except PermissionError:
            # Process exists but we can't signal it -- it's running
            console.print(f"[green]Daemon is running[/green] (PID {pid}).")
