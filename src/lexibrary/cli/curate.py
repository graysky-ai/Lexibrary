"""Curator CLI command -- thin wrapper over the coordinator pipeline.

Registered on the ``lexictl`` app as ``lexictl curate``.  All output goes
through :mod:`lexibrary.cli._output` helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from lexibrary.cli._output import error, hint, info, warn
from lexibrary.cli._shared import require_project_root


def curate(
    *,
    scope: Annotated[
        Path | None,
        typer.Option(
            "--scope",
            help="Limit curation to a specific directory or file path.",
        ),
    ] = None,
    check: Annotated[
        str | None,
        typer.Option(
            "--check",
            help="Run only the named validation check.",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Show what would be dispatched without modifying files.",
        ),
    ] = False,
    last_run: Annotated[
        bool,
        typer.Option(
            "--last-run",
            help="Display the most recent curator report.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            help=(
                "Emit per-dispatch detail lines. When combined with "
                "--last-run, walks the persisted dispatched list."
            ),
        ),
    ] = False,
) -> None:
    """Run the curator pipeline to detect and fix library issues.

    Without flags, performs a full sweep: collect signals, triage, dispatch
    sub-agents for fixable issues, and write a JSON report.
    """
    project_root = require_project_root()

    # --last-run: display most recent report and exit
    if last_run:
        _handle_last_run(project_root, verbose=verbose)
        return

    # Validate --scope path exists
    resolved_scope: Path | None = None
    if scope is not None:
        resolved_scope = Path(scope).resolve()
        if not resolved_scope.exists():
            error(f"Scope path not found: {scope}")
            raise typer.Exit(1)
        try:
            resolved_scope.relative_to(project_root)
        except ValueError:
            error(f"Scope path is outside the project root: {scope}\nProject root: {project_root}")
            raise typer.Exit(1) from None

    # Validate --check name
    if check is not None:
        from lexibrary.validator import AVAILABLE_CHECKS  # noqa: PLC0415

        if check not in AVAILABLE_CHECKS:
            available = ", ".join(sorted(AVAILABLE_CHECKS))
            error(f"Unknown check: {check!r}")
            hint(f"Available checks: {available}")
            raise typer.Exit(1)

    # Instantiate coordinator and run
    import asyncio  # noqa: PLC0415

    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.curator.coordinator import Coordinator, CuratorLockError  # noqa: PLC0415

    config = load_config(project_root)
    coordinator = Coordinator(project_root, config)

    try:
        report = asyncio.run(coordinator.run(scope=resolved_scope, check=check, dry_run=dry_run))
    except CuratorLockError as exc:
        error(str(exc))
        raise typer.Exit(1) from None

    # Render output
    from lexibrary.services.curate_render import (  # noqa: PLC0415
        render_dry_run,
        render_summary,
    )

    _dispatch = {"info": info, "warn": warn, "error": error}

    if dry_run:
        # Compute estimated LLM calls from dispatched items
        estimated_llm = sum(1 for d in (report.sub_agent_calls or {}).values() if d > 0)
        lines = render_dry_run(
            checked=report.checked,
            dispatched_count=report.fixed,  # In dry-run, "fixed" counts dispatched stubs
            deferred_count=report.deferred,
            sub_agent_calls=report.sub_agent_calls,
            estimated_llm_calls=estimated_llm,
        )
    else:
        lines = render_summary(
            checked=report.checked,
            fixed=report.fixed,
            deferred=report.deferred,
            errored=report.errored,
            sub_agent_calls=report.sub_agent_calls,
            report_path=report.report_path,
            stubbed=report.stubbed,
            verbose=verbose,
            dispatched_details=report.dispatched_details,
        )

    for level, msg in lines:
        _dispatch[level](msg)

    # Exit non-zero if there were errors
    if report.errored > 0:
        raise typer.Exit(1)


def _handle_last_run(project_root: Path, *, verbose: bool = False) -> None:
    """Read and display the most recent curator report."""
    from lexibrary.services.curate_render import render_last_run  # noqa: PLC0415

    reports_dir = project_root / ".lexibrary" / "curator" / "reports"
    if not reports_dir.is_dir():
        info("No previous curator runs found.")
        return

    report_files = sorted(reports_dir.glob("*.json"))
    if not report_files:
        info("No previous curator runs found.")
        return

    latest = report_files[-1]

    _dispatch = {"info": info, "warn": warn, "error": error}
    for level, msg in render_last_run(latest, verbose=verbose):
        _dispatch[level](msg)
