"""Migration execution for post-deprecation dependent artifact updates.

After a deprecation is committed, the coordinator may dispatch a migration
cycle to update dependent artifacts.  This module provides:

- :func:`validate_successor_chain` -- verify the ``superseded_by`` target
  exists and is ``active``, and detect cycles in the chain.
- :func:`apply_migration_edits` -- apply a list of ``MigrationEdit`` objects
  to dependent artifacts on disk, writing back via ``serialize_design_file()``
  + ``atomic_write()`` for design files and ``atomic_write()`` for concepts
  / conventions.
- :func:`verify_migration` -- re-run ``reverse_deps()`` on the deprecated
  artifact to check for remaining inbound references.

Public API
----------
- :func:`validate_successor_chain`
- :func:`apply_migration_edits`
- :func:`verify_migration`
- :class:`MigrationReport`
- :class:`EditOutcome`
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.baml_client.types import MigrationEdit, MigrationEditType

if TYPE_CHECKING:
    from lexibrary.linkgraph.query import LinkGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Wikilink replacement regex
# ---------------------------------------------------------------------------

# Matches [[target]] wikilinks.  The capture group gets the inner text.
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EditOutcome:
    """Result of applying a single ``MigrationEdit``.

    Attributes
    ----------
    edit:
        The edit that was applied (or attempted).
    success:
        Whether the edit was applied successfully.
    error:
        Error message if the edit failed, empty string otherwise.
    """

    edit: MigrationEdit
    success: bool
    error: str = ""


@dataclass
class MigrationReport:
    """Aggregated result of applying a batch of migration edits.

    Attributes
    ----------
    outcomes:
        Per-edit success/failure details.
    success_count:
        Number of edits that succeeded.
    failure_count:
        Number of edits that failed.
    """

    outcomes: list[EditOutcome] = field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0


# ---------------------------------------------------------------------------
# Successor chain validation
# ---------------------------------------------------------------------------


def validate_successor_chain(
    superseded_by: str,
    link_graph: LinkGraph | None,
) -> tuple[bool, str]:
    """Verify the successor target exists, is ``active``, and has no cycles.

    Traverses the chain ``A -> B -> C ...`` by reading each artifact's
    ``superseded_by`` frontmatter field.  Returns ``(False, reason)`` on
    the first problem encountered.

    Parameters
    ----------
    superseded_by:
        The project-relative path of the immediate successor artifact.
    link_graph:
        Open link graph instance, or ``None`` if unavailable.  When
        ``None``, only file-existence and status checks are performed
        (no cycle detection via link graph).

    Returns
    -------
    tuple[bool, str]
        ``(True, "")`` when the chain is valid.
        ``(False, reason)`` otherwise.
    """
    if not superseded_by:
        return (False, "superseded_by is empty")

    visited: list[str] = []
    current = superseded_by

    while current:
        # Cycle detection -- have we seen this path before?
        if current in visited:
            cycle_desc = " -> ".join(visited + [current])
            return (False, f"cycle detected: {cycle_desc}")

        visited.append(current)

        # Read artifact status
        status, next_superseded_by = _read_artifact_status_and_successor(current)

        if status is None:
            return (False, f"successor does not exist: {current}")

        if status == "deprecated":
            return (False, f"successor is deprecated: {current}")

        if status not in ("active", "draft"):
            return (False, f"successor has unexpected status '{status}': {current}")

        # If the successor itself has a superseded_by, follow the chain
        current = next_superseded_by or ""

    return (True, "")


def _read_artifact_status_and_successor(
    artifact_path: str,
) -> tuple[str | None, str | None]:
    """Read the status and superseded_by of an artifact from disk.

    Tries concept, convention, and design file parsers in order.
    Returns ``(None, None)`` if the artifact does not exist or cannot
    be parsed.

    Returns
    -------
    tuple[str | None, str | None]
        ``(status, superseded_by)`` or ``(None, None)`` on failure.
    """
    path = Path(artifact_path)

    # If path is not absolute, try resolving from cwd
    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.exists():
        return (None, None)

    # Try concept parser
    try:
        from lexibrary.wiki.parser import parse_concept_file  # noqa: PLC0415

        concept = parse_concept_file(path)
        if concept is not None:
            return (
                concept.frontmatter.status or "draft",
                concept.frontmatter.superseded_by,
            )
    except Exception:  # noqa: BLE001
        pass

    # Try convention parser
    try:
        from lexibrary.conventions.parser import (  # noqa: PLC0415
            parse_convention_file,
        )

        convention = parse_convention_file(path)
        if convention is not None:
            return (convention.frontmatter.status or "draft", None)
    except Exception:  # noqa: BLE001
        pass

    # Try design file parser
    try:
        from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
            parse_design_file_frontmatter,
        )

        fm = parse_design_file_frontmatter(path)
        if fm is not None:
            return (fm.status or "active", None)
    except Exception:  # noqa: BLE001
        pass

    return (None, None)


# ---------------------------------------------------------------------------
# Migration edit application
# ---------------------------------------------------------------------------


def apply_migration_edits(
    edits: list[MigrationEdit],
    project_root: Path,
) -> MigrationReport:
    """Apply a list of migration edits to dependent artifacts.

    For each edit, reads the target artifact, applies the edit (replace
    wikilink text, update frontmatter ref, or remove reference), and
    writes back using ``serialize_design_file()`` + ``atomic_write()``
    for design files, ``atomic_write()`` for concepts/conventions.

    If a single edit fails, the error is logged, that edit is skipped,
    and processing continues with remaining edits.

    Parameters
    ----------
    edits:
        The list of ``MigrationEdit`` objects from the sub-agent.
    project_root:
        Absolute path to the project root.

    Returns
    -------
    MigrationReport
        Aggregated success/failure counts and per-edit outcomes.
    """
    report = MigrationReport()

    for edit in edits:
        try:
            _apply_single_edit(edit, project_root)
            outcome = EditOutcome(edit=edit, success=True)
            report.success_count += 1
            logger.info(
                "Migration edit applied: %s on %s",
                edit.edit_type.value if hasattr(edit.edit_type, "value") else edit.edit_type,
                edit.artifact_path,
            )
        except Exception as exc:  # noqa: BLE001
            outcome = EditOutcome(edit=edit, success=False, error=str(exc))
            report.failure_count += 1
            logger.error(
                "Migration edit failed for %s: %s",
                edit.artifact_path,
                exc,
            )

        report.outcomes.append(outcome)

    return report


def _apply_single_edit(edit: MigrationEdit, project_root: Path) -> None:
    """Apply a single migration edit to an artifact on disk.

    Dispatches to the appropriate handler based on artifact type
    (design file vs concept/convention).

    Raises
    ------
    FileNotFoundError
        If the target artifact does not exist.
    ValueError
        If the edit type is unsupported or the edit cannot be applied.
    """
    artifact_path = project_root / edit.artifact_path
    if not artifact_path.exists():
        msg = f"Target artifact does not exist: {artifact_path}"
        raise FileNotFoundError(msg)

    if _is_design_file(artifact_path):
        _apply_design_file_edit(edit, artifact_path)
    else:
        _apply_text_edit(edit, artifact_path)


def _is_design_file(path: Path) -> bool:
    """Check whether a path is under a designs directory."""
    parts = path.parts
    return "designs" in parts


def _apply_design_file_edit(edit: MigrationEdit, artifact_path: Path) -> None:
    """Apply a migration edit to a design file.

    Reads the design file, applies the text transformation to all text
    fields (summary, interface_contract, preserved_sections, wikilinks list),
    sets ``updated_by: curator`` in frontmatter, and writes back via
    ``serialize_design_file()`` + ``atomic_write()``.
    """
    from lexibrary.artifacts.design_file_parser import (  # noqa: PLC0415
        parse_design_file,
    )
    from lexibrary.artifacts.design_file_serializer import (  # noqa: PLC0415
        serialize_design_file,
    )
    from lexibrary.utils.atomic import atomic_write  # noqa: PLC0415

    design = parse_design_file(artifact_path)
    if design is None:
        msg = f"Cannot parse design file: {artifact_path}"
        raise ValueError(msg)

    edit_type = edit.edit_type
    edit_type_val = edit_type.value if isinstance(edit_type, MigrationEditType) else str(edit_type)

    # Apply text transformation across all text fields in the design file
    transform = _get_transform(edit_type_val, edit.old_value, edit.new_value)

    design.summary = transform(design.summary)
    design.interface_contract = transform(design.interface_contract)

    # Transform preserved sections
    for key in list(design.preserved_sections):
        design.preserved_sections[key] = transform(design.preserved_sections[key])

    # Transform wikilinks list entries (just the text, not [[]] wrapped)
    old_lower = edit.old_value.strip().lower()
    if edit_type_val in (
        MigrationEditType.ReplaceWikilink.value,
        "replace_wikilink",
        MigrationEditType.UpdateConceptRef.value,
        "update_concept_ref",
    ):
        design.wikilinks = [
            edit.new_value if (w.strip().lower() == old_lower and edit.new_value) else w
            for w in design.wikilinks
        ]
    elif edit_type_val in (
        MigrationEditType.RemoveReference.value,
        "remove_reference",
    ):
        design.wikilinks = [w for w in design.wikilinks if w.strip().lower() != old_lower]

    # Set updated_by to curator
    design.frontmatter.updated_by = "curator"

    content = serialize_design_file(design)
    atomic_write(artifact_path, content)


def _get_transform(
    edit_type_val: str,
    old_value: str,
    new_value: str | None,
) -> Callable[[str], str]:
    """Return a text transformation function for the given edit type."""
    if edit_type_val in (
        MigrationEditType.ReplaceWikilink.value,
        "replace_wikilink",
        MigrationEditType.UpdateConceptRef.value,
        "update_concept_ref",
    ):

        def transform(text: str) -> str:
            return _replace_wikilink(text, old_value, new_value)

        return transform

    if edit_type_val in (
        MigrationEditType.RemoveReference.value,
        "remove_reference",
    ):

        def transform(text: str) -> str:
            return _remove_reference(text, old_value)

        return transform

    msg = f"Unsupported edit type: {edit_type_val}"
    raise ValueError(msg)


def _apply_text_edit(edit: MigrationEdit, artifact_path: Path) -> None:
    """Apply a migration edit to a concept or convention file.

    Reads the file as plain text, applies the text transformation, and
    writes back via ``atomic_write()``.
    """
    from lexibrary.utils.atomic import atomic_write  # noqa: PLC0415

    text = artifact_path.read_text(encoding="utf-8")

    edit_type = edit.edit_type
    edit_type_val = edit_type.value if isinstance(edit_type, MigrationEditType) else str(edit_type)

    if edit_type_val in (
        MigrationEditType.ReplaceWikilink.value,
        "replace_wikilink",
    ):
        text = _replace_wikilink(text, edit.old_value, edit.new_value)
    elif edit_type_val in (
        MigrationEditType.RemoveReference.value,
        "remove_reference",
    ):
        text = _remove_reference(text, edit.old_value)
    elif edit_type_val in (
        MigrationEditType.UpdateConceptRef.value,
        "update_concept_ref",
    ):
        text = _replace_wikilink(text, edit.old_value, edit.new_value)
    else:
        msg = f"Unsupported edit type: {edit_type_val}"
        raise ValueError(msg)

    atomic_write(artifact_path, text)


# ---------------------------------------------------------------------------
# Text transformation helpers
# ---------------------------------------------------------------------------


def _replace_wikilink(text: str, old_value: str, new_value: str | None) -> str:
    """Replace ``[[old_value]]`` wikilinks with ``[[new_value]]``.

    Case-insensitive matching of the link target.  If *new_value* is
    ``None`` or empty, the wikilink is removed entirely (degrades to
    ``_remove_reference``).
    """
    if not new_value:
        return _remove_reference(text, old_value)

    def replacer(m: re.Match[str]) -> str:
        if m.group(1).strip().lower() == old_value.strip().lower():
            return f"[[{new_value}]]"
        return m.group(0)

    return _WIKILINK_RE.sub(replacer, text)


def _remove_reference(text: str, old_value: str) -> str:
    """Remove ``[[old_value]]`` wikilinks, leaving just the link text.

    The wikilink brackets are stripped, leaving the display text inline
    so the prose remains readable.
    """

    def replacer(m: re.Match[str]) -> str:
        if m.group(1).strip().lower() == old_value.strip().lower():
            return m.group(1)
        return m.group(0)

    return _WIKILINK_RE.sub(replacer, text)


# ---------------------------------------------------------------------------
# Post-migration verification
# ---------------------------------------------------------------------------


def verify_migration(
    artifact_path: str,
    link_graph: LinkGraph | None,
) -> list[str]:
    """Re-check for remaining inbound references to a deprecated artifact.

    Runs ``reverse_deps()`` on the deprecated artifact and returns
    any remaining inbound reference paths.  An empty list means
    the migration was fully successful.

    Parameters
    ----------
    artifact_path:
        Project-relative path to the deprecated artifact.
    link_graph:
        Open link graph instance, or ``None`` if unavailable.

    Returns
    -------
    list[str]
        Paths of artifacts that still reference the deprecated artifact.
        Empty list means full success.
    """
    if link_graph is None:
        logger.warning(
            "Link graph unavailable -- cannot verify migration for %s",
            artifact_path,
        )
        return []

    remaining = link_graph.reverse_deps(artifact_path)
    paths = sorted({r.source_path for r in remaining})

    if paths:
        logger.warning(
            "Post-migration verification: %s still has %d inbound reference(s): %s",
            artifact_path,
            len(paths),
            ", ".join(paths[:5]),
        )
    else:
        logger.info(
            "Post-migration verification: %s has no remaining inbound references",
            artifact_path,
        )

    return paths
