"""Consistency fix helpers for the curator coordinator (Phase 3 — group 8).

Every helper in this module implements a single :class:`FixInstruction`
action string emitted by :class:`lexibrary.curator.consistency.ConsistencyChecker`.
Helpers receive a :class:`TriageItem` and :class:`DispatchContext`, perform
the fix, and return a :class:`SubAgentResult` with
``outcome="fixed"`` / ``"fixer_failed"`` / ``"errored"``.

Design-file rewrites MUST go through
:func:`lexibrary.curator.write_contract.write_design_file_as_curator` --
no helper writes a design file directly.  The shared contract stamps
``updated_by="curator"``, recomputes ``source_hash``/``interface_hash``,
serializes, and atomically writes.

Non-design-file rewrites (deleting orphan ``.aindex`` / ``.comments.yaml``,
deleting orphan concepts, writing warning IWH signals for stale
conventions / playbooks) do not go through the design-file write
contract -- they are simple ``unlink``s or IWH writes.

Every helper SHALL be unit-testable without spinning up a full
coordinator; helpers receive only ``item`` and ``ctx`` so tests can
fabricate minimal stubs.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
)
from lexibrary.curator.models import SubAgentResult, TriageItem
from lexibrary.curator.write_contract import write_design_file_as_curator

if TYPE_CHECKING:
    from lexibrary.curator.dispatch_context import DispatchContext

logger = logging.getLogger(__name__)


CONSISTENCY_ACTION_KEYS: dict[str, str] = {
    # Wikilink hygiene
    "fix_broken_wikilink_fuzzy": "fix_broken_wikilink_fuzzy",
    "strip_unresolved_wikilink": "strip_unresolved_wikilink",
    # Identifier normalisation
    "resolve_slug_collision": "resolve_slug_collision",
    "resolve_alias_collision": "resolve_alias_collision",
    # Bidirectional dependency repair
    "add_missing_bidirectional_dep": "add_missing_bidirectional_dep",
    # Cleanup
    "remove_orphaned_aindex": "remove_orphaned_aindex",
    "delete_orphaned_comments": "delete_orphaned_comments",
    "remove_orphan_zero_deps": "remove_orphan_zero_deps",
    # Convention / playbook staleness
    "flag_stale_convention": "flag_stale_convention",
    "flag_stale_playbook": "flag_stale_playbook",
    # Medium-risk (deferred under auto_low)
    "suggest_new_concept": "suggest_new_concept",
    "promote_blocked_iwh": "promote_blocked_iwh",
}


# ---------------------------------------------------------------------------
# Helper internals
# ---------------------------------------------------------------------------


_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _extract_wikilink_target_from_detail(detail: str) -> str | None:
    """Extract the first ``[[target]]`` substring from an action detail string.

    ``FixInstruction.detail`` uses formats like
    ``"Wikilink [[NonexistentConcept]] cannot be resolved; strip it"``
    -- this helper pulls the inner target so the fix helper can locate
    it in the design file's ``wikilinks`` list.
    """
    match = _WIKILINK_RE.search(detail)
    if match is None:
        return None
    return match.group(1).strip()


def _extract_suggestion_from_detail(detail: str) -> str | None:
    """Extract the first fuzzy suggestion name from a ``fix_broken_wikilink_fuzzy`` detail.

    Detail format emitted by ``consistency.check_wikilinks`` for fuzzy
    hits::

        Wikilink [[Authentcation]] unresolved; suggestions: Authentication, Auth
    """
    marker = "suggestions:"
    idx = detail.find(marker)
    if idx < 0:
        return None
    tail = detail[idx + len(marker) :].strip()
    if not tail:
        return None
    # Take the first comma-separated suggestion.
    first = tail.split(",", 1)[0].strip()
    return first or None


def _result(
    *,
    action_key: str,
    path: Path | None,
    message: str,
    success: bool = True,
    outcome: str = "fixed",
) -> SubAgentResult:
    """Build a :class:`SubAgentResult` with standardised defaults."""
    return SubAgentResult(
        success=success,
        action_key=action_key,
        path=path,
        message=message,
        llm_calls=0,
        outcome=outcome,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Wikilink fix helpers
# ---------------------------------------------------------------------------


def apply_strip_wikilink(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Remove an unresolved wikilink from a design file.

    Parses the design file at ``item.source_item.path``, removes the
    target extracted from ``item.source_item.fix_instruction_detail`` from
    the ``wikilinks`` list, and persists via the shared write contract.
    """
    action_key = item.action_key
    design_path = item.source_item.path
    if design_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No design path available for strip_unresolved_wikilink",
            success=False,
            outcome="fixer_failed",
        )

    target = _extract_wikilink_target_from_detail(item.source_item.fix_instruction_detail)
    if target is None:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Could not extract wikilink target from detail",
            success=False,
            outcome="fixer_failed",
        )

    design = parse_design_file(design_path)
    if design is None:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Failed to parse design file",
            success=False,
            outcome="fixer_failed",
        )

    target_norm = target.strip().lower()
    new_wikilinks = [wl for wl in design.wikilinks if wl.strip().lower() != target_norm]
    if len(new_wikilinks) == len(design.wikilinks):
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"Wikilink [[{target}]] not present; nothing to strip",
            outcome="fixed",
        )

    design.wikilinks = new_wikilinks
    try:
        write_design_file_as_curator(design, design_path, ctx.project_root)
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(design_path))
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"Failed to write design file: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=design_path,
        message=f"Stripped unresolved wikilink [[{target}]]",
        outcome="fixed",
    )


