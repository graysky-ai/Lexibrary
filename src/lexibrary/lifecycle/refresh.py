"""Refresh helpers — resolve stale/orphan state WITHOUT deprecating.

Shared between the ``lexi validate --fix --interactive`` flow (non-admin) and
the ``lexictl curate resolve`` admin subcommand.

These helpers are strictly free of ``lexibrary._output`` calls (``info``,
``warn``, ``error``, ``hint``, ``markdown_table``); user-facing messages live
in the CLI / interactive-prompt layer (SHARED_BLOCK_A).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from lexibrary.artifacts.convention import split_scope
from lexibrary.conventions.parser import parse_convention_file
from lexibrary.conventions.serializer import serialize_convention_file
from lexibrary.playbooks.parser import parse_playbook_file
from lexibrary.playbooks.serializer import serialize_playbook_file
from lexibrary.utils.atomic import atomic_write
from lexibrary.wiki.parser import parse_concept_file
from lexibrary.wiki.serializer import serialize_concept_file


def refresh_stale_concept(concept_path: Path, project_root: Path) -> int:
    """Prune ``linked_files`` entries whose targets no longer exist.

    Parses the concept, identifies every ``linked_files`` entry whose
    resolved target (relative to *project_root*) does NOT exist on disk,
    and rewrites the concept body with those backtick-delimited references
    removed. All other body content is preserved.

    Parameters
    ----------
    concept_path:
        Absolute path to the concept ``.md`` file.
    project_root:
        Absolute path to the project root used to resolve relative
        ``linked_files`` references.

    Returns
    -------
    int
        The number of pruned entries. Returns ``0`` when the concept cannot
        be parsed, when ``linked_files`` is empty, or when every referenced
        target exists.
    """
    concept = parse_concept_file(concept_path)
    if concept is None:
        return 0

    missing: list[str] = [
        file_ref for file_ref in concept.linked_files if not (project_root / file_ref).exists()
    ]
    if not missing:
        return 0

    # ``linked_files`` is a derived field (``_FILE_REF_RE.findall`` over
    # the body in ``wiki/parser.py``), so pruning means editing the body
    # text that produced each entry. Match only the full backticked
    # occurrence to avoid touching bare paths that might appear elsewhere.
    new_body = concept.body
    for ref in missing:
        pattern = re.compile(r"`" + re.escape(ref) + r"`")
        new_body = pattern.sub("", new_body)

    concept.body = new_body
    atomic_write(concept_path, serialize_concept_file(concept))

    return len(missing)


def refresh_orphan_concept(concept_path: Path) -> None:
    """Stamp ``last_verified`` on an orphan concept without deprecating it.

    Used when an operator confirms a concept with zero inbound link-graph
    references is still valuable. Sets ``frontmatter.last_verified = date.today()``
    so ``check_orphan_concepts`` skips the concept for the
    ``concepts.orphan_verify_ttl_days`` window.

    Parameters
    ----------
    concept_path:
        Absolute path to the concept ``.md`` file.

    Returns
    -------
    None
        Silently returns ``None`` when the concept cannot be parsed (parity
        with the other lifecycle helpers). On success, the updated frontmatter
        is persisted via an atomic write (temp file + ``os.replace``).
    """
    concept = parse_concept_file(concept_path)
    if concept is None:
        return

    concept.frontmatter.last_verified = date.today()
    atomic_write(concept_path, serialize_concept_file(concept))


def refresh_convention_stale(
    convention_path: Path,
    project_root: Path,
    *,
    new_scope: str,
) -> None:
    """Rewrite a convention's ``scope`` to an operator-supplied value.

    Used when one or more paths in the existing scope no longer exist on
    disk and the operator has chosen to refresh (rather than deprecate)
    the convention. Validates that every path in *new_scope* resolves to
    an existing filesystem location (``project`` is a symbolic scope and
    always passes), then persists the new scope via an atomic write.

    Parameters
    ----------
    convention_path:
        Absolute path to the convention ``.md`` file.
    project_root:
        Absolute path to the project root used to resolve non-``project``
        scope paths.
    new_scope:
        The replacement scope string. Matches the existing scope grammar:
        either the literal ``"project"`` or one or more comma-separated
        relative paths (e.g. ``"src/lexibrary/cli/, src/lexibrary/services/"``).

    Returns
    -------
    None
        Silently returns ``None`` when the convention cannot be parsed
        (parity with the other lifecycle helpers). On success, the updated
        frontmatter is persisted via an atomic write (temp file +
        ``os.replace``).

    Raises
    ------
    FileNotFoundError
        If any non-``project`` path in *new_scope* does not exist under
        *project_root*. Message format:
        ``"scope path does not exist: <path>"``.
    ValueError
        If every path in the existing scope is missing (i.e. the convention
        is fully stale) AND *new_scope* equals the existing scope. The
        operator must supply a different scope in this case since otherwise
        the refresh would be a no-op on an unrecoverable artifact.
    """
    convention = parse_convention_file(convention_path)
    if convention is None:
        return

    # Fully-stale short-circuit: when every path in the EXISTING scope is
    # missing (not just partial), a refresh that keeps the same scope value
    # would be a silent no-op on an unrecoverable artifact. Catch that case
    # before path validation so the operator receives a meaningful
    # ``ValueError`` rather than the downstream ``FileNotFoundError`` from
    # the shared stale paths.
    existing_paths = split_scope(convention.frontmatter.scope)
    non_project_existing = [p for p in existing_paths if p != "project"]
    if (
        non_project_existing
        and all(not (project_root / p).exists() for p in non_project_existing)
        and new_scope == convention.frontmatter.scope
    ):
        raise ValueError("new_scope required: all existing scope paths are missing")

    # Every non-``project`` path in ``new_scope`` must exist on disk.
    # ``split_scope`` normalizes whitespace and trailing slashes and returns
    # ``["project"]`` verbatim when the scope is the symbolic ``"project"``.
    for path in split_scope(new_scope):
        if path == "project":
            continue
        if not (project_root / path).exists():
            raise FileNotFoundError(f"scope path does not exist: {path}")

    convention.frontmatter.scope = new_scope
    atomic_write(convention_path, serialize_convention_file(convention))


def refresh_playbook_staleness(playbook_path: Path) -> None:
    """Stamp ``last_verified`` on a playbook to clear staleness.

    Used by both the ``lexi playbook verify`` CLI command and the
    ``lexi validate --fix --interactive`` escalation flow so the two
    paths share one implementation.

    Parameters
    ----------
    playbook_path:
        Absolute path to the playbook ``.md`` file.

    Returns
    -------
    None
        Silently returns ``None`` when the playbook cannot be parsed
        (parity with the other lifecycle helpers). On success, the updated
        frontmatter is persisted via an atomic write (temp file + ``os.replace``).
    """
    playbook = parse_playbook_file(playbook_path)
    if playbook is None:
        return

    playbook.frontmatter.last_verified = date.today()
    atomic_write(playbook_path, serialize_playbook_file(playbook))
