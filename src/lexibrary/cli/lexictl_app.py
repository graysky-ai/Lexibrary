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
    topology: Annotated[
        bool,
        typer.Option(
            "--topology",
            help="Regenerate TOPOLOGY.md only, without running the full update.",
        ),
    ] = False,
    skeleton: Annotated[
        bool,
        typer.Option(
            "--skeleton",
            help=(
                "Generate a skeleton design file without LLM enrichment. "
                "Requires a single file path argument. Used by PostToolUse hooks."
            ),
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

    # Mutual exclusivity checks — skeleton first (it subsumes the path argument)
    if skeleton and (changed_only is not None or topology or dry_run):
        console.print(
            "[red]Error:[/red] [cyan]--skeleton[/cyan] cannot be combined with"
            " [cyan]--changed-only[/cyan], [cyan]--topology[/cyan],"
            " or [cyan]--dry-run[/cyan]."
        )
        raise typer.Exit(1)

    if skeleton and path is None:
        console.print(
            "[red]Error:[/red] [cyan]--skeleton[/cyan] requires a file path argument."
        )
        raise typer.Exit(1)

    if path is not None and changed_only is not None:
        console.print(
            "[red]Error:[/red] [cyan]path[/cyan] and [cyan]--changed-only[/cyan]"
            " are mutually exclusive. Use one or the other."
        )
        raise typer.Exit(1)

    if topology and (changed_only is not None or path is not None):
        console.print(
            "[red]Error:[/red] [cyan]--topology[/cyan] cannot be combined with"
            " [cyan]path[/cyan] or [cyan]--changed-only[/cyan]."
        )
        raise typer.Exit(1)

    project_root = require_project_root()
    config = load_config(project_root)

    # --skeleton: quick skeleton design file without LLM enrichment
    if skeleton:
        from lexibrary.lifecycle.bootstrap import _generate_quick_design  # noqa: PLC0415
        from lexibrary.lifecycle.queue import queue_for_enrichment  # noqa: PLC0415

        target = Path(path).resolve()  # type: ignore[arg-type]

        if not target.exists():
            console.print(f"[red]File not found:[/red] {path}")
            raise typer.Exit(1)

        if not target.is_file():
            console.print(f"[red]Not a file:[/red] {path}")
            raise typer.Exit(1)

        try:
            result = _generate_quick_design(target, project_root)
        except Exception as exc:
            console.print(f"[red]Failed to generate skeleton:[/red] {exc}")
            raise typer.Exit(1) from None

        # Queue for later LLM enrichment
        queue_for_enrichment(project_root, target)

        console.print(
            f"[green]Skeleton generated.[/green] Change level: {result.change.value}"
        )
        return

    # --topology: regenerate TOPOLOGY.md only
    if topology:
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

    # Deprecation lifecycle stats
    has_lifecycle = (
        stats.designs_deprecated
        + stats.designs_unlinked
        + stats.designs_deleted_ttl
        + stats.concepts_deleted_ttl
        + stats.concepts_skipped_referenced
        + stats.conventions_deleted_ttl
        + stats.renames_detected
        + stats.renames_migrated
    ) > 0
    if has_lifecycle:
        console.print()
        console.print("[bold]Lifecycle:[/bold]")
        if stats.renames_detected:
            console.print(f"  Renames detected:    {stats.renames_detected}")
        if stats.renames_migrated:
            console.print(f"  Renames migrated:    {stats.renames_migrated}")
        if stats.designs_deprecated:
            console.print(f"  Designs deprecated:  {stats.designs_deprecated}")
        if stats.designs_unlinked:
            console.print(f"  Designs unlinked:    {stats.designs_unlinked}")
        if stats.designs_deleted_ttl:
            console.print(
                f"  [yellow]Designs TTL-deleted: {stats.designs_deleted_ttl}[/yellow]"
            )
        if stats.concepts_deleted_ttl:
            console.print(
                f"  [yellow]Concepts TTL-deleted: {stats.concepts_deleted_ttl}[/yellow]"
            )
        if stats.concepts_skipped_referenced:
            console.print(
                f"  Concepts skipped (referenced): {stats.concepts_skipped_referenced}"
            )
        if stats.conventions_deleted_ttl:
            console.print(
                f"  [yellow]Conventions TTL-deleted: {stats.conventions_deleted_ttl}[/yellow]"
            )

    # Enrichment queue stats
    has_queue = (stats.queue_processed + stats.queue_failed + stats.queue_remaining) > 0
    if has_queue:
        console.print()
        console.print("[bold]Enrichment queue:[/bold]")
        if stats.queue_processed:
            console.print(f"  Enriched:            {stats.queue_processed}")
        if stats.queue_failed:
            console.print(f"  [red]Failed:             {stats.queue_failed}[/red]")
        if stats.queue_remaining:
            console.print(f"  Remaining:           {stats.queue_remaining}")

    if stats.error_summary.has_errors():
        from lexibrary.errors import format_error_summary  # noqa: PLC0415

        format_error_summary(stats.error_summary, console)

    # Run IWH cleanup on full project update (no path / no --changed-only)
    if path is None and changed_only is None:
        from lexibrary.iwh.cleanup import iwh_cleanup  # noqa: PLC0415

        cleanup = iwh_cleanup(project_root, config.iwh.ttl_hours)
        total_cleaned = len(cleanup.expired) + len(cleanup.orphaned)
        if total_cleaned > 0:
            console.print()
            console.print("[bold]IWH cleanup:[/bold]")
            if cleanup.expired:
                console.print(f"  Expired:  {len(cleanup.expired)} signal(s) removed")
            if cleanup.orphaned:
                console.print(f"  Orphaned: {len(cleanup.orphaned)} signal(s) removed")
            if cleanup.kept > 0:
                console.print(f"  Kept:     {cleanup.kept} signal(s)")

    if stats.files_failed:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------


@lexictl_app.command()
def bootstrap(
    *,
    scope: Annotated[
        str | None,
        typer.Option(
            "--scope",
            help="Override the scope root from config (directory relative to project root).",
        ),
    ] = None,
    full: Annotated[
        bool,
        typer.Option(
            "--full",
            help="Full bootstrap with LLM-enriched design file generation.",
        ),
    ] = False,
    quick: Annotated[
        bool,
        typer.Option(
            "--quick",
            help="Quick bootstrap — aindex + skeleton design files (default behaviour).",
        ),
    ] = False,
) -> None:
    """Batch-initialize the library: generate .aindex and design files.

    Resolves the scope root from config (or --scope override), then
    recursively generates .aindex files bottom-up and skeleton design files
    for all source files. Safe to re-run at any time (idempotent).

    Quick mode (default) uses tree-sitter extraction and heuristic
    descriptions. Full mode (--full) additionally enriches design files
    via LLM.
    """
    import asyncio  # noqa: PLC0415

    from rich.progress import (  # noqa: PLC0415
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
    )

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.indexer.orchestrator import index_recursive  # noqa: PLC0415
    from lexibrary.lifecycle.bootstrap import bootstrap_full, bootstrap_quick  # noqa: PLC0415

    # Mutual exclusivity
    if full and quick:
        console.print(
            "[red]Error:[/red] [cyan]--full[/cyan] and [cyan]--quick[/cyan]"
            " are mutually exclusive."
        )
        raise typer.Exit(1)

    project_root = require_project_root()
    config = load_config(project_root)

    # Resolve scope root
    scope_root_str = scope if scope is not None else config.scope_root
    scope_dir = (project_root / scope_root_str).resolve()

    # Validate scope directory
    if not scope_dir.exists():
        console.print(f"[red]Scope directory not found:[/red] {scope_root_str}")
        raise typer.Exit(1)

    if not scope_dir.is_dir():
        console.print(f"[red]Scope root is not a directory:[/red] {scope_root_str}")
        raise typer.Exit(1)

    # Determine mode label
    mode_label = "full" if full else "quick"

    # Run recursive indexing with progress
    rel_scope = scope_dir.relative_to(project_root) if scope_dir != project_root else Path(".")
    console.print(
        f"Bootstrapping [cyan]{rel_scope}[/cyan] in [cyan]{project_root.name}[/cyan]"
        f" ([cyan]{mode_label}[/cyan] mode)..."
    )

    # Phase 1: .aindex generation
    console.print()
    console.print("[bold]Phase 1:[/bold] Generating .aindex files...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Indexing...", total=None)

        def _index_progress(current: int, total: int, name: str) -> None:
            progress.update(task, description=f"Indexing [{current}/{total}] {name}")

        index_stats = index_recursive(
            scope_dir, project_root, config, progress_callback=_index_progress
        )

    console.print(
        f"  Directories indexed: {index_stats.directories_indexed}, "
        f"Files found: {index_stats.files_found}"
    )
    if index_stats.errors:
        console.print(f"  [red]Errors: {index_stats.errors}[/red]")

    if index_stats.error_summary.has_errors():
        from lexibrary.errors import format_error_summary  # noqa: PLC0415

        format_error_summary(index_stats.error_summary, console)

    # Phase 2: Design file generation
    console.print()
    console.print(
        f"[bold]Phase 2:[/bold] Generating design files ([cyan]{mode_label}[/cyan] mode)..."
    )

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Generating design files...", total=None)
        file_count = 0

        def _design_progress(file_path: Path, status: str) -> None:
            nonlocal file_count
            file_count += 1
            progress.update(
                task,
                advance=1,
                description=f"[{status}] {file_path.name}",
            )

        if full:
            design_stats = asyncio.run(
                bootstrap_full(
                    project_root,
                    config,
                    scope_override=scope,
                    progress_callback=_design_progress,
                )
            )
        else:
            design_stats = bootstrap_quick(
                project_root,
                config,
                scope_override=scope,
                progress_callback=_design_progress,
            )

    # Report summary
    console.print()
    console.print("[bold]Bootstrap summary:[/bold]")
    console.print(f"  Files scanned:  {design_stats.files_scanned}")
    console.print(f"  Files created:  {design_stats.files_created}")
    console.print(f"  Files updated:  {design_stats.files_updated}")
    console.print(f"  Files skipped:  {design_stats.files_skipped}")
    if design_stats.files_failed:
        console.print(f"  [red]Files failed:  {design_stats.files_failed}[/red]")

    if design_stats.errors:
        console.print()
        console.print("[bold red]Errors:[/bold red]")
        for err in design_stats.errors:
            console.print(f"  [red]{err}[/red]")

    has_errors = index_stats.errors > 0 or design_stats.files_failed > 0
    if has_errors:
        raise typer.Exit(1)

    console.print()
    console.print("[green]Bootstrap complete.[/green]")


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
# help
# ---------------------------------------------------------------------------


@lexictl_app.command("help")
def maintainer_help() -> None:
    """Display structured guidance about lexictl maintenance commands."""
    from rich.panel import Panel  # noqa: PLC0415
    from rich.text import Text  # noqa: PLC0415

    # -- About -----------------------------------------------------------------
    about_text = Text()
    about_text.append("lexictl", style="bold cyan")
    about_text.append(" is the maintenance CLI for Lexibrary.\n")
    about_text.append("It is used by project maintainers (humans) for setup, indexing,\n")
    about_text.append("design file generation, and validation.\n\n")
    about_text.append("Agents must use ", style="bold")
    about_text.append("lexi", style="bold cyan")
    about_text.append(" instead.", style="bold")
    about_text.append(" All agent-facing commands live there.\n")
    about_text.append("Running lexictl commands in agent sessions is prohibited per project rules.")

    console.print(Panel(about_text, title="About lexictl", border_style="yellow"))

    # -- Maintenance Commands --------------------------------------------------
    cmds_text = Text()
    cmds_text.append("Setup & Initialization\n", style="bold underline")
    cmds_text.append("  lexictl init [--defaults]", style="cyan")
    cmds_text.append("              Initialize project (runs setup wizard)\n")
    cmds_text.append("  lexictl setup [--update] [--env ENV] [--hooks]", style="cyan")
    cmds_text.append("\n                                                Install/update agent rules or git hooks\n")
    cmds_text.append("  lexictl bootstrap [--scope SCOPE] [--full | --quick]", style="cyan")
    cmds_text.append("\n                                                Batch-initialize library (idempotent)\n")
    cmds_text.append("\n")
    cmds_text.append("Indexing & Updates\n", style="bold underline")
    cmds_text.append("  lexictl index [directory] [-r/--recursive]", style="cyan")
    cmds_text.append("\n                                                Generate .aindex file(s)\n")
    cmds_text.append("  lexictl update [path] [--changed-only PATH] [--dry-run] [--topology] [--skeleton]", style="cyan")
    cmds_text.append("\n                                                Re-index and regenerate design files\n")
    cmds_text.append("\n")
    cmds_text.append("Validation & Status\n", style="bold underline")
    cmds_text.append("  lexictl validate [--severity LEVEL] [--check NAME] [--json] [--ci] [--fix]", style="cyan")
    cmds_text.append("\n                                                Run consistency checks\n")
    cmds_text.append("  lexictl status [path] [-q/--quiet]", style="cyan")
    cmds_text.append("          Library health and staleness summary\n")
    cmds_text.append("\n")
    cmds_text.append("Background Processing\n", style="bold underline")
    cmds_text.append("  lexictl sweep [--watch]", style="cyan")
    cmds_text.append("                Run update sweep (one-shot or watch mode)\n")
    cmds_text.append("  lexictl daemon [start|stop|status]", style="cyan")
    cmds_text.append("      (deprecated -- use 'sweep')\n")
    cmds_text.append("\n")
    cmds_text.append("IWH Maintenance\n", style="bold underline")
    cmds_text.append("  lexictl iwh clean [--older-than N] [--all]", style="cyan")
    cmds_text.append("\n                                                Remove expired IWH signal files\n")

    console.print(Panel(cmds_text, title="Maintenance Commands", border_style="cyan"))

    # -- Agent Guidance --------------------------------------------------------
    guide_text = Text()
    guide_text.append("Run ", style="bold")
    guide_text.append("lexi help", style="cyan")
    guide_text.append(" to see all agent-facing commands.\n\n")
    guide_text.append("Key agent commands:\n")
    guide_text.append("  lexi lookup <file>", style="cyan")
    guide_text.append("       Understand a file before editing it\n")
    guide_text.append("  lexi concepts <topic>", style="cyan")
    guide_text.append("    Check conventions before architectural decisions\n")
    guide_text.append("  lexi stack search <query>", style="cyan")
    guide_text.append("  Search for known issues before debugging\n\n")
    guide_text.append("If you see lexictl in an error message, the project maintainer\n")
    guide_text.append("needs to run it. Do not run it yourself.")

    console.print(Panel(guide_text, title="Agent Guidance", border_style="green"))


# ---------------------------------------------------------------------------
# iwh clean
# ---------------------------------------------------------------------------


@iwh_ctl_app.command("clean")
def iwh_clean(
    *,
    older_than: Annotated[
        int | None,
        typer.Option(
            "--older-than",
            help="Only remove signals older than N hours (default: config TTL).",
        ),
    ] = None,
    all_signals: Annotated[
        bool,
        typer.Option("--all", help="Remove all signals regardless of age (bypass TTL)."),
    ] = False,
) -> None:
    """Remove IWH signal files from the project.

    By default, removes signals older than the configured TTL
    (config.iwh.ttl_hours). Use --older-than to override the TTL
    threshold, or --all to remove every signal regardless of age.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.iwh.reader import IWH_FILENAME, find_all_iwh  # noqa: PLC0415
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    project_root = require_project_root()
    results = find_all_iwh(project_root)

    if not results:
        console.print("[dim]No IWH signals to clean.[/dim]")
        return

    # Determine the TTL threshold to apply
    if all_signals:
        ttl_threshold: int | None = None  # bypass TTL — remove everything
    elif older_than is not None:
        ttl_threshold = older_than
    else:
        # Default: use config TTL
        config = load_config(project_root)
        ttl_threshold = config.iwh.ttl_hours

    now = datetime.now(tz=UTC)
    removed = 0
    for source_dir, iwh in results:
        if ttl_threshold is not None:
            created = iwh.created
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            age_hours = (now - created).total_seconds() / 3600
            if age_hours < ttl_threshold:
                continue

        iwh_file = project_root / LEXIBRARY_DIR / source_dir / IWH_FILENAME
        if iwh_file.exists():
            iwh_file.unlink()
            display_dir = f"{source_dir}/" if str(source_dir) != "." else "./"
            console.print(f"  [red]Removed[/red] {display_dir} ({iwh.scope})")
            removed += 1

    console.print(f"\n[green]Cleaned[/green] {removed} signal(s)")