def apply_substitute_wikilink(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Replace a broken wikilink with a fuzzy-match suggestion.

    Parses the design file, locates the target wikilink, replaces it
    with the first suggestion extracted from the detail string, and
    persists via the shared write contract.
    """
    action_key = item.action_key
    design_path = item.source_item.path
    if design_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No design path available for fix_broken_wikilink_fuzzy",
            success=False,
            outcome="fixer_failed",
        )

    detail = item.source_item.fix_instruction_detail
    target = _extract_wikilink_target_from_detail(detail)
    suggestion = _extract_suggestion_from_detail(detail)
    if target is None or suggestion is None:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Could not parse target or suggestion from detail",
            success=False,
            outcome="fixer_failed",
        )

    design = parse_design_file(design_path)
    if design is None:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Failed to parse design file",
            success=False,
            outcome="fixer_failed",
        )

    target_norm = target.strip().lower()
    replaced = False
    new_wikilinks: list[str] = []
    for wl in design.wikilinks:
        if wl.strip().lower() == target_norm:
            new_wikilinks.append(suggestion)
            replaced = True
        else:
            new_wikilinks.append(wl)

    if not replaced:
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"Wikilink [[{target}]] not present; nothing to substitute",
            outcome="fixed",
        )

    design.wikilinks = new_wikilinks
    try:
        write_design_file_as_curator(design, design_path, ctx.project_root)
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(design_path))
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"Failed to write design file: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=design_path,
        message=f"Substituted [[{target}]] -> [[{suggestion}]]",
        outcome="fixed",
    )


# ---------------------------------------------------------------------------
# Slug / alias collision helpers
# ---------------------------------------------------------------------------


def apply_slug_suffix(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Append a deterministic ``-NN`` suffix to a colliding design file's id.

    The helper rewrites ``frontmatter.id`` with a numeric suffix derived
    from the colliding artifact's position so the slug becomes unique
    without altering the human-readable title.  Persists via the shared
    write contract.
    """
    action_key = item.action_key
    design_path = item.source_item.path
    if design_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No design path for resolve_slug_collision",
            success=False,
            outcome="fixer_failed",
        )

    design = parse_design_file(design_path)
    if design is None:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Failed to parse design file",
            success=False,
            outcome="fixer_failed",
        )

    existing_id = design.frontmatter.id
    # Compute the next numeric suffix deterministically from the id hash
    # so re-running the helper on the same file produces the same result.
    import hashlib  # noqa: PLC0415

    digest = hashlib.sha256(existing_id.encode("utf-8")).hexdigest()
    suffix = int(digest[:2], 16) % 90 + 10  # -> 10..99
    new_id = f"{existing_id}-{suffix}"
    design.frontmatter.id = new_id

    try:
        write_design_file_as_curator(design, design_path, ctx.project_root)
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(design_path))
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"Failed to write design file: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=design_path,
        message=f"Resolved slug collision: id {existing_id} -> {new_id}",
        outcome="fixed",
    )


