"""Shared CLI helpers used by both lexi and lexictl apps."""

from __future__ import annotations

import json as _json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from lexibrary.cli._output import error, info, warn
from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.root import find_project_root

if TYPE_CHECKING:
    from lexibrary.validator.report import ValidationIssue


def require_project_root() -> Path:
    """Resolve the project root or exit with a friendly error."""
    try:
        return find_project_root()
    except LexibraryNotFoundError:
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None


def _stdout_is_tty() -> bool:
    """Thin wrapper around ``sys.stdout.isatty()`` for easier test patching.

    ``typer.testing.CliRunner`` swaps ``sys.stdout`` for a captured buffer,
    so patching the global ``sys.stdout.isatty`` attribute from test code
    does not affect calls made through the module-level ``sys`` reference
    here. Wrapping the call in a named function lets tests monkey-patch
    the wrapper directly (``patch("lexibrary.cli._shared._stdout_is_tty",
    return_value=True)``) without touching stdout capture.
    """
    return sys.stdout.isatty()


def stub(name: str) -> None:
    """Print a standard stub message for unimplemented commands."""
    require_project_root()
    warn(f"Not yet implemented. ({name})")


# ---------------------------------------------------------------------------
# Shared command implementations
# ---------------------------------------------------------------------------


def _run_validate(
    project_root: Path,
    *,
    severity: str | None = None,
    check: str | None = None,
    json_output: bool = False,
    ci_mode: bool = False,
    fix: bool = False,
    interactive: bool = False,
) -> int:
    """Run validation checks and render output.

    Accepts parsed CLI args, calls ``validate_library()``, renders the
    results via plain text or JSON, and returns the process exit code.

    Args:
        project_root: Resolved project root directory.
        severity: Minimum severity to report (``"error"``, ``"warning"``,
            or ``"info"``).  ``None`` means all severities.
        check: Run only the named check.  ``None`` means all checks.
        json_output: When ``True``, output results as JSON instead of
            plain tables.
        ci_mode: When ``True``, output a compact single-line summary
            suitable for CI pipelines.
        fix: When ``True``, attempt to auto-fix fixable issues after
            validation.
        interactive: When ``True`` (requires ``fix=True`` and a TTY),
            route issues whose ``check`` is in
            :data:`lexibrary.validator.fixes.ESCALATION_CHECKS` through a
            per-issue prompt loop (``[i]gnore [d]eprecate [r]efresh
            [s]kip-remaining [q]uit``) instead of the autonomous
            ``FIXERS`` dispatch.  The prompt dispatches to the matching
            ``deprecate_*`` / ``refresh_*`` lifecycle helper. Non-TTY +
            ``interactive=True`` exits 1 with guidance.

    Returns:
        Exit code: 0 = clean, 1 = errors, 2 = warnings only.

    Raises:
        typer.Exit: With code 1 when ``check`` names an unknown check,
            ``severity`` is not a valid severity level, or
            ``interactive=True`` is passed with stdout not a TTY.
    """
    from lexibrary.validator import AVAILABLE_CHECKS, validate_library  # noqa: PLC0415

    lexibrary_dir = project_root / ".lexibrary"

    try:
        report = validate_library(
            project_root,
            lexibrary_dir,
            severity_filter=severity,
            check_filter=check,
        )
    except ValueError as exc:
        error(str(exc))
        # Show available checks if an unknown check was requested
        if check is not None and check not in AVAILABLE_CHECKS:
            info("Available checks: " + ", ".join(sorted(AVAILABLE_CHECKS)))
        raise typer.Exit(1) from None

    # CI mode: compact single-line output
    if ci_mode:
        counts = report.counts_by_severity()
        print(  # noqa: T201
            f"lexibrary-validate: errors={counts['error']}"
            f" warnings={counts['warning']}"
            f" info={counts['info']}"
        )
        return report.exit_code()

    # Fix mode: run fixers after validation
    if fix:
        from lexibrary.config.loader import load_config  # noqa: PLC0415
        from lexibrary.validator.fixes import (  # noqa: PLC0415
            DESTRUCTIVE_CHECKS,
            ESCALATION_CHECKS,
            FIXERS,
        )

        # curator-4 Group 17: TTY guard for ``--interactive``.
        # Escalation prompts require a real terminal to collect operator
        # input. When stdout is redirected (CI, pipes, captured test
        # harnesses) we refuse the request up-front with an actionable
        # message rather than silently fall back to autonomous dispatch.
        if interactive and not _stdout_is_tty():
            error(
                "--interactive requires a terminal; re-run without --interactive, "
                "or administrators can use `lexictl curate resolve --batch-ignore-all`"
            )
            raise typer.Exit(1)

        config = load_config(project_root)
        fixed_count = 0
        refreshed_count = 0
        deprecated_count = 0
        ignored_count = 0

        # Deduplicate: when both ``orphaned_designs`` and ``orphan_artifacts``
        # fire for the same artifact path, keep only the ``orphaned_designs``
        # issue because its fixer applies the proper deprecation workflow rather
        # than hard-deleting the file.  This pair-specific dedup is intentionally
        # narrow; a general "skip already-fixed paths" guard follows in the fixer
        # loops below.
        _preferred_check = "orphaned_designs"
        _subordinate_check = "orphan_artifacts"
        _preferred_paths = {
            issue.artifact for issue in report.issues if issue.check == _preferred_check
        }
        deduped_issues = [
            issue
            for issue in report.issues
            if not (issue.check == _subordinate_check and issue.artifact in _preferred_paths)
        ]

        total_issues = len(deduped_issues)

        # Partition fixable issues into three buckets.
        # Destructive fixes gate behind a y/N confirmation. Escalation checks
        # (curator-4 Group 17) are routed through the per-issue 3-option
        # prompt loop when ``--interactive`` is set; otherwise they fall
        # through to the standard ``FIXERS`` dispatch where the
        # ``escalate_*`` fixers write IWH signals and return
        # ``outcome_hint="escalation_required"``.
        destructive_issues = [
            issue
            for issue in deduped_issues
            if issue.check in DESTRUCTIVE_CHECKS and issue.check in FIXERS
        ]
        escalation_issues = [
            issue
            for issue in deduped_issues
            if issue.check in ESCALATION_CHECKS and issue.check not in DESTRUCTIVE_CHECKS
        ]
        safe_issues = [
            issue
            for issue in deduped_issues
            if issue.check not in DESTRUCTIVE_CHECKS and issue.check not in ESCALATION_CHECKS
        ]

        # curator-4 Group 17: interactive escalation loop. Runs BEFORE the
        # ``FIXERS`` dispatch so escalation issues are consumed by the
        # operator prompt rather than by the ``escalate_*`` fixers (which
        # would write IWH breadcrumbs we do not want in an interactive run).
        quit_requested = False
        if interactive and escalation_issues:
            (
                handled,
                refreshed_delta,
                deprecated_delta,
                ignored_delta,
                quit_requested,
            ) = _run_escalation_prompts(escalation_issues, project_root)
            refreshed_count += refreshed_delta
            deprecated_count += deprecated_delta
            ignored_count += ignored_delta
            # Any escalation issues left unhandled (quit early) are counted
            # in the manual bucket via ``total_issues - handled_total`` below.

        # Gate destructive fixes behind a single user confirmation.
        run_destructive = False
        if destructive_issues and not quit_requested:
            warn(f"{len(destructive_issues)} issue(s) require deleting files:")
            for issue in destructive_issues:
                warn(f"  {issue.check}: {issue.artifact}")
            run_destructive = typer.confirm(
                f"\nDelete {len(destructive_issues)} file(s)? [y/N]",
                default=False,
            )
            if not run_destructive:
                info("Skipping all destructive fixes.")

        # Non-interactive runs (or runs without ``--interactive``): route
        # escalation issues through the standard ``FIXERS`` dispatch. The
        # ``escalate_*`` fixers handle IWH signalling + the
        # ``escalation_required`` outcome hint; the coordinator bridges
        # those into ``PendingDecision`` entries when invoked by curator.
        non_destructive_issues: list[ValidationIssue] = list(safe_issues)
        if not interactive:
            non_destructive_issues.extend(escalation_issues)

        # Run non-destructive fixers unconditionally.
        if not quit_requested:
            for issue in non_destructive_issues:
                fixer = FIXERS.get(issue.check)
                if fixer is not None:
                    result = fixer(issue, project_root, config)
                    if result.fixed:
                        info(f"  [FIXED] {issue.check}: {result.message}")
                        fixed_count += 1
                    else:
                        info(f"  [SKIP] {issue.check}: {result.message}")
                else:
                    info(f"  [SKIP] {issue.check}: no auto-fix available")

        # Run destructive fixers only when the user confirmed.
        if not quit_requested:
            for issue in destructive_issues:
                if run_destructive:
                    fixer = FIXERS.get(issue.check)
                    if fixer is not None:
                        result = fixer(issue, project_root, config)
                        if result.fixed:
                            info(f"  [FIXED] {issue.check}: {result.message}")
                            fixed_count += 1
                        else:
                            info(f"  [SKIP] {issue.check}: {result.message}")
                    else:
                        info(f"  [SKIP] {issue.check}: no auto-fix available")
                else:
                    info(f"  [SKIP] {issue.check}: skipped (destructive fix not confirmed)")

        handled_total = fixed_count + refreshed_count + deprecated_count + ignored_count
        manual_count = total_issues - handled_total
        info("")
        if interactive:
            info(
                f"fixed: {fixed_count}, refreshed: {refreshed_count}, "
                f"deprecated: {deprecated_count}, ignored: {ignored_count}, "
                f"manual: {manual_count}"
            )
        else:
            info(
                f"Fixed {fixed_count} of {total_issues} issues."
                f" {manual_count} require manual attention."
            )
        return report.exit_code()

    if json_output:
        info(_json.dumps(report.to_dict(), indent=2))
    else:
        report.render()

    return report.exit_code()


