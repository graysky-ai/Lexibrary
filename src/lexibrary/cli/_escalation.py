"""Shared escalation-resolution helpers for the interactive CLI flows.

Exposes a single entry point -- :func:`resolve_pending_decision` -- used by
both ``lexi validate --fix --interactive`` (``cli/_shared.py``) and
``lexictl curate resolve`` (``cli/curate.py``) so the 3-option prompt loop
(``[i]gnore [d]eprecate [r]efresh``) lives in one place.

The helper accepts a :class:`~lexibrary.curator.models.PendingDecision` --
the canonical shape of an operator-resolution queue entry -- plus the
project root and project config. Both call sites construct this shape
even when starting from a raw ``ValidationIssue`` (the interactive
validate flow synthesises a decision per issue) so the resolution logic
is uniform.

All user-facing output flows through :mod:`lexibrary.cli._output` helpers
per project conventions; there are no bare ``print()`` or Rich calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import typer

from lexibrary.cli._output import info, warn

if TYPE_CHECKING:
    from lexibrary.config.schema import LexibraryConfig
    from lexibrary.curator.models import PendingDecision


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------


# Maps escalation ``check`` values to the deprecate reason code and the
# refresh-helper key used to select the matching ``refresh_*`` lifecycle
# helper. Kept as a key rather than a direct callable reference to defer
# lifecycle imports until the interactive branch actually runs.
_ESCALATION_DISPATCH: dict[str, tuple[str, str]] = {
    "orphan_concepts": ("no_inbound_links", "orphan_concept"),
    "stale_concept": ("all_linked_files_missing", "stale_concept"),
    "convention_stale": ("scope_path_missing", "convention_stale"),
    "playbook_staleness": ("past_last_verified", "playbook_staleness"),
}


# ---------------------------------------------------------------------------
# Outcome value object
# ---------------------------------------------------------------------------


@dataclass
class EscalationOutcome:
    """Structured result of a single ``resolve_pending_decision`` invocation.

    Attributes:
        action: What the operator chose. ``"ignored"`` covers both ``i``
            and ``s`` (skip-remaining) replies as well as any unrecognised
            input (default behaviour mirrors the original
            ``_run_escalation_prompts``). ``"quit"`` signals the caller
            should abort the outer validate/resolve loop.
        skip_remaining: ``True`` when the operator chose ``s`` --
            subsequent decisions in the batch SHOULD be counted as
            ignored without further prompting.
    """

    action: Literal["ignored", "deprecated", "refreshed", "quit", "skipped"]
    skip_remaining: bool = False


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def _prompt_new_scope(project_root: Path) -> str | None:
    """Collect + validate a new scope string for ``refresh_convention_stale``.

    Loops until the operator provides a scope where every non-``project``
    path exists on disk, or submits blank input to abort the refresh. The
    validation uses the same ``split_scope`` grammar the lifecycle helper
    enforces, so live rejections match the helper's eventual acceptance.
    """
    from lexibrary.artifacts.convention import split_scope  # noqa: PLC0415

    while True:
        raw: str = typer.prompt(
            "    new scope (comma-separated paths, or 'project'; blank to abort)",
            default="",
            show_default=False,
        )
        candidate = raw.strip()
        if not candidate:
            return None

        missing: list[str] = []
        for path in split_scope(candidate):
            if path == "project":
                continue
            if not (project_root / path).exists():
                missing.append(path)

        if missing:
            warn(f"    scope path(s) do not exist: {', '.join(missing)}")
            continue
        return candidate


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def resolve_pending_decision(
    decision: PendingDecision,
    project_root: Path,
    config: LexibraryConfig,
    *,
    auto_ignore: bool = False,
    delete_iwh_on_success: bool = True,
) -> EscalationOutcome:
    """Walk the 3-option prompt loop for a single ``PendingDecision``.

    Shared by ``lexi validate --fix --interactive`` and
    ``lexictl curate resolve`` so both admin-facing and agent-facing
    escalation surfaces use one implementation.

    Args:
        decision: The pending decision to resolve. Carries the originating
            check name, the resolved artifact path on disk, the operator
            message, and (optionally) the IWH breadcrumb path.
        project_root: Absolute project root for path resolution.
        config: Project configuration (unused today but plumbed through
            to keep the call signature stable for future gates such as
            config-driven auto-approve).
        auto_ignore: When ``True``, bypass the interactive prompt and
            treat the decision as ignored. Used by
            ``lexictl curate resolve --batch-ignore-all`` for CI runs.
        delete_iwh_on_success: When ``True`` (interactive default),
            remove the matching IWH breadcrumb after a successful
            resolve/deprecate/refresh. When ``False`` (batch-ignore-all),
            preserve the breadcrumb so operators can still see what was
            flagged.

    Returns:
        An :class:`EscalationOutcome` describing which action was taken
        and whether the caller should skip remaining decisions.
    """
    # Lifecycle helper imports stay local so importing this module is
    # cheap for the non-interactive code paths.
    from lexibrary.lifecycle.concept_deprecation import deprecate_concept  # noqa: PLC0415
    from lexibrary.lifecycle.convention_deprecation import deprecate_convention  # noqa: PLC0415
    from lexibrary.lifecycle.playbook_deprecation import deprecate_playbook  # noqa: PLC0415
    from lexibrary.lifecycle.refresh import (  # noqa: PLC0415
        refresh_convention_stale,
        refresh_orphan_concept,
        refresh_playbook_staleness,
        refresh_stale_concept,
    )

    check = decision.check
    path = decision.path
    message = decision.message

    # Defensive: the caller is expected to pre-filter on membership in
    # ``ESCALATION_CHECKS``, but misconfiguration should count as ignored
    # rather than crash the outer loop.
    if check not in _ESCALATION_DISPATCH:
        warn(f"  [SKIP] {check}: no interactive handler; count as ignored")
        return EscalationOutcome(action="ignored")

    if not path.exists():
        warn(f"  [SKIP] {check}: {path} — artifact not found on disk")
        return EscalationOutcome(action="ignored")

    deprecate_reason, refresh_key = _ESCALATION_DISPATCH[check]

    # Batch-ignore-all short-circuit for admin CI runs. Emit an info line
    # so the report shows that the decision was observed + ignored, then
    # return without touching the IWH breadcrumb.
    if auto_ignore:
        info(f"[{check}] {path.name} — {message}")
        info(f"  [IGNORED] {check}: {path.name} (batch-ignore-all)")
        return EscalationOutcome(action="ignored")

    info(f"\n[{check}] {path.name} — {message}")
    choice = (
        typer.prompt(
            "  [i]gnore [d]eprecate [r]efresh [s]kip-remaining [q]uit",
            default="i",
        )
        .strip()
        .lower()
    )

    if choice in ("q", "quit"):
        return EscalationOutcome(action="quit", skip_remaining=True)

    if choice in ("s", "skip-remaining", "skip"):
        return EscalationOutcome(action="ignored", skip_remaining=True)

    if choice in ("d", "deprecate"):
        if check in ("orphan_concepts", "stale_concept"):
            deprecate_concept(path, reason=deprecate_reason)
        elif check == "convention_stale":
            deprecate_convention(path, reason=deprecate_reason)
        elif check == "playbook_staleness":
            deprecate_playbook(path, reason=deprecate_reason)
        info(f"  [DEPRECATED] {check}: {path.name}")
        _cleanup_iwh(decision.iwh_path, delete=delete_iwh_on_success)
        return EscalationOutcome(action="deprecated")

    if choice in ("r", "refresh"):
        if refresh_key == "orphan_concept":
            refresh_orphan_concept(path)
            info(f"  [REFRESHED] {check}: {path.name} — last_verified bumped")
        elif refresh_key == "stale_concept":
            pruned = refresh_stale_concept(path, project_root)
            info(f"  [REFRESHED] {check}: {path.name} — {pruned} linked_files entry/entries pruned")
        elif refresh_key == "convention_stale":
            new_scope = _prompt_new_scope(project_root)
            if new_scope is None:
                info(f"  [SKIP] {check}: refresh aborted (no scope supplied)")
                return EscalationOutcome(action="ignored")
            try:
                refresh_convention_stale(path, project_root, new_scope=new_scope)
            except (FileNotFoundError, ValueError) as exc:
                # ``_prompt_new_scope`` pre-validates existence, so this
                # only fires on the fully-stale-new-equals-old ValueError
                # branch. Count as ignored; the operator can retry.
                warn(f"  [SKIP] {check}: refresh rejected — {exc}")
                return EscalationOutcome(action="ignored")
            info(f"  [REFRESHED] {check}: {path.name} — scope set to '{new_scope}'")
        elif refresh_key == "playbook_staleness":
            refresh_playbook_staleness(path)
            info(f"  [REFRESHED] {check}: {path.name} — last_verified bumped")
        _cleanup_iwh(decision.iwh_path, delete=delete_iwh_on_success)
        return EscalationOutcome(action="refreshed")

    # Default (``i`` or any unrecognised input): ignore.
    info(f"  [IGNORED] {check}: {path.name}")
    return EscalationOutcome(action="ignored")


# ---------------------------------------------------------------------------
# IWH breadcrumb cleanup
# ---------------------------------------------------------------------------


def _cleanup_iwh(iwh_path: Path | None, *, delete: bool) -> None:
    """Remove the escalation breadcrumb after a successful resolution.

    Best-effort: missing files are no-ops. Errors during ``unlink`` are
    surfaced as a warning so the caller knows the breadcrumb is still on
    disk, but do not fail the resolution -- the operator's decision
    already took effect on the artifact.
    """
    if iwh_path is None or not delete:
        return
    if not iwh_path.exists():
        return
    try:
        iwh_path.unlink()
    except OSError as exc:
        warn(f"    could not remove IWH breadcrumb at {iwh_path}: {exc}")
