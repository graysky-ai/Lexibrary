"""Validation bridge — translate curator triage items into validator auto-fixes.

Bridges the curator's dispatch phase and the :mod:`lexibrary.validator.fixes`
registry.  A :class:`TriageItem` classified as a validation issue carries its
originating :class:`CollectItem`, which holds the validator's ``check`` name,
``severity``, ``path`` and ``message``.  The bridge reconstructs a
``ValidationIssue`` from those fields, looks up the matching fixer in
``FIXERS``, runs it, and maps the resulting ``FixResult`` onto a
``SubAgentResult`` with an appropriate ``outcome``:

- No fixer registered for the check → ``outcome="no_fixer"``.
- Fixer raised an exception            → ``outcome="errored"``.
- ``FixResult.fixed`` is ``True``      → ``outcome="fixed"``.
- ``FixResult.fixed`` is ``False``     → ``outcome="fixer_failed"``.

The bridge preserves the narrow per-check ``action_key`` (e.g.
``"fix_hash_freshness"``) on the returned ``SubAgentResult`` instead of the
umbrella ``"autofix_validation_issue"`` key — honest counters and per-check
reporting depend on this distinction.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from lexibrary.curator.models import SubAgentResult, TriageItem
from lexibrary.validator.fixes import FIXERS
from lexibrary.validator.report import ValidationIssue

if TYPE_CHECKING:
    from lexibrary.config.schema import LexibraryConfig

logger = logging.getLogger(__name__)


def fix_validation_issue(
    item: TriageItem,
    project_root: Path,
    config: LexibraryConfig,
) -> SubAgentResult:
    """Route a validation triage item to the matching validator auto-fixer.

    Args:
        item: The triage item whose ``source_item`` carries the original
            validator metadata (``check``, ``severity``, ``path``, ``message``).
        project_root: Project root passed through to the fixer.
        config: Project configuration passed through to the fixer.

    Returns:
        A :class:`SubAgentResult` whose ``action_key`` is the narrow per-check
        key from ``item.action_key`` and whose ``outcome`` reflects the fixer
        result (``"fixed"``, ``"fixer_failed"``, ``"no_fixer"``, or
        ``"errored"``).
    """
    source_item = item.source_item
    check = source_item.check
    path = source_item.path

    # Look up the concrete fixer.
    fixer = FIXERS.get(check)
    if fixer is None:
        message = f"no_fixer_registered: {check or '<empty>'}"
        return SubAgentResult(
            success=False,
            action_key=item.action_key,
            path=path,
            message=message,
            llm_calls=0,
            outcome="no_fixer",
        )

    # Reconstruct a ValidationIssue for the fixer.  ``artifact`` is a string;
    # use POSIX-style for portability across platforms.  Validation collection
    # stores ``path`` as the raw artifact path from the original
    # ``ValidationIssue.artifact``, so we faithfully round-trip it here.
    artifact = path.as_posix() if path is not None else ""
    issue = ValidationIssue(
        severity=source_item.severity,
        check=check,
        message=source_item.message,
        artifact=artifact,
    )

    try:
        result = fixer(issue, project_root, config)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "validator fixer for check %r raised for artifact %r",
            check,
            artifact,
        )
        return SubAgentResult(
            success=False,
            action_key=item.action_key,
            path=path,
            message=f"fixer raised: {exc}",
            llm_calls=0,
            outcome="errored",
        )

    outcome: Literal["fixed", "fixer_failed"] = "fixed" if result.fixed else "fixer_failed"
    return SubAgentResult(
        success=bool(result.fixed),
        action_key=item.action_key,
        path=result.path,
        message=result.message,
        llm_calls=0,
        outcome=outcome,
    )