def apply_alias_dedup(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Remove duplicate aliases from a concept or convention file's frontmatter.

    Parses the YAML frontmatter in-place (concept/convention files are
    NOT design files, so the shared design-file write contract does NOT
    apply).  The helper keeps the first occurrence of each alias
    (case-insensitive), preserving order.
    """
    import yaml  # noqa: PLC0415

    from lexibrary.utils.atomic import atomic_write  # noqa: PLC0415

    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for resolve_alias_collision",
            success=False,
            outcome="fixer_failed",
        )

    try:
        text = target_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _result(
            action_key=action_key,
            path=target_path,
            message=f"Failed to read artifact: {exc}",
            success=False,
            outcome="errored",
        )

    if not text.startswith("---\n"):
        return _result(
            action_key=action_key,
            path=target_path,
            message="Artifact has no YAML frontmatter",
            success=False,
            outcome="fixer_failed",
        )
    end = text.find("\n---\n", 4)
    if end < 0:
        return _result(
            action_key=action_key,
            path=target_path,
            message="Artifact frontmatter is unterminated",
            success=False,
            outcome="fixer_failed",
        )

    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        return _result(
            action_key=action_key,
            path=target_path,
            message=f"Failed to parse frontmatter: {exc}",
            success=False,
            outcome="errored",
        )
    if not isinstance(data, dict):
        return _result(
            action_key=action_key,
            path=target_path,
            message="Frontmatter is not a mapping",
            success=False,
            outcome="fixer_failed",
        )

    aliases = data.get("aliases", [])
    if not isinstance(aliases, list):
        return _result(
            action_key=action_key,
            path=target_path,
            message="Frontmatter aliases field is not a list",
            success=False,
            outcome="fixer_failed",
        )

    seen: set[str] = set()
    deduped: list[str] = []
    for alias in aliases:
        if not isinstance(alias, str):
            continue
        key = alias.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(alias)

    if len(deduped) == len(aliases):
        return _result(
            action_key=action_key,
            path=target_path,
            message="No duplicate aliases to remove",
            outcome="fixed",
        )

    data["aliases"] = deduped
    new_frontmatter = yaml.dump(data, default_flow_style=False, sort_keys=False).rstrip()
    # Splice the new frontmatter into the file in front of the ``\n---\n``
    # terminator.  We avoid escape-sequence-in-f-string by binding the
    # separator to a local first.
    separator = "\n---\n"
    body = text[end + len(separator) :]
    new_text = f"---\n{new_frontmatter}\n---\n{body}"

    try:
        atomic_write(target_path, new_text)
    except OSError as exc:
        ctx.summary.add("dispatch", exc, path=str(target_path))
        return _result(
            action_key=action_key,
            path=target_path,
            message=f"Failed to write artifact: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message=f"Removed {len(aliases) - len(deduped)} duplicate alias(es)",
        outcome="fixed",
    )


# ---------------------------------------------------------------------------
# Bidirectional dependency helper
# ---------------------------------------------------------------------------


def apply_bidirectional_dep(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Add a missing reverse-dependency entry to the target design file.

    ``FixInstruction.target_path`` points at the design file that needs
    the ``## Dependents`` line added.  ``detail`` carries the source path
    that should be listed as a dependent::

        "<source> depends on <target> but <target> does not list <source>
        as dependent"

    Idempotent: if the dependent is already present, returns success
    without rewriting the file.
    """
    action_key = item.action_key
    design_path = item.source_item.path
    if design_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No design path for add_missing_bidirectional_dep",
            success=False,
            outcome="fixer_failed",
        )

    detail = item.source_item.fix_instruction_detail
    # Extract the source path -- the text before " depends on "
    if " depends on " not in detail:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Could not parse source path from detail",
            success=False,
            outcome="fixer_failed",
        )
    source_rel = detail.split(" depends on ", 1)[0].strip()
    if not source_rel:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Parsed source path is empty",
            success=False,
            outcome="fixer_failed",
        )

    design = parse_design_file(design_path)
    if design is None:
        return _result(
            action_key=action_key,
            path=design_path,
            message="Failed to parse design file",
            success=False,
            outcome="fixer_failed",
        )

    # Idempotency: check the ``dependents`` bullet list for the source path.
    existing = [d.strip() for d in design.dependents]
    if any(e == source_rel or e.startswith(f"{source_rel} ") for e in existing):
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"Dependent {source_rel} already present",
            outcome="fixed",
        )

    design.dependents = [*design.dependents, source_rel]

    try:
        write_design_file_as_curator(design, design_path, ctx.project_root)
    except Exception as exc:
        ctx.summary.add("dispatch", exc, path=str(design_path))
        return _result(
            action_key=action_key,
            path=design_path,
            message=f"Failed to write design file: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=design_path,
        message=f"Added bidirectional dep entry for {source_rel}",
        outcome="fixed",
    )


