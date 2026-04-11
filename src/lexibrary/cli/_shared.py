"""Shared CLI helpers used by both lexi and lexictl apps."""

from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from lexibrary.cli._output import error, info, warn
from lexibrary.exceptions import LexibraryNotFoundError
from lexibrary.utils.root import find_project_root


def require_project_root() -> Path:
    """Resolve the project root or exit with a friendly error."""
    try:
        return find_project_root()
    except LexibraryNotFoundError:
        error("No .lexibrary/ directory found. Run `lexictl init` to create one.")
        raise typer.Exit(1) from None


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

    Returns:
        Exit code: 0 = clean, 1 = errors, 2 = warnings only.

    Raises:
        typer.Exit: With code 1 when ``check`` names an unknown check or
            ``severity`` is not a valid severity level.
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
        from lexibrary.validator.fixes import DESTRUCTIVE_CHECKS, FIXERS  # noqa: PLC0415

        config = load_config(project_root)
        fixed_count = 0

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

        # Separate fixable issues into destructive and non-destructive buckets.
        destructive_issues = [
            issue
            for issue in deduped_issues
            if issue.check in DESTRUCTIVE_CHECKS and issue.check in FIXERS
        ]
        safe_issues = [issue for issue in deduped_issues if issue.check not in DESTRUCTIVE_CHECKS]

        # Gate destructive fixes behind a single user confirmation.
        run_destructive = False
        if destructive_issues:
            warn(f"{len(destructive_issues)} issue(s) require deleting files:")
            for issue in destructive_issues:
                warn(f"  {issue.check}: {issue.artifact}")
            run_destructive = typer.confirm(
                f"\nDelete {len(destructive_issues)} file(s)? [y/N]",
                default=False,
            )
            if not run_destructive:
                info("Skipping all destructive fixes.")

        # Run non-destructive fixers unconditionally.
        for issue in safe_issues:
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

        manual_count = total_issues - fixed_count
        info("")
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
