"""Maintenance CLI for Lexibrary — setup, design file generation, and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._shared import (
    _run_status,
    _run_validate,
    console,
    load_dotenv_if_configured,
    require_project_root,
)

lexictl_app = typer.Typer(
    name="lexictl",
    help=(
        "Maintenance CLI for Lexibrary. "
        "Provides setup, design file generation, and validation for library management."
    ),
    no_args_is_help=True,
    callback=load_dotenv_if_configured,
)

iwh_ctl_app = typer.Typer(help="IWH signal maintenance commands.")
lexictl_app.add_typer(iwh_ctl_app, name="iwh")


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

    # Install git hooks if user opted in
    if answers.install_hooks:
        from lexibrary.hooks.post_commit import install_post_commit_hook  # noqa: PLC0415
        from lexibrary.hooks.pre_commit import install_pre_commit_hook  # noqa: PLC0415

        post_result = install_post_commit_hook(project_root)
        if post_result.no_git_dir or post_result.already_installed:
            console.print(f"[yellow]{post_result.message}[/yellow]")
        else:
            console.print(f"[green]{post_result.message}[/green]")

        pre_result = install_pre_commit_hook(project_root)
        if pre_result.no_git_dir or pre_result.already_installed:
            console.print(f"[yellow]{pre_result.message}[/yellow]")
        else:
            console.print(f"[green]{pre_result.message}[/green]")

    # Post-init: offer to run lexictl update (skip in defaults mode)
    if not defaults:
        from rich.prompt import Confirm as _Confirm  # noqa: PLC0415

        run_update = _Confirm.ask(
            "\nRun [cyan]lexictl update[/cyan] now to generate design files?",
            default=False,
            console=console,
        )
        if run_update:
            console.print("[dim]Running lexictl update...[/dim]")
            import asyncio  # noqa: PLC0415

            from lexibrary.archivist.pipeline import update_project  # noqa: PLC0415
            from lexibrary.archivist.service import ArchivistService  # noqa: PLC0415
            from lexibrary.config.loader import load_config  # noqa: PLC0415
            from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

            config = load_config(project_root)
            rate_limiter = RateLimiter()
            archivist = ArchivistService(rate_limiter=rate_limiter, config=config.llm)
            stats = asyncio.run(update_project(project_root, config, archivist))
            console.print(
                f"[green]Update complete.[/green] "
                f"{stats.files_scanned} files scanned, "
                f"{stats.files_created} created, "
                f"{stats.files_updated} updated."
            )
        else:
            console.print(
                "[dim]Run [cyan]lexictl update[/cyan] later to generate design files.[/dim]"
            )
    else:
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
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview which files would change without making any modifications.",
        ),
    ] = False,
    start_here: Annotated[
        bool,
        typer.Option(
            "--start-here",
            help="Regenerate TOPOLOGY.md only, without running the full update.",
        ),
    ] = False,
) -> None:
    """Re-index changed files and regenerate design files."""
    import asyncio  # noqa: PLC0415

    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn  # noqa: PLC0415

    from lexibrary.archivist.pipeline import (  # noqa: PLC0415
        UpdateStats,
        dry_run_files,
        dry_run_project,
        update_file,
        update_files,
        update_project,
    )
    from lexibrary.archivist.service import ArchivistService  # noqa: PLC0415
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

    # Mutual exclusivity checks
    if path is not None and changed_only is not None:
        console.print(
            "[red]Error:[/red] [cyan]path[/cyan] and [cyan]--changed-only[/cyan]"
            " are mutually exclusive. Use one or the other."
        )
        raise typer.Exit(1)

    if start_here and (changed_only is not None or path is not None):
        console.print(
            "[red]Error:[/red] [cyan]--start-here[/cyan] cannot be combined with"
            " [cyan]path[/cyan] or [cyan]--changed-only[/cyan]."
        )
        raise typer.Exit(1)

    project_root = require_project_root()
    config = load_config(project_root)

    # --start-here: regenerate TOPOLOGY.md only
    if start_here:
        from lexibrary.archivist.topology import generate_topology  # noqa: PLC0415

        try:
            generate_topology(project_root)
            console.print("[green]TOPOLOGY.md generated.[/green]")
        except Exception as exc:
            console.print(f"[red]Failed to generate TOPOLOGY.md:[/red] {exc}")
            raise typer.Exit(1) from None
        return

    # --dry-run: preview changes without modifications
    if dry_run:
        console.print("[yellow]DRY-RUN MODE -- no files will be modified[/yellow]")
        console.print()

        if changed_only is not None:
            resolved_paths = [p.resolve() for p in changed_only]
            results = asyncio.run(dry_run_files(resolved_paths, project_root, config))
        else:
            results = asyncio.run(dry_run_project(project_root, config))

        if not results:
            console.print("[dim]No files would change.[/dim]")
            return

        # Display results
        counts: dict[str, int] = {}
        for file_path, change_level in results:
            label = change_level.value.upper()
            counts[label] = counts.get(label, 0) + 1
            rel_path = file_path.relative_to(project_root)
            console.print(f"  [cyan]{label:<20}[/cyan] {rel_path}")

        # Summary
        console.print()
        total = len(results)
        parts = [f"{total} file{'s' if total != 1 else ''}"]
        for label, count in sorted(counts.items()):
            parts.append(f"{count} {label.lower()}")
        console.print("[bold]Summary:[/bold] " + ", ".join(parts))
        return

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

        if stats.error_summary.has_errors():
            from lexibrary.errors import format_error_summary  # noqa: PLC0415

            format_error_summary(stats.error_summary, console)

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

    if stats.topology_failed:
        console.print("[red]Failed to generate TOPOLOGY.md.[/red]")
    else:
        console.print("[green]TOPOLOGY.md generated.[/green]")

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

    if stats.error_summary.has_errors():
        from lexibrary.errors import format_error_summary  # noqa: PLC0415

        format_error_summary(stats.error_summary, console)

    if stats.files_failed:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


@lexictl_app.command()
def index(
    directory: Annotated[
        Path,
        typer.Argument(help="Directory to index."),
    ] = Path("."),
    *,
    recursive: Annotated[
        bool,
        typer.Option("-r", "--recursive", help="Recursively index all directories."),
    ] = False,
) -> None:
    """Generate .aindex file(s) for a directory."""
    from rich.progress import Progress, SpinnerColumn, TextColumn  # noqa: PLC0415

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.indexer.orchestrator import index_directory, index_recursive  # noqa: PLC0415

    project_root = require_project_root()

    # Resolve directory relative to cwd
    target = Path(directory).resolve()

    # Validate directory exists
    if not target.exists():
        console.print(f"[red]Directory not found:[/red] {directory}")
        raise typer.Exit(1)

    if not target.is_dir():
        console.print(f"[red]Not a directory:[/red] {directory}")
        raise typer.Exit(1)

    # Validate directory is within project root
    try:
        target.relative_to(project_root)
    except ValueError:
        console.print(
            f"[red]Directory is outside the project root:[/red] {directory}\n"
            f"Project root: {project_root}"
        )
        raise typer.Exit(1) from None

    config = load_config(project_root)

    if recursive:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Indexing...", total=None)

            def _progress_callback(current: int, total: int, name: str) -> None:
                progress.update(task, description=f"Indexing [{current}/{total}] {name}")

            stats = index_recursive(
                target, project_root, config, progress_callback=_progress_callback
            )

        console.print(
            f"\n[green]Indexing complete.[/green] "
            f"{stats.directories_indexed} directories indexed, "
            f"{stats.files_found} files found"
            + (f", [red]{stats.errors} errors[/red]" if stats.errors else "")
            + "."
        )

        if stats.error_summary.has_errors():
            from lexibrary.errors import format_error_summary  # noqa: PLC0415

            format_error_summary(stats.error_summary, console)
    else:
        output_path = index_directory(target, project_root, config)
        console.print(f"[green]Wrote[/green] {output_path}")


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
    ci: Annotated[
        bool,
        typer.Option(
            "--ci",
            help="Compact single-line output for CI pipelines.",
        ),
    ] = False,
    fix: Annotated[
        bool,
        typer.Option(
            "--fix",
            help="Auto-fix fixable issues after validation.",
        ),
    ] = False,
) -> None:
    """Run consistency checks on the library."""
    project_root = require_project_root()
    exit_code = _run_validate(
        project_root,
        severity=severity,
        check=check,
        json_output=json_output,
        ci_mode=ci,
        fix=fix,
    )
    raise typer.Exit(exit_code)


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
    project_root = require_project_root()
    exit_code = _run_status(
        project_root, path=path, quiet=quiet, cli_prefix="lexictl"
    )
    raise typer.Exit(exit_code)


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
        typer.Option(
            "--hooks",
            help="Install git hooks (post-commit auto-update, pre-commit validation).",
        ),
    ] = False,
) -> None:
    """Install or update agent environment rules."""
    if hooks:
        from lexibrary.hooks.post_commit import install_post_commit_hook  # noqa: PLC0415
        from lexibrary.hooks.pre_commit import install_pre_commit_hook  # noqa: PLC0415

        project_root = require_project_root()

        # Install post-commit hook
        post_result = install_post_commit_hook(project_root)
        if post_result.no_git_dir:
            console.print(f"[red]{post_result.message}[/red]")
            raise typer.Exit(1)
        if post_result.already_installed:
            console.print(f"[yellow]{post_result.message}[/yellow]")
        else:
            console.print(f"[green]{post_result.message}[/green]")

        # Install pre-commit hook
        pre_result = install_pre_commit_hook(project_root)
        if pre_result.no_git_dir:
            console.print(f"[red]{pre_result.message}[/red]")
            raise typer.Exit(1)
        if pre_result.already_installed:
            console.print(f"[yellow]{pre_result.message}[/yellow]")
        else:
            console.print(f"[green]{pre_result.message}[/green]")
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


# ---------------------------------------------------------------------------
# iwh clean
# ---------------------------------------------------------------------------


@iwh_ctl_app.command("clean")
def iwh_clean(
    *,
    older_than: Annotated[
        int | None,
        typer.Option("--older-than", help="Only remove signals older than N hours."),
    ] = None,
) -> None:
    """Remove all IWH signal files from the project."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.iwh.reader import IWH_FILENAME, find_all_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    project_root = require_project_root()
    results = find_all_iwh(project_root)

    if not results:
        console.print("[dim]No IWH signals to clean.[/dim]")
        return

    now = datetime.now(tz=UTC)
    removed = 0
    for source_dir, iwh in results:
        if older_than is not None:
            created = iwh.created
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            age_hours = (now - created).total_seconds() / 3600
            if age_hours < older_than:
                continue

        iwh_file = project_root / LEXIBRARY_DIR / source_dir / IWH_FILENAME
        if iwh_file.exists():
            iwh_file.unlink()
            display_dir = f"{source_dir}/" if str(source_dir) != "." else "./"
            console.print(f"  [red]Removed[/red] {display_dir} ({iwh.scope})")
            removed += 1

    console.print(f"\n[green]Cleaned[/green] {removed} signal(s)")