# ---------------------------------------------------------------------------
# Cleanup helpers (non-design-file deletions)
# ---------------------------------------------------------------------------


def apply_orphaned_aindex_delete(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Delete an orphaned ``.aindex`` file whose source directory is gone."""
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for remove_orphaned_aindex",
            success=False,
            outcome="fixer_failed",
        )

    if not target_path.exists():
        return _result(
            action_key=action_key,
            path=target_path,
            message=".aindex already absent",
            outcome="fixed",
        )

    try:
        target_path.unlink()
    except OSError as exc:
        ctx.summary.add("dispatch", exc, path=str(target_path))
        return _result(
            action_key=action_key,
            path=target_path,
            message=f"Failed to delete .aindex: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message=f"Deleted orphaned .aindex at {target_path.name}",
        outcome="fixed",
    )


def apply_orphaned_comments_delete(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Delete an orphaned ``.comments.yaml`` whose parent artifact is missing."""
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for delete_orphaned_comments",
            success=False,
            outcome="fixer_failed",
        )

    if not target_path.exists():
        return _result(
            action_key=action_key,
            path=target_path,
            message=".comments.yaml already absent",
            outcome="fixed",
        )

    try:
        target_path.unlink()
    except OSError as exc:
        ctx.summary.add("dispatch", exc, path=str(target_path))
        return _result(
            action_key=action_key,
            path=target_path,
            message=f"Failed to delete .comments.yaml: {exc}",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message=f"Deleted orphaned {target_path.name}",
        outcome="fixed",
    )


def apply_orphan_concept_delete(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Delete an orphan concept file and its sibling ``.comments.yaml`` if present.

    Per ``tasks.md`` 8.7: "``apply_orphan_concept_delete`` should also
    remove sibling ``.comments.yaml`` if it exists".
    """
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for remove_orphan_zero_deps",
            success=False,
            outcome="fixer_failed",
        )

    if not target_path.exists():
        return _result(
            action_key=action_key,
            path=target_path,
            message="Orphan concept already absent",
            outcome="fixed",
        )

    # Derive sibling .comments.yaml (same stem + .comments.yaml).
    # Concept files are named ``CN-NNN-slug.md``; the comments sidecar
    # drops the ``.md`` extension and appends ``.comments.yaml`` (matching
    # other sidecar conventions in this codebase).
    stem = target_path.name
    if stem.endswith(".md"):
        stem = stem[:-3]
    comments_sibling = target_path.parent / f"{stem}.comments.yaml"

    try:
        target_path.unlink()
    except OSError as exc:
        ctx.summary.add("dispatch", exc, path=str(target_path))
        return _result(
            action_key=action_key,
            path=target_path,
            message=f"Failed to delete orphan concept: {exc}",
            success=False,
            outcome="errored",
        )

    removed_sibling = False
    if comments_sibling.exists():
        try:
            comments_sibling.unlink()
            removed_sibling = True
        except OSError as exc:
            logger.warning(
                "Removed orphan concept %s but failed to delete sibling comments %s: %s",
                target_path,
                comments_sibling,
                exc,
            )

    suffix = " (plus sibling comments)" if removed_sibling else ""
    return _result(
        action_key=action_key,
        path=target_path,
        message=f"Deleted orphan concept {target_path.name}{suffix}",
        outcome="fixed",
    )


# ---------------------------------------------------------------------------
# Convention / playbook / medium-risk helpers
# ---------------------------------------------------------------------------


def _write_flag_iwh(
    target_path: Path,
    *,
    project_root: Path,
    lexibrary_dir: Path,
    body: str,
) -> Path | None:
    """Write a ``scope=warning`` IWH signal next to *target_path*.

    Chooses the mirror directory under ``.lexibrary/`` when *target_path*
    is already inside the library (typical for conventions/playbooks),
    otherwise writes alongside the file.  Returns the written path or
    ``None`` on failure.
    """
    from lexibrary.iwh.writer import write_iwh  # noqa: PLC0415

    try:
        rel = target_path.relative_to(lexibrary_dir)
        dest_dir = lexibrary_dir / rel.parent
    except ValueError:
        try:
            rel = target_path.relative_to(project_root)
            dest_dir = lexibrary_dir / rel.parent
        except ValueError:
            dest_dir = target_path.parent

    try:
        return write_iwh(dest_dir, author="curator", scope="warning", body=body)
    except OSError as exc:
        logger.warning("Failed to write flag IWH at %s: %s", dest_dir, exc)
        return None


def apply_flag_stale_convention(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Escalation-only: flag a convention that references a path that no longer exists.

    Writes a ``scope=warning`` IWH signal in the convention's directory
    so the next agent session sees the warning.  Does NOT modify the
    convention body -- human review decides whether to rewrite scope or
    deprecate.
    """
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for flag_stale_convention",
            success=False,
            outcome="fixer_failed",
        )

    body = (
        f"Stale convention: {target_path.name}\n"
        f"{item.source_item.fix_instruction_detail}\n"
        f"Action: review and rewrite scope or deprecate."
    )
    iwh_path = _write_flag_iwh(
        target_path,
        project_root=ctx.project_root,
        lexibrary_dir=ctx.lexibrary_dir,
        body=body,
    )
    if iwh_path is None:
        return _result(
            action_key=action_key,
            path=target_path,
            message="Failed to write warning IWH for stale convention",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message=f"Flagged stale convention {target_path.name}",
        outcome="fixed",
    )


