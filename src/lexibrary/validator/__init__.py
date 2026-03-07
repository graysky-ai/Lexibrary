"""Validator module -- library health checks and validation reporting."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from lexibrary.errors import ErrorSummary
from lexibrary.exceptions import LexibraryError
from lexibrary.validator.checks import (
    check_aindex_coverage,
    check_bidirectional_deps,
    check_comment_accumulation,
    check_concept_frontmatter,
    check_convention_consistent_violation,
    check_convention_gap,
    check_convention_orphaned_scope,
    check_convention_stale,
    check_dangling_links,
    check_deprecated_concept_usage,
    check_deprecated_ttl,
    check_file_existence,
    check_forward_dependencies,
    check_hash_freshness,
    check_lookup_token_budget_exceeded,
    check_orphan_artifacts,
    check_orphan_concepts,
    check_orphaned_designs,
    check_orphaned_iwh_signals,
    check_resolved_post_staleness,
    check_stack_staleness,
    check_stale_concepts,
    check_supersession_candidates,
    check_token_budgets,
    check_wikilink_resolution,
    find_orphaned_aindex,
    find_orphaned_iwh,
)
from lexibrary.validator.report import (
    Severity,
    ValidationIssue,
    ValidationReport,
    ValidationSummary,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AVAILABLE_CHECKS",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSummary",
    "validate_library",
]

# Type alias for check functions
CheckFn = Callable[[Path, Path], list[ValidationIssue]]

# Registry of all available checks, keyed by name.
# Each entry maps to (check_function, default_severity).
# The default_severity is the severity the check is designed to produce;
# it determines which checks are included when severity_filter is applied.
AVAILABLE_CHECKS: dict[str, tuple[CheckFn, Severity]] = {
    "wikilink_resolution": (check_wikilink_resolution, "error"),
    "file_existence": (check_file_existence, "error"),
    "concept_frontmatter": (check_concept_frontmatter, "error"),
    "hash_freshness": (check_hash_freshness, "warning"),
    "token_budgets": (check_token_budgets, "warning"),
    "orphan_concepts": (check_orphan_concepts, "warning"),
    "deprecated_concept_usage": (check_deprecated_concept_usage, "warning"),
    "orphaned_designs": (check_orphaned_designs, "warning"),
    "forward_dependencies": (check_forward_dependencies, "info"),
    "stack_staleness": (check_stack_staleness, "info"),
    "resolved_post_staleness": (check_resolved_post_staleness, "info"),
    "aindex_coverage": (check_aindex_coverage, "info"),
    "bidirectional_deps": (check_bidirectional_deps, "info"),
    "dangling_links": (check_dangling_links, "info"),
    "orphan_artifacts": (check_orphan_artifacts, "info"),
    "orphaned_aindex": (find_orphaned_aindex, "warning"),
    "orphaned_iwh": (find_orphaned_iwh, "info"),
    "comment_accumulation": (check_comment_accumulation, "info"),
    "deprecated_ttl": (check_deprecated_ttl, "info"),
    "stale_concept": (check_stale_concepts, "info"),
    "supersession_candidate": (check_supersession_candidates, "info"),
    "convention_orphaned_scope": (check_convention_orphaned_scope, "warning"),
    "convention_stale": (check_convention_stale, "info"),
    "convention_gap": (check_convention_gap, "info"),
    "convention_consistent_violation": (check_convention_consistent_violation, "info"),
    "lookup_token_budget_exceeded": (check_lookup_token_budget_exceeded, "info"),
    "orphaned_iwh_signals": (check_orphaned_iwh_signals, "info"),
}

# Severity levels ordered from most to least severe.
_SEVERITY_ORDER: dict[Severity, int] = {
    "error": 0,
    "warning": 1,
    "info": 2,
}


def validate_library(
    project_root: Path,
    lexibrary_dir: Path,
    *,
    severity_filter: str | None = None,
    check_filter: str | None = None,
) -> ValidationReport:
    """Run all validation checks and return an aggregated report.

    Runs the registered checks, aggregates their issues into a single
    ``ValidationReport``, and optionally filters by severity or check name.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.
        severity_filter: Only include checks at this severity level or above.
            Valid values: ``"error"`` (errors only), ``"warning"`` (errors +
            warnings), ``"info"`` (all -- the default when ``None``).
        check_filter: Run only the named check. Must be a key in
            ``AVAILABLE_CHECKS``. When ``None``, all checks are run.

    Returns:
        A ValidationReport with all discovered issues.

    Raises:
        ValueError: If ``check_filter`` names an unknown check or
            ``severity_filter`` is not a valid severity level.
    """
    # Validate severity_filter
    if severity_filter is not None and severity_filter not in _SEVERITY_ORDER:
        valid = ", ".join(sorted(_SEVERITY_ORDER, key=_SEVERITY_ORDER.get))  # type: ignore[arg-type]
        msg = f"Invalid severity_filter: {severity_filter!r}. Must be one of: {valid}"
        raise ValueError(msg)

    # Validate check_filter
    if check_filter is not None and check_filter not in AVAILABLE_CHECKS:
        valid_checks = ", ".join(sorted(AVAILABLE_CHECKS))
        msg = f"Unknown check: {check_filter!r}. Available checks: {valid_checks}"
        raise ValueError(msg)

    # Determine which checks to run
    checks_to_run: dict[str, tuple[CheckFn, Severity]]
    if check_filter is not None:
        checks_to_run = {check_filter: AVAILABLE_CHECKS[check_filter]}
    else:
        checks_to_run = dict(AVAILABLE_CHECKS)

    # Apply severity filter: only run checks whose default severity is at or
    # above (more severe than) the threshold.
    if severity_filter is not None:
        threshold = _SEVERITY_ORDER[severity_filter]  # type: ignore[index]
        checks_to_run = {
            name: (fn, sev)
            for name, (fn, sev) in checks_to_run.items()
            if _SEVERITY_ORDER[sev] <= threshold
        }

    # Run selected checks and aggregate issues
    all_issues: list[ValidationIssue] = []
    error_summary = ErrorSummary()
    for name, (check_fn, _sev) in checks_to_run.items():
        try:
            issues = check_fn(project_root, lexibrary_dir)
            all_issues.extend(issues)
        except LexibraryError as exc:
            logger.warning("Validation check %r failed", name, exc_info=True)
            error_summary.add("validate", exc, path=name)
        except Exception as exc:
            logger.warning("Validation check %r failed unexpectedly", name, exc_info=True)
            error_summary.add("validate", exc, path=name)

    report = ValidationReport(issues=all_issues)
    report.error_summary = error_summary
    return report
