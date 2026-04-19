"""Curator CLI command group -- ``lexictl curate``.

The ``curate`` command group exposes two subcommands:

* ``run`` (default) -- thin wrapper over the coordinator pipeline. This
  is the original ``lexictl curate`` behaviour; ``lexictl curate`` with
  no subcommand resolves to ``run`` via Typer's ``invoke_without_command``
  callback so backward compatibility is preserved.
* ``resolve`` -- admin-only replay of ``CuratorReport.pending_decisions``
  through the same 3-option operator prompt used by
  ``lexi validate --fix --interactive``. Exposes ``--report`` to point at
  a specific report file and ``--batch-ignore-all`` for CI pipelines.

All user-facing output goes through :mod:`lexibrary.cli._output` helpers.
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from lexibrary.cli._output import error, hint, info, warn
from lexibrary.cli._shared import require_project_root

if TYPE_CHECKING:
    from lexibrary.curator.models import PendingDecision

# ---------------------------------------------------------------------------
# Typer sub-app
# ---------------------------------------------------------------------------


curate_app = typer.Typer(
    name="curate",
    help=(
        "Run the curator pipeline or replay pending operator decisions. "
        "Admin-only: agents must not invoke lexictl."
    ),
    rich_markup_mode=None,
    invoke_without_command=True,
    no_args_is_help=False,
)


@curate_app.callback()
def _curate_default(
    ctx: typer.Context,
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
    """Default callback -- runs the coordinator when no subcommand is given.

    Invoked for every ``lexictl curate`` call because the sub-app is created
    with ``invoke_without_command=True``. When the user explicitly selects
    a subcommand (``lexictl curate run`` / ``lexictl curate resolve``),
    ``ctx.invoked_subcommand`` is non-``None`` and this callback is a
    no-op so the named subcommand runs normally. Otherwise we delegate to
    :func:`run` so ``lexictl curate`` keeps its pre-subcommand behaviour.
    """
    if ctx.invoked_subcommand is not None:
        return

    _run_pipeline(
        scope=scope,
        check=check,
        dry_run=dry_run,
        last_run=last_run,
        verbose=verbose,
    )


@curate_app.command("run")
def run(
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
    _run_pipeline(
        scope=scope,
        check=check,
        dry_run=dry_run,
        last_run=last_run,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# Shared pipeline implementation
# ---------------------------------------------------------------------------


def _run_pipeline(
    *,
    scope: Path | None,
    check: str | None,
    dry_run: bool,
    last_run: bool,
    verbose: bool,
) -> None:
    """Core pipeline invocation shared by the default callback and ``run``.

    Extracted so ``lexictl curate`` (no subcommand) and ``lexictl curate run``
    exercise identical code paths -- guarantees the subcommand refactor in
    curator-4 Group 18 did not diverge behaviour.
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


# ---------------------------------------------------------------------------
# resolve subcommand (curator-4 Group 18)
# ---------------------------------------------------------------------------


