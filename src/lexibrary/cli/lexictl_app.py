"""Maintenance CLI for Lexibrary — setup, design file generation, and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._output import error, info, warn
from lexibrary.cli._shared import (
    _run_status,
    _run_validate,
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
    rich_markup_mode=None,
    callback=load_dotenv_if_configured,
)

iwh_ctl_app = typer.Typer(help="IWH signal maintenance commands.", rich_markup_mode=None)
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
        error(
            "Project already initialised."
            " Use `lexictl setup --update` to modify settings."
        )
        raise typer.Exit(1)

    # Non-TTY detection
    if not defaults and not sys.stdin.isatty():
        error(
            "Non-interactive environment detected."
            " Use `lexictl init --defaults` to run without prompts."
        )
        raise typer.Exit(1)

    # Show startup banner
    from lexibrary.cli.banner import render_banner  # noqa: PLC0415

    render_banner()

    # Run wizard
    answers = run_wizard(project_root, use_defaults=defaults)

    if answers is None:
        warn("Init cancelled.")
        raise typer.Exit(1)

    # Create skeleton from wizard answers
    created = create_lexibrary_from_wizard(project_root, answers)
    info(f"Created .lexibrary/ skeleton ({len(created)} items)")

    # Generate agent rule files for selected environments
    if answers.agent_environments:
        from lexibrary.init.rules import generate_rules, supported_environments  # noqa: PLC0415

        # Filter to only supported environments (user may have typed an unsupported name)
        supported = supported_environments()
        valid_envs = [e for e in answers.agent_environments if e in supported]
        if valid_envs:
            results = generate_rules(project_root, valid_envs)
            for env_name, paths in results.items():
                info(f"  {env_name}: {len(paths)} rule file(s) created")
                for p in paths:
                    rel = p.relative_to(project_root)
                    info(f"    {rel}")

    # Install git hooks if user opted in
    if answers.install_hooks:
        from lexibrary.hooks.post_commit import install_post_commit_hook  # noqa: PLC0415
        from lexibrary.hooks.pre_commit import install_pre_commit_hook  # noqa: PLC0415

        post_result = install_post_commit_hook(project_root)
        info(post_result.message)

        pre_result = install_pre_commit_hook(project_root)
        info(pre_result.message)

    # Post-init: offer to run lexictl update (skip in defaults mode)
    if not defaults:
        answer = input("\nRun `lexictl update` now to generate design files? [y/N] ")
        run_update = answer.strip().lower() in ("y", "yes")
        if run_update:
            info("Running lexictl update...")
            import asyncio  # noqa: PLC0415

            from lexibrary.archivist.pipeline import update_project  # noqa: PLC0415
            from lexibrary.archivist.service import ArchivistService  # noqa: PLC0415
            from lexibrary.config.loader import load_config  # noqa: PLC0415
            from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

            config = load_config(project_root)
            rate_limiter = RateLimiter()
            archivist = ArchivistService(rate_limiter=rate_limiter, config=config.llm)
            stats = asyncio.run(update_project(project_root, config, archivist))
            info(
                f"Update complete. "
                f"{stats.files_scanned} files scanned, "
                f"{stats.files_created} created, "
                f"{stats.files_updated} updated."
            )
        else:
            info("Run `lexictl update` later to generate design files.")
    else:
        info("Run `lexictl update` to generate design files.")


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

    from lexibrary.archivist.pipeline import (  # noqa: PLC0415
        UpdateStats,
        dry_run_files,
        dry_run_project,
        update_directory,
        update_file,
        update_files,
        update_project,
    )
    from lexibrary.archivist.service import ArchivistService  # noqa: PLC0415
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

    # Mutual exclusivity checks — skeleton first (it subsumes the path argument)
    if skeleton and (changed_only is not None or topology or dry_run):
        error(
            "--skeleton cannot be combined with"
            " --changed-only, --topology,"
            " or --dry-run."
        )
        raise typer.Exit(1)

    if skeleton and path is None:
        error(
            "--skeleton requires a file path argument."
        )
        raise typer.Exit(1)

    if path is not None and changed_only is not None:
        error(
            "path and --changed-only"
            " are mutually exclusive. Use one or the other."
        )
        raise typer.Exit(1)

    if topology and (changed_only is not None or path is not None):
        error(
            "--topology cannot be combined with"
            " path or --changed-only."
        )
        raise typer.Exit(1)

    project_root = require_project_root()
    config = load_config(project_root)

    # Resolve and validate path argument early
    target: Path | None = None
    if path is not None:
        target = Path(path).resolve()
        if not target.exists():
            error(f"Path not found: {path}")
            raise typer.Exit(1)
        try:
            target.relative_to(project_root)
        except ValueError:
            error(
                f"Path is outside the project root: {path}\n"
                f"Project root: {project_root}"
            )
            raise typer.Exit(1) from None

    # --skeleton: quick skeleton design file without LLM enrichment
    if skeleton:
        from lexibrary.lifecycle.bootstrap import _generate_quick_design  # noqa: PLC0415
        from lexibrary.lifecycle.queue import queue_for_enrichment  # noqa: PLC0415

        assert target is not None  # guaranteed by earlier check

        if not target.is_file():
            error(f"Not a file: {path}")
            raise typer.Exit(1)

        try:
            result = _generate_quick_design(target, project_root)
        except Exception as exc:
            error(f"Failed to generate skeleton: {exc}")
            raise typer.Exit(1) from None

        queue_for_enrichment(project_root, target)

        info(
            f"Skeleton generated. Change level: {result.change.value}"
        )
        return

    # --topology: regenerate TOPOLOGY.md only
    if topology:
        from lexibrary.archivist.topology import generate_topology  # noqa: PLC0415

        try:
            generate_topology(project_root)
            info("TOPOLOGY.md generated.")
        except Exception as exc:
            error(f"Failed to generate TOPOLOGY.md: {exc}")
            raise typer.Exit(1) from None
        return

    # --dry-run: preview changes without modifications
    if dry_run:
        warn("DRY-RUN MODE -- no files will be modified")
        info("")

        if changed_only is not None:
            resolved_paths = [p.resolve() for p in changed_only]
            results = asyncio.run(dry_run_files(resolved_paths, project_root, config))
        elif target is not None:
            if target.is_file():
                results = asyncio.run(dry_run_files([target], project_root, config))
            else:
                results = asyncio.run(
                    dry_run_project(project_root, config, scope_dir=target)
                )
        else:
            results = asyncio.run(dry_run_project(project_root, config))

        if not results:
            info("No files would change.")
            return

        # Display results
        counts: dict[str, int] = {}
        for file_path, change_level in results:
            label = change_level.value.upper()
            counts[label] = counts.get(label, 0) + 1
            rel_path = file_path.relative_to(project_root)
            info(f"  {label:<20} {rel_path}")

        # Summary
        info("")
        total = len(results)
        parts = [f"{total} file{'s' if total != 1 else ''}"]
        for label, count in sorted(counts.items()):
            parts.append(f"{count} {label.lower()}")
        info("Summary: " + ", ".join(parts))
        return

    rate_limiter = RateLimiter()
    archivist = ArchivistService(rate_limiter=rate_limiter, config=config.llm)

    # --changed-only: batch update specific files
    if changed_only is not None:
        resolved_paths = [p.resolve() for p in changed_only]
        info(f"Updating {len(resolved_paths)} changed file(s)...")

        stats = asyncio.run(update_files(resolved_paths, project_root, config, archivist))

        info("")
        info("Update summary:")
        info(f"  Files scanned:       {stats.files_scanned}")
        info(f"  Files unchanged:     {stats.files_unchanged}")
        info(f"  Files created:       {stats.files_created}")
        info(f"  Files updated:       {stats.files_updated}")
        info(f"  Files agent-updated: {stats.files_agent_updated}")
        if stats.files_failed:
            error(f"  Files failed:       {stats.files_failed}")
            for failed_path, reason in stats.failed_files:
                try:
                    rel = Path(failed_path).relative_to(project_root)
                except ValueError:
                    rel = failed_path
                error(f"    - {rel}: {reason}")

        if stats.error_summary.has_errors():
            from lexibrary.errors import format_error_summary  # noqa: PLC0415

            format_error_summary(stats.error_summary)

        if stats.files_failed:
            raise typer.Exit(1)
        return

    # Single file update
    if target is not None and target.is_file():
        info(f"Updating design file for {path}...")
        result = asyncio.run(update_file(target, project_root, config, archivist))
        if result.failed:
            error(f"Failed to update design file for {path}")
            raise typer.Exit(1)
        info(f"Done. Change level: {result.change.value}")
        return

    # Directory-scoped or full project update with progress
    if target is not None:
        rel_dir = target.relative_to(project_root)
        info(f"Updating directory: {rel_dir}/")

    stats = UpdateStats()
    _file_count = 0

    def _progress_callback(file_path: Path, change_level: object) -> None:
        nonlocal _file_count
        _file_count += 1
        info(f"  [{_file_count}] Processing {file_path.name}")

    if target is not None:
        stats = asyncio.run(
            update_directory(
                target, project_root, config, archivist,
                progress_callback=_progress_callback,
            )
        )
    else:
        stats = asyncio.run(
            update_project(
                project_root, config, archivist,
                progress_callback=_progress_callback,
            )
        )

    if stats.topology_failed:
        error("Failed to generate TOPOLOGY.md.")
    else:
        info("TOPOLOGY.md generated.")

    # Print summary stats
    info("")
    info("Update summary:")
    info(f"  Files scanned:       {stats.files_scanned}")
    info(f"  Files unchanged:     {stats.files_unchanged}")
    info(f"  Files created:       {stats.files_created}")
    info(f"  Files updated:       {stats.files_updated}")
    info(f"  Files agent-updated: {stats.files_agent_updated}")
    if stats.files_failed:
        error(f"  Files failed:       {stats.files_failed}")
        for failed_path, reason in stats.failed_files:
            try:
                rel = Path(failed_path).relative_to(project_root)
            except ValueError:
                rel = failed_path
            error(f"    - {rel}: {reason}")
    if stats.aindex_refreshed:
        info(f"  .aindex refreshed:   {stats.aindex_refreshed}")
    if stats.token_budget_warnings:
        warn(f"  Token budget warnings: {stats.token_budget_warnings}")

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
        info("")
        info("Lifecycle:")
        if stats.renames_detected:
            info(f"  Renames detected:    {stats.renames_detected}")
        if stats.renames_migrated:
            info(f"  Renames migrated:    {stats.renames_migrated}")
        if stats.designs_deprecated:
            info(f"  Designs deprecated:  {stats.designs_deprecated}")
        if stats.designs_unlinked:
            info(f"  Designs unlinked:    {stats.designs_unlinked}")
        if stats.designs_deleted_ttl:
            warn(
                f"  Designs TTL-deleted: {stats.designs_deleted_ttl}"
            )
        if stats.concepts_deleted_ttl:
            warn(
                f"  Concepts TTL-deleted: {stats.concepts_deleted_ttl}"
            )
        if stats.concepts_skipped_referenced:
            info(
                f"  Concepts skipped (referenced): {stats.concepts_skipped_referenced}"
            )
        if stats.conventions_deleted_ttl:
            warn(
                f"  Conventions TTL-deleted: {stats.conventions_deleted_ttl}"
            )

    # Enrichment queue stats
    has_queue = (stats.queue_processed + stats.queue_failed + stats.queue_remaining) > 0
    if has_queue:
        info("")
        info("Enrichment queue:")
        if stats.queue_processed:
            info(f"  Enriched:            {stats.queue_processed}")
        if stats.queue_failed:
            error(f"  Failed:             {stats.queue_failed}")
        if stats.queue_remaining:
            info(f"  Remaining:           {stats.queue_remaining}")

    if stats.error_summary.has_errors():
        from lexibrary.errors import format_error_summary  # noqa: PLC0415

        format_error_summary(stats.error_summary)

    # Run IWH cleanup on full project update (no path / no --changed-only)
    if path is None and changed_only is None:
        from lexibrary.iwh.cleanup import iwh_cleanup  # noqa: PLC0415

        cleanup = iwh_cleanup(project_root, config.iwh.ttl_hours)
        total_cleaned = len(cleanup.expired) + len(cleanup.orphaned)
        if total_cleaned > 0:
            info("")
            info("IWH cleanup:")
            if cleanup.expired:
                info(f"  Expired:  {len(cleanup.expired)} signal(s) removed")
            if cleanup.orphaned:
                info(f"  Orphaned: {len(cleanup.orphaned)} signal(s) removed")
            if cleanup.kept > 0:
                info(f"  Kept:     {cleanup.kept} signal(s)")

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

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.indexer.orchestrator import index_recursive  # noqa: PLC0415
    from lexibrary.lifecycle.bootstrap import bootstrap_full, bootstrap_quick  # noqa: PLC0415

    # Mutual exclusivity
    if full and quick:
        error(
            "--full and --quick"
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
        error(f"Scope directory not found: {scope_root_str}")
        raise typer.Exit(1)

    if not scope_dir.is_dir():
        error(f"Scope root is not a directory: {scope_root_str}")
        raise typer.Exit(1)

    # Determine mode label
    mode_label = "full" if full else "quick"

    # Run recursive indexing with progress
    rel_scope = scope_dir.relative_to(project_root) if scope_dir != project_root else Path(".")
    info(
        f"Bootstrapping {rel_scope} in {project_root.name}"
        f" ({mode_label} mode)..."
    )

    # Phase 1: .aindex generation
    info("")
    info("Phase 1: Generating .aindex files...")

    def _index_progress(current: int, total: int, name: str) -> None:
        info(f"  Indexing [{current}/{total}] {name}")

    index_stats = index_recursive(
        scope_dir, project_root, config, progress_callback=_index_progress
    )

    info(
        f"  Directories indexed: {index_stats.directories_indexed}, "
        f"Files found: {index_stats.files_found}"
    )
    if index_stats.errors:
        error(f"  Errors: {index_stats.errors}")

    if index_stats.error_summary.has_errors():
        from lexibrary.errors import format_error_summary  # noqa: PLC0415

        format_error_summary(index_stats.error_summary)

    # Phase 2: Design file generation
    info("")
    info(
        f"Phase 2: Generating design files ({mode_label} mode)..."
    )

    _design_file_count = 0

    def _design_progress(file_path: Path, status: str) -> None:
        nonlocal _design_file_count
        _design_file_count += 1
        info(f"  [{status}] {file_path.name}")

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
    info("")
    info("Bootstrap summary:")
    info(f"  Files scanned:  {design_stats.files_scanned}")
    info(f"  Files created:  {design_stats.files_created}")
    info(f"  Files updated:  {design_stats.files_updated}")
    info(f"  Files skipped:  {design_stats.files_skipped}")
    if design_stats.files_failed:
        error(f"  Files failed:  {design_stats.files_failed}")

    if design_stats.errors:
        info("")
        error("Errors:")
        for err in design_stats.errors:
            error(f"  {err}")

    has_errors = index_stats.errors > 0 or design_stats.files_failed > 0
    if has_errors:
        raise typer.Exit(1)

    info("")
    info("Bootstrap complete.")


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
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.indexer.orchestrator import index_directory, index_recursive  # noqa: PLC0415

    project_root = require_project_root()

    # Resolve directory relative to cwd
    target = Path(directory).resolve()

    # Validate directory exists
    if not target.exists():
        error(f"Directory not found: {directory}")
        raise typer.Exit(1)

    if not target.is_dir():
        error(f"Not a directory: {directory}")
        raise typer.Exit(1)

    # Validate directory is within project root
    try:
        target.relative_to(project_root)
    except ValueError:
        error(
            f"Directory is outside the project root: {directory}\n"
            f"Project root: {project_root}"
        )
        raise typer.Exit(1) from None

    config = load_config(project_root)

    if recursive:
        def _progress_callback(current: int, total: int, name: str) -> None:
            info(f"  Indexing [{current}/{total}] {name}")

        stats = index_recursive(
            target, project_root, config, progress_callback=_progress_callback
        )

        info(
            f"\nIndexing complete. "
            f"{stats.directories_indexed} directories indexed, "
            f"{stats.files_found} files found"
            + (f", {stats.errors} errors" if stats.errors else "")
            + "."
        )

        if stats.error_summary.has_errors():
            from lexibrary.errors import format_error_summary  # noqa: PLC0415

            format_error_summary(stats.error_summary)
    else:
        output_path = index_directory(target, project_root, config)
        info(f"Wrote {output_path}")


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
            error(post_result.message)
            raise typer.Exit(1)
        if post_result.already_installed:
            warn(post_result.message)
        else:
            info(post_result.message)

        # Install pre-commit hook
        pre_result = install_pre_commit_hook(project_root)
        if pre_result.no_git_dir:
            error(pre_result.message)
            raise typer.Exit(1)
        if pre_result.already_installed:
            warn(pre_result.message)
        else:
            info(pre_result.message)
        return

    if not update_flag:
        info(
            "Usage:\n"
            "  lexictl setup --update  "
            "Update agent rules for configured environments\n"
            "  lexictl init             "
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
        warn(
            "No agent environments configured."
            " Run `lexictl init` to set up agent environments."
        )
        raise typer.Exit(1)

    # Validate environment names before generating
    supported = supported_environments()
    unsupported = [e for e in environments if e not in supported]
    if unsupported:
        error(
            f"Unsupported environment(s): {', '.join(sorted(unsupported))}\n"
            f"Supported: {', '.join(supported)}"
        )
        raise typer.Exit(1)

    # Generate rules for each environment
    results = generate_rules(project_root, environments)

    for env_name, paths in results.items():
        info(f"  {env_name}: {len(paths)} file(s) written")
        for p in paths:
            rel = p.relative_to(project_root)
            info(f"    {rel}")

    # Ensure IWH files are gitignored
    iwh_modified = ensure_iwh_gitignored(project_root)
    if iwh_modified:
        info("  .gitignore: added IWH pattern")

    total_files = sum(len(paths) for paths in results.values())
    info(f"\nSetup complete. {total_files} rule file(s) updated.")


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
        error(
            f"Unknown action: {resolved_action}\n"
            f"Valid actions: {', '.join(valid_actions)}"
        )
        raise typer.Exit(1)

    pid_path = project_root / ".lexibrary" / "daemon.pid"

    if resolved_action == "start":
        config = load_config(project_root)
        if not config.daemon.watchdog_enabled:
            warn(
                "Watchdog mode is disabled in config.\n"
                "Use `lexictl sweep --watch` for periodic sweeps, "
                "or set `daemon.watchdog_enabled: true` in config."
            )
            return
        svc = DaemonService(project_root)
        svc.run_watchdog()

    elif resolved_action == "stop":
        if not pid_path.exists():
            warn("No daemon is running (no PID file found).")
            return
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            error("Cannot read PID file.")
            pid_path.unlink(missing_ok=True)
            raise typer.Exit(1) from None

        try:
            os.kill(pid, _signal.SIGTERM)
            info(f"Sent SIGTERM to daemon (PID {pid}).")
        except ProcessLookupError:
            warn(
                f"Process {pid} not found -- cleaning up stale PID file."
            )
            pid_path.unlink(missing_ok=True)
        except PermissionError:
            error(f"Permission denied sending signal to PID {pid}.")
            raise typer.Exit(1) from None

    elif resolved_action == "status":
        if not pid_path.exists():
            info("No daemon is running.")
            return
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            error("Cannot read PID file.")
            pid_path.unlink(missing_ok=True)
            raise typer.Exit(1) from None

        # Check if process is still running
        try:
            os.kill(pid, 0)
            info(f"Daemon is running (PID {pid}).")
        except ProcessLookupError:
            warn(
                f"Stale PID file found (PID {pid} is not running). Cleaning up."
            )
            pid_path.unlink(missing_ok=True)
        except PermissionError:
            # Process exists but we can't signal it -- it's running
            info(f"Daemon is running (PID {pid}).")


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


@lexictl_app.command("help")
def maintainer_help() -> None:
    """Display structured guidance about lexictl maintenance commands."""
    help_text = """\
