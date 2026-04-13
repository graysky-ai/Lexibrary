"""Maintenance CLI for Lexibrary — setup, design file generation, and validation."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._output import error, hint, info, warn
from lexibrary.cli._shared import (
    _run_validate,
    load_dotenv_if_configured,
    require_project_root,
)
from lexibrary.services.status import collect_status
from lexibrary.services.status_render import render_dashboard, render_quiet

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

from lexibrary.cli.curate import curate  # noqa: E402

lexictl_app.command("curate")(curate)


# ---------------------------------------------------------------------------
# init — helpers
# ---------------------------------------------------------------------------


def _run_post_init_update(project_root: Path) -> None:
    """Prompt the user to run ``lexictl update`` after init and execute if accepted."""
    import asyncio  # noqa: PLC0415

    from lexibrary.archivist.pipeline import update_project  # noqa: PLC0415
    from lexibrary.archivist.service import ArchivistService  # noqa: PLC0415
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.llm.client_registry import build_client_registry  # noqa: PLC0415
    from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

    answer = input("\nRun `lexictl update` now to generate design files? [y/N] ")
    if answer.strip().lower() not in ("y", "yes"):
        info("Run `lexictl update` later to generate design files.")
        return

    info("Running lexictl update...")
    config = load_config(project_root)
    rate_limiter = RateLimiter()
    registry = build_client_registry(config)
    archivist = ArchivistService(rate_limiter=rate_limiter, client_registry=registry)
    stats = asyncio.run(update_project(project_root, config, archivist))
    info(
        f"Update complete. "
        f"{stats.files_scanned} files scanned, "
        f"{stats.files_created} created, "
        f"{stats.files_updated} updated."
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
        error("Project already initialised. Use `lexictl setup --update` to modify settings.")
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
        _run_post_init_update(project_root)
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
            help="Regenerate raw-topology.md only, without running the full update.",
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
    unlimited: Annotated[
        bool,
        typer.Option(
            "--unlimited",
            help=(
                "Bypass the size gate so large files are sent to the LLM "
                "instead of receiving a skeleton fallback."
            ),
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help=(
                "Force a full rebuild regardless of modification timestamps. "
                "Treats every file as new so the pipeline regenerates all design files "
                "and rebuilds the link-graph index from scratch, pruning stale entries "
                "left behind by deleted concept or convention files."
            ),
        ),
    ] = False,
    reindex: Annotated[
        bool,
        typer.Option(
            "--reindex",
            help=(
                "Rebuild the link graph index from existing artifacts on disk. "
                "Does not regenerate design files or invoke the LLM."
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
    from lexibrary.llm.client_registry import build_client_registry  # noqa: PLC0415
    from lexibrary.llm.rate_limiter import RateLimiter  # noqa: PLC0415

    # Mutual exclusivity checks — skeleton first (it subsumes the path argument)
    if skeleton and (
        changed_only is not None or topology or dry_run or unlimited or force or reindex
    ):
        error(
            "--skeleton cannot be combined with"
            " --changed-only, --topology, --dry-run, --unlimited, or --force."
        )
        raise typer.Exit(1)

    if force and (topology or dry_run):
        error("--force cannot be combined with --topology or --dry-run.")
        raise typer.Exit(1)

    if skeleton and path is None:
        error("--skeleton requires a file path argument.")
        raise typer.Exit(1)

    if path is not None and changed_only is not None:
        error("path and --changed-only are mutually exclusive. Use one or the other.")
        raise typer.Exit(1)

    if topology and (changed_only is not None or path is not None):
        error("--topology cannot be combined with path or --changed-only.")
        raise typer.Exit(1)

    if reindex and (
        path is not None
        or changed_only is not None
        or dry_run
        or topology
        or skeleton
        or force
        or unlimited
    ):
        error("--reindex cannot be combined with any other update flags.")
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
            error(f"Path is outside the project root: {path}\nProject root: {project_root}")
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

        info(f"Skeleton generated. Change level: {result.change.value}")
        return

    # --topology: regenerate raw topology only
    if topology:
        from lexibrary.archivist.topology import generate_raw_topology  # noqa: PLC0415

        try:
            generate_raw_topology(project_root)
            info("Raw topology written to .lexibrary/tmp/raw-topology.md")
            hint("Run /topology-builder to generate TOPOLOGY.md")
        except Exception as exc:
            error(f"Failed to generate raw topology: {exc}")
            raise typer.Exit(1) from None
        return

    # --reindex: rebuild link graph index from existing artifacts
    if reindex:
        from lexibrary.linkgraph.builder import build_index  # noqa: PLC0415

        info("Rebuilding link graph index...")
        try:
            build_result = build_index(project_root)
            info(
                f"Link graph rebuilt: "
                f"{build_result.artifact_count} artifacts, "
                f"{build_result.link_count} links "
                f"({build_result.duration_ms / 1000:.1f}s)"
            )
            if build_result.errors:
                warn(
                    f"  {len(build_result.errors)} artifact(s) had parse errors"
                    " (see log for details)"
                )
        except Exception as exc:
            error(f"Failed to rebuild link graph: {exc}")
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
                results = asyncio.run(dry_run_project(project_root, config, scope_dir=target))
        else:
            results = asyncio.run(dry_run_project(project_root, config))

        if not results:
            info("No files would change.")
            return

        # Display results
        from lexibrary.services.update_render import render_dry_run_results  # noqa: PLC0415

        info(render_dry_run_results(results, project_root))
        return

    rate_limiter = RateLimiter()
    registry = build_client_registry(config, unlimited=unlimited)
    archivist = ArchivistService(rate_limiter=rate_limiter, client_registry=registry)

    # --changed-only: batch update specific files
    if changed_only is not None:
        resolved_paths = [p.resolve() for p in changed_only]
        info(f"Updating {len(resolved_paths)} changed file(s)...")

        stats = asyncio.run(
            update_files(
                resolved_paths, project_root, config, archivist, force=force, unlimited=unlimited
            )
        )

        from lexibrary.services.update_render import render_update_summary  # noqa: PLC0415

        for level, msg in render_update_summary(stats, project_root):
            {"info": info, "warn": warn, "error": error}[level](msg)

        if stats.error_summary.has_errors():
            from lexibrary.errors import format_error_summary  # noqa: PLC0415

            format_error_summary(stats.error_summary)

        if stats.files_failed:
            raise typer.Exit(1)
        return

    # Single file update
    if target is not None and target.is_file():
        info(f"Updating design file for {path}...")
        result = asyncio.run(
            update_file(target, project_root, config, archivist, force=force, unlimited=unlimited)
        )
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

    def _progress_callback(
        file_path: Path,
        change_level: object,
        skip_reason: str | None = None,
    ) -> None:
        nonlocal _file_count
        _file_count += 1
        if skip_reason:
            info(f"  [{_file_count}] Skipped {file_path.name} ({skip_reason})")
        else:
            info(f"  [{_file_count}] Processing {file_path.name}")

    if target is not None:
        stats = asyncio.run(
            update_directory(
                target,
                project_root,
                config,
                archivist,
                progress_callback=_progress_callback,
                force=force,
                unlimited=unlimited,
            )
        )
    else:
        stats = asyncio.run(
            update_project(
                project_root,
                config,
                archivist,
                progress_callback=_progress_callback,
                force=force,
                unlimited=unlimited,
            )
        )

    if stats.topology_failed:
        error("Failed to generate raw-topology.md.")
    else:
        info("Raw topology generated.")
        hint("Run /topology-builder to generate TOPOLOGY.md")

    # Print summary stats
    from lexibrary.services.update_render import (  # noqa: PLC0415
        has_enrichment_queue,
        has_lifecycle_stats,
        render_enrichment_queue,
        render_lifecycle_stats,
        render_update_summary,
    )

    _dispatch = {"info": info, "warn": warn, "error": error}

    for level, msg in render_update_summary(stats, project_root):
        _dispatch[level](msg)

    # Deprecation lifecycle stats
    if has_lifecycle_stats(stats):
        for level, msg in render_lifecycle_stats(stats):
            _dispatch[level](msg)

    # Enrichment queue stats
    if has_enrichment_queue(stats):
        for level, msg in render_enrichment_queue(stats):
            _dispatch[level](msg)

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
    from lexibrary.llm.client_registry import build_client_registry  # noqa: PLC0415

    # Mutual exclusivity
    if full and quick:
        error("--full and --quick are mutually exclusive.")
        raise typer.Exit(1)

    project_root = require_project_root()
    config = load_config(project_root)

    # Resolve scope roots. When ``--scope`` is provided, treat it as a
    # single-root override that must resolve to one of the declared
    # ``scope_roots``. When omitted, iterate every declared root.
    from lexibrary.config.scope import find_owning_root  # noqa: PLC0415

    scope_dirs: list[Path]
    if scope is not None:
        override = (project_root / scope).resolve()
        if find_owning_root(override, config.scope_roots, project_root) is None:
            error(
                f"{scope} is outside all configured scope_roots: "
                f"{[r.path for r in config.scope_roots]}"
            )
            raise typer.Exit(1)
        if not override.exists():
            error(f"Scope directory not found: {scope}")
            raise typer.Exit(1)
        if not override.is_dir():
            error(f"Scope root is not a directory: {scope}")
            raise typer.Exit(1)
        scope_dirs = [override]
    else:
        scope_dirs = list(config.resolved_scope_roots(project_root).resolved)
        if not scope_dirs:
            error(
                "No scope_roots resolved on disk. "
                f"Declared: {[r.path for r in config.scope_roots]}"
            )
            raise typer.Exit(1)

    # Determine mode label
    mode_label = "full" if full else "quick"

    # Phase 1: .aindex generation — one walk per declared root.
    info("")
    info("Phase 1: Generating .aindex files...")

    def _index_progress(current: int, total: int, name: str) -> None:
        info(f"  Indexing [{current}/{total}] {name}")

    from lexibrary.indexer.orchestrator import IndexStats  # noqa: PLC0415

    index_stats = IndexStats()
    for scope_dir in scope_dirs:
        rel_scope = (
            scope_dir.relative_to(project_root) if scope_dir != project_root else Path(".")
        )
        info(f"Bootstrapping {rel_scope} in {project_root.name} ({mode_label} mode)...")
        per_root_stats = index_recursive(
            scope_dir, project_root, config, progress_callback=_index_progress
        )
        # Aggregate per-root counts into the running totals; concatenate the
        # error records list so format_error_summary downstream can group by
        # phase exactly as it does for a single-root run.
        index_stats.directories_indexed += per_root_stats.directories_indexed
        index_stats.files_found += per_root_stats.files_found
        index_stats.errors += per_root_stats.errors
        index_stats.error_summary.records.extend(per_root_stats.error_summary.records)

    from lexibrary.services.bootstrap_render import (  # noqa: PLC0415
        render_bootstrap_summary,
        render_index_summary,
    )

    for level, msg in render_index_summary(index_stats):
        {"info": info, "error": error}[level](msg)

    if index_stats.error_summary.has_errors():
        from lexibrary.errors import format_error_summary  # noqa: PLC0415

        format_error_summary(index_stats.error_summary)

    # Phase 2: Design file generation
    info("")
    info(f"Phase 2: Generating design files ({mode_label} mode)...")

    _design_file_count = 0

    def _design_progress(file_path: Path, status: str) -> None:
        nonlocal _design_file_count
        _design_file_count += 1
        info(f"  [{status}] {file_path.name}")

    if full:
        registry = build_client_registry(config)
        design_stats = asyncio.run(
            bootstrap_full(
                project_root,
                config,
                scope_override=scope,
                progress_callback=_design_progress,
                client_registry=registry,
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
    for level, msg in render_bootstrap_summary(design_stats):
        {"info": info, "error": error}[level](msg)

    has_errors = index_stats.errors > 0 or design_stats.files_failed > 0
    if has_errors:
        raise typer.Exit(1)

    # Phase 3: Generate raw topology
    info("")
    info("Phase 3: Generating raw topology...")
    try:
        from lexibrary.archivist.topology import generate_raw_topology  # noqa: PLC0415

        generate_raw_topology(project_root)
        info("  Raw topology written to .lexibrary/tmp/raw-topology.md")
        hint("  Run /topology-builder to generate TOPOLOGY.md")
    except Exception as exc:
        warn(f"  Raw topology generation failed (non-fatal): {exc}")

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
        error(f"Directory is outside the project root: {directory}\nProject root: {project_root}")
        raise typer.Exit(1) from None

    config = load_config(project_root)

    if recursive:

        def _progress_callback(current: int, total: int, name: str) -> None:
            info(f"  Indexing [{current}/{total}] {name}")

        stats = index_recursive(target, project_root, config, progress_callback=_progress_callback)

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
    result = collect_status(project_root)
    if quiet:
        info(render_quiet(result, cli_prefix="lexictl"))
    else:
        info(render_dashboard(result, cli_prefix="lexictl"))
    raise typer.Exit(result.exit_code)


# ---------------------------------------------------------------------------
# setup / sweep
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
        warn("No agent environments configured. Run `lexictl init` to set up agent environments.")
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
    import signal as _signal  # noqa: PLC0415
    import threading  # noqa: PLC0415

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.services.sweep import (  # noqa: PLC0415
        has_changes,
        run_single_sweep,
        run_sweep_watch,
    )

    project_root = require_project_root()
    config = load_config(project_root)

    from lexibrary.archivist.pipeline import UpdateStats  # noqa: PLC0415

    def _render_stats(stats: UpdateStats) -> None:
        info(
            f"Sweep complete: {stats.files_scanned} scanned, "
            f"{stats.files_updated} updated, "
            f"{stats.files_created} created, "
            f"{stats.files_unchanged} unchanged"
            + (f", {stats.files_failed} failed" if stats.files_failed else "")
        )

    if not watch:
        # One-shot mode
        if config.sweep.sweep_skip_if_unchanged and not has_changes(project_root, 0.0):
            info("No changes detected -- skipping sweep.")
            return
        stats = run_single_sweep(project_root, config)
        _render_stats(stats)
        return

    # Watch mode: periodic sweeps with threading.Event for clean shutdown
    shutdown_event = threading.Event()
    interval = float(config.sweep.sweep_interval_seconds)

    def _signal_handler(signum: int, frame: object) -> None:
        shutdown_event.set()

    _signal.signal(_signal.SIGTERM, _signal_handler)
    _signal.signal(_signal.SIGINT, _signal_handler)

    info(f"Watching {project_root} (sweep every {interval:.0f}s). Press Ctrl+C to stop.")

    run_sweep_watch(
        project_root,
        config,
        interval=interval,
        skip_unchanged=config.sweep.sweep_skip_if_unchanged,
        on_complete=_render_stats,
        on_skip=lambda: info("No changes detected -- skipping sweep."),
        on_error=lambda exc: error(f"Sweep failed: {exc}"),
        shutdown_event=shutdown_event,
    )

    info("Sweep watch stopped.")


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
  lexictl update --reindex              Rebuild link graph from existing artifacts

Validation & Status
  lexictl validate [--severity LEVEL] [--check NAME] [--json] [--ci] [--fix]
                                         Run consistency checks
  lexictl status [path] [-q/--quiet]     Library health and staleness summary

Background Processing
  lexictl sweep [--watch]                Run update sweep (one-shot or watch mode)

IWH Maintenance
  lexictl iwh clean [--older-than N] [--all]
                                         Remove expired IWH signal files

=== Agent Guidance ===

Run `lexi --help` to see all agent-facing commands.

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
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.iwh.cleanup import iwh_cleanup  # noqa: PLC0415

    project_root = require_project_root()

    # Determine TTL and mode, then delegate to iwh_cleanup()
    if all_signals:
        result = iwh_cleanup(project_root, ttl_hours=0, remove_all=True)
    elif older_than is not None:
        result = iwh_cleanup(project_root, ttl_hours=older_than)
    else:
        config = load_config(project_root)
        result = iwh_cleanup(project_root, ttl_hours=config.iwh.ttl_hours)

    removed = result.expired + result.orphaned
    if not removed:
        info("No IWH signals to clean.")
        return

    for sig in removed:
        display_dir = f"{sig.source_dir}/" if str(sig.source_dir) != "." else "./"
        info(f"  Removed {display_dir} ({sig.scope})")

    info(f"\nCleaned {len(removed)} signal(s)")