@curate_app.command("resolve")
def resolve(
    *,
    report_path: Annotated[
        Path | None,
        typer.Option(
            "--report",
            help=(
                "Path to a specific curator report JSON file. "
                "Defaults to the most recent report under "
                ".lexibrary/curator/reports/."
            ),
        ),
    ] = None,
    batch_ignore_all: Annotated[
        bool,
        typer.Option(
            "--batch-ignore-all",
            help=(
                "Bypass the per-decision prompt; mark every pending "
                "decision as ignored. Intended for CI pipelines where an "
                "administrator wants to acknowledge the queue without "
                "making individual calls."
            ),
        ),
    ] = False,
) -> None:
    """Replay ``pending_decisions`` from a curator report through the prompt loop.

    Reads a curator report (latest by default, or ``--report PATH`` for a
    specific file), iterates ``pending_decisions``, and walks each entry
    through the same 3-option prompt (``[i]gnore [d]eprecate [r]efresh``)
    used by ``lexi validate --fix --interactive``.

    After a successful deprecate/refresh, the matching IWH breadcrumb
    (``iwh_path`` on the decision) is removed when running interactively.
    Under ``--batch-ignore-all``, the breadcrumb is preserved so operators
    can still discover what was flagged during a later manual review.

    This command is **admin-only** and is not exposed on the ``lexi``
    entrypoint; agents must not invoke ``lexictl`` per project rules.
    """
    from lexibrary.cli._escalation import resolve_pending_decision  # noqa: PLC0415
    from lexibrary.config.loader import load_config  # noqa: PLC0415

    project_root = require_project_root()
    config = load_config(project_root)

    selected = _select_report_path(project_root, override=report_path)
    if selected is None:
        return  # _select_report_path already printed an info line

    decisions = _load_pending_decisions(selected)
    if decisions is None:
        # Parse error: message already emitted. Exit non-zero so CI
        # callers notice the bad report.
        raise typer.Exit(1)

    if not decisions:
        info(f"No pending decisions in {selected.name}.")
        return

    info(f"Replaying {len(decisions)} pending decision(s) from {selected.name}.")

    ignored = 0
    deprecated = 0
    refreshed = 0
    skip_remaining = False
    quit_requested = False

    for decision in decisions:
        if skip_remaining and not batch_ignore_all:
            info(f"  [IGNORED] {decision.check}: {decision.path.name} (skip-remaining)")
            ignored += 1
            continue

        outcome = resolve_pending_decision(
            decision,
            project_root,
            config,
            auto_ignore=batch_ignore_all,
            # Preserve IWH breadcrumbs under --batch-ignore-all so the
            # signal is still visible to a later manual sweep. Interactive
            # runs clean up after a successful resolve/deprecate/refresh.
            delete_iwh_on_success=not batch_ignore_all,
        )

        if outcome.action == "quit":
            quit_requested = True
            break
        if outcome.skip_remaining:
            skip_remaining = True
        if outcome.action == "deprecated":
            deprecated += 1
        elif outcome.action == "refreshed":
            refreshed += 1
        else:
            ignored += 1

    _render_summary(
        total=len(decisions),
        ignored=ignored,
        deprecated=deprecated,
        refreshed=refreshed,
        quit_requested=quit_requested,
    )


# ---------------------------------------------------------------------------
# resolve -- helpers
# ---------------------------------------------------------------------------


def _select_report_path(project_root: Path, *, override: Path | None) -> Path | None:
    """Pick the report JSON to replay.

    When ``override`` is provided, validate it exists. Otherwise pick the
    most recent file under ``.lexibrary/curator/reports/``. Returns
    ``None`` when there's nothing to replay (and emits an info line so
    the user knows why).
    """
    if override is not None:
        resolved = override if override.is_absolute() else (Path.cwd() / override).resolve()
        if not resolved.exists():
            error(f"Report file not found: {override}")
            raise typer.Exit(1)
        if not resolved.is_file():
            error(f"Report path is not a file: {override}")
            raise typer.Exit(1)
        return resolved

    reports_dir = project_root / ".lexibrary" / "curator" / "reports"
    if not reports_dir.is_dir():
        info("No curator reports found. Run `lexictl curate` first.")
        return None

    report_files = sorted(reports_dir.glob("*.json"))
    if not report_files:
        info("No curator reports found. Run `lexictl curate` first.")
        return None

    return report_files[-1]


def _load_pending_decisions(report_path: Path) -> list[PendingDecision] | None:
    """Parse ``pending_decisions`` out of a curator report JSON file.

    Returns a list of :class:`PendingDecision` objects (possibly empty)
    on success, or ``None`` on parse / validation failure (the caller
    should exit non-zero in that case).
    """
    from lexibrary.curator.models import PendingDecision  # noqa: PLC0415

    try:
        raw = _json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        error(f"Could not read report {report_path}: {exc}")
        return None

    if not isinstance(raw, dict):
        error(f"Report at {report_path} is not a JSON object.")
        return None

    entries = raw.get("pending_decisions", [])
    if not isinstance(entries, list):
        error(f"Report at {report_path} has malformed pending_decisions (expected list).")
        return None

    decisions: list[PendingDecision] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            warn(f"  skipping malformed pending_decisions[{idx}] (not a JSON object)")
            continue
        try:
            decisions.append(PendingDecision.model_validate(entry))
        except Exception as exc:  # noqa: BLE001
            warn(f"  skipping pending_decisions[{idx}]: {exc}")
            continue
    return decisions


def _render_summary(
    *,
    total: int,
    ignored: int,
    deprecated: int,
    refreshed: int,
    quit_requested: bool,
) -> None:
    """Emit the final summary line for a ``resolve`` run."""
    handled = ignored + deprecated + refreshed
    unresolved = total - handled
    info("")
    info(
        f"resolved: {handled}/{total} "
        f"(ignored: {ignored}, deprecated: {deprecated}, refreshed: {refreshed}"
        + (f", unresolved: {unresolved}" if unresolved else "")
        + ")"
    )
    if quit_requested:
        warn("Resolve aborted early via [q]uit; remaining decisions left pending.")