=== About lexictl ===

lexictl is the maintenance CLI for Lexibrary.
It is used by project maintainers (humans) for setup, indexing,
design file generation, and validation.

Agents must use `lexi` instead. All agent-facing commands live there.
Running lexictl commands in agent sessions is prohibited per project rules.

=== Maintenance Commands ===

Setup & Initialization
  lexictl init [--defaults]              Initialize project (runs setup wizard)
  lexictl setup [--update] [--env ENV] [--hooks]
                                         Install/update agent rules or git hooks
  lexictl bootstrap [--scope SCOPE] [--full | --quick]
                                         Batch-initialize library (idempotent)

Indexing & Updates
  lexictl index [directory] [-r/--recursive]
                                         Generate .aindex file(s)
  lexictl update [path] [--changed-only PATH] [--dry-run] [--topology] [--skeleton]
                                         Re-index and regenerate design files

Validation & Status
  lexictl validate [--severity LEVEL] [--check NAME] [--json] [--ci] [--fix]
                                         Run consistency checks
  lexictl status [path] [-q/--quiet]     Library health and staleness summary

Background Processing
  lexictl sweep [--watch]                Run update sweep (one-shot or watch mode)
  lexictl daemon [start|stop|status]     (deprecated -- use 'sweep')

IWH Maintenance
  lexictl iwh clean [--older-than N] [--all]
                                         Remove expired IWH signal files

=== Agent Guidance ===

Run `lexi help` to see all agent-facing commands.

Key agent commands:
  lexi lookup <file>         Understand a file before editing it
  lexi concepts <topic>      Check conventions before architectural decisions
  lexi stack search <query>  Search for known issues before debugging

If you see lexictl in an error message, the project maintainer
needs to run it. Do not run it yourself."""

    info(help_text)


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
        info("No IWH signals to clean.")
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
            info(f"  Removed {display_dir} ({iwh.scope})")
            removed += 1

    info(f"\nCleaned {removed} signal(s)")