# ---------------------------------------------------------------------------
# curator-4 Group 17: interactive escalation prompt loop
# ---------------------------------------------------------------------------


def _resolve_escalation_artifact_path(
    check: str,
    artifact: str,
    project_root: Path,
) -> Path | None:
    """Resolve an escalation issue's artifact string to an on-disk path.

    Mirrors the path-resolution logic used by the ``escalate_*`` fixers in
    :mod:`lexibrary.validator.fixes` so the interactive prompt loop acts on
    the same file the autonomous path would have acted on.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR  # noqa: PLC0415

    if check in {"orphan_concepts", "stale_concept"}:
        # ``check_orphan_concepts`` / ``check_stale_concepts`` emit
        # ``"concepts/<title>"`` (no ``.md`` suffix); look up by title.
        from lexibrary.wiki.index import ConceptIndex  # noqa: PLC0415

        concepts_dir = project_root / LEXIBRARY_DIR / "concepts"
        if not concepts_dir.is_dir():
            return None
        title = artifact
        prefix = "concepts/"
        if title.startswith(prefix):
            title = title[len(prefix) :]
        index = ConceptIndex.load(concepts_dir)
        concept = index.find(title)
        if concept is None or concept.file_path is None:
            return None
        return concept.file_path

    if check == "convention_stale":
        # ``check_convention_stale`` emits the artifact relative to
        # ``.lexibrary/`` (e.g. ``"conventions/foo.md"``).
        return project_root / LEXIBRARY_DIR / artifact

    if check == "playbook_staleness":
        # ``check_playbook_staleness`` emits the artifact relative to
        # the project root (e.g. ``".lexibrary/playbooks/foo.md"``).
        return project_root / artifact

    return None


def _run_escalation_prompts(
    escalation_issues: list[ValidationIssue],
    project_root: Path,
) -> tuple[int, int, int, int, bool]:
    """Walk ``escalation_issues`` with the shared 3-option prompt loop.

    Delegates per-issue handling to
    :func:`lexibrary.cli._escalation.resolve_pending_decision` so the
    interactive ``lexi validate --fix --interactive`` flow (this caller)
    and the admin ``lexictl curate resolve`` command share one
    implementation (curator-4 Group 18).

    Each ``ValidationIssue`` is synthesised into an in-memory
    :class:`~lexibrary.curator.models.PendingDecision` so the helper
    accepts a uniform shape regardless of the originating code path.
    The helper handles the prompt, the lifecycle dispatch, and the
    ``[s]kip-remaining`` / ``[q]uit`` replies; this wrapper translates
    its outcomes back into the legacy ``(handled, refreshed, deprecated,
    ignored, quit_requested)`` tuple the caller expects.

    Returns
    -------
    tuple[int, int, int, int, bool]
        ``(handled, refreshed, deprecated, ignored, quit_requested)``.
        ``handled`` is the sum of the three action counters plus ignored;
        ``quit_requested`` signals that remaining fix paths should abort.
    """
    from lexibrary.cli._escalation import (  # noqa: PLC0415
        _ESCALATION_DISPATCH,
        resolve_pending_decision,
    )
    from lexibrary.config.loader import load_config  # noqa: PLC0415
    from lexibrary.curator.models import PendingDecision  # noqa: PLC0415

    # Config is used for future gates (e.g. risk-override allow-list);
    # load once here so each per-issue call sees a consistent view.
    config = load_config(project_root)

    refreshed = 0
    deprecated = 0
    ignored = 0
    skip_remaining = False

    for issue in escalation_issues:
        if issue.check not in _ESCALATION_DISPATCH:
            warn(f"  [SKIP] {issue.check}: no interactive handler; count as ignored")
            ignored += 1
            continue

        if skip_remaining:
            ignored += 1
            continue

        path = _resolve_escalation_artifact_path(issue.check, issue.artifact, project_root)
        if path is None or not path.exists():
            warn(f"  [SKIP] {issue.check}: {issue.artifact} — artifact not found on disk")
            ignored += 1
            continue

        # Synthesise a ``PendingDecision`` so the shared helper sees a
        # uniform shape. ``iwh_path`` is ``None`` here because the
        # interactive validate flow never wrote a breadcrumb -- the
        # autonomous ``escalate_*`` fixers do.
        decision = PendingDecision(
            check=issue.check,
            path=path,
            message=issue.message,
            suggested_actions=["ignore", "deprecate", "refresh"],
            iwh_path=None,
        )

        outcome = resolve_pending_decision(
            decision,
            project_root,
            config,
            auto_ignore=False,
            # No breadcrumb to clean up in the interactive validate flow.
            delete_iwh_on_success=False,
        )

        if outcome.action == "quit":
            return (refreshed + deprecated + ignored, refreshed, deprecated, ignored, True)
        if outcome.skip_remaining:
            skip_remaining = True
        if outcome.action == "deprecated":
            deprecated += 1
        elif outcome.action == "refreshed":
            refreshed += 1
        else:
            ignored += 1

    return (refreshed + deprecated + ignored, refreshed, deprecated, ignored, False)


def load_dotenv_if_configured() -> None:
    """Load ``.env`` at CLI startup when ``api_key_source`` is ``"dotenv"``.

    Reads raw YAML from the project config (no Pydantic validation) to
    check ``llm.api_key_source`` before full config initialisation.
    When the value equals ``"dotenv"``, calls
    ``load_dotenv(project_root / ".env", override=False)`` so that env
    vars already set in the shell take precedence.

    All errors are silently swallowed -- the normal project-not-found or
    config-not-found error surfaces later when a command actually runs.
    """
    try:
        import yaml  # noqa: PLC0415
        from dotenv import load_dotenv  # noqa: PLC0415

        project_root = find_project_root()
        config_path = project_root / ".lexibrary" / "config.yaml"
        if not config_path.exists():
            return

        with open(config_path) as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            return

        llm_section = raw.get("llm")
        if not isinstance(llm_section, dict):
            return

        if llm_section.get("api_key_source") == "dotenv":
            load_dotenv(project_root / ".env", override=False)
    except Exception:  # noqa: BLE001
        # Silently skip -- errors will surface later during normal
        # config loading when a command actually runs.
        pass