def apply_flag_stale_playbook(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Flag a playbook that references a path that no longer exists."""
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for flag_stale_playbook",
            success=False,
            outcome="fixer_failed",
        )

    body = (
        f"Stale playbook: {target_path.name}\n"
        f"{item.source_item.fix_instruction_detail}\n"
        f"Action: review and update path refs or deprecate."
    )
    iwh_path = _write_flag_iwh(
        target_path,
        project_root=ctx.project_root,
        lexibrary_dir=ctx.lexibrary_dir,
        body=body,
    )
    if iwh_path is None:
        return _result(
            action_key=action_key,
            path=target_path,
            message="Failed to write warning IWH for stale playbook",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message=f"Flagged stale playbook {target_path.name}",
        outcome="fixed",
    )


def apply_suggest_new_concept(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Medium-risk: propose a new concept for a recurring unresolved term.

    Under ``auto_low``, this action is deferred (see autonomy gating in
    :func:`should_dispatch`).  Under ``full``, the helper writes a
    ``scope=warning`` IWH next to the first referencing design file so
    a human reviewer sees the proposal.  Concept creation itself is
    left to the reviewer -- the helper is read-only with respect to
    concept files.
    """
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for suggest_new_concept",
            success=False,
            outcome="fixer_failed",
        )

    body = (
        f"Suggested new concept proposal:\n"
        f"{item.source_item.fix_instruction_detail}\n"
        f"Action: create a concept artifact or ignore."
    )
    iwh_path = _write_flag_iwh(
        target_path,
        project_root=ctx.project_root,
        lexibrary_dir=ctx.lexibrary_dir,
        body=body,
    )
    if iwh_path is None:
        return _result(
            action_key=action_key,
            path=target_path,
            message="Failed to write IWH for suggest_new_concept",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message="Flagged suggest_new_concept proposal",
        outcome="fixed",
    )


def apply_promote_blocked_iwh(item: TriageItem, ctx: DispatchContext) -> SubAgentResult:
    """Escalation-only: mark a blocked IWH signal for promotion to a Stack post.

    Under ``auto_low``, this action is deferred.  Under ``full``, the
    helper overwrites the blocked ``.iwh`` with a ``scope=warning`` signal
    indicating promotion should happen.  The original blocked body content
    is lost.  Actual Stack post creation is left to the human reviewer or
    a future Stack-transition sub-agent.
    """
    action_key = item.action_key
    target_path = item.source_item.path
    if target_path is None:
        return _result(
            action_key=action_key,
            path=None,
            message="No target path for promote_blocked_iwh",
            success=False,
            outcome="fixer_failed",
        )

    body = (
        f"Blocked IWH promotion proposal:\n"
        f"{item.source_item.fix_instruction_detail}\n"
        f"Action: promote to Stack post and consume the signal."
    )
    iwh_path = _write_flag_iwh(
        target_path,
        project_root=ctx.project_root,
        lexibrary_dir=ctx.lexibrary_dir,
        body=body,
    )
    if iwh_path is None:
        return _result(
            action_key=action_key,
            path=target_path,
            message="Failed to write promotion IWH",
            success=False,
            outcome="errored",
        )

    return _result(
        action_key=action_key,
        path=target_path,
        message="Flagged promote_blocked_iwh proposal",
        outcome="fixed",
    )
