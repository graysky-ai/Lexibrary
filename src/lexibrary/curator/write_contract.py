"""Shared design-file write contract for curator sub-agents.

Centralises the canonical write sequence that every curator sub-agent
must follow when rewriting a design file.  Prior to this module, the
sequence was duplicated across ``staleness.py``, ``reconciliation.py``,
and ``comments.py`` -- each doing its own ``compute_hashes`` call,
``serialize_design_file`` call, and ``atomic_write`` call, and each
setting ``updated_by`` inline.  Duplication invited drift: the three
copies could disagree about hash computation order, authorship
assignment, or error handling.

The helper exposed here -- :func:`write_design_file_as_curator` --
captures the full sequence in one place:

1. Stamp ``frontmatter.updated_by = "curator"`` (curator owns the blame
   for any design-file rewrite that goes through this contract).
2. Recompute ``source_hash`` and ``interface_hash`` from the current
   on-disk source file and update ``metadata.source_hash`` /
   ``metadata.interface_hash`` on the in-memory DesignFile.
3. Serialize via :func:`serialize_design_file`, which also computes
   the ``design_hash`` footer field from the rendered body.
4. Write the result via :func:`atomic_write` to avoid ever leaving a
   partially-written file on disk.

The helper intentionally raises on hash or write failures so that
dispatch callers can convert the exception to a ``SubAgentResult``
with a structured error message using their existing try/except
blocks.  Callers should NOT try to recover inside the helper.

Group 8 (consistency integration) will also call this helper from
every consistency fix helper so that wikilink repairs, slug collision
resolution, and similar rewrites inherit the same authorship and
hash-freshness guarantees.
"""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.design_file import DesignFile
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.ast_parser import compute_hashes
from lexibrary.utils.atomic import atomic_write


def write_design_file_as_curator(
    design_file: DesignFile,
    path: Path,
    project_root: Path,
) -> None:
    """Persist *design_file* at *path* under the curator write contract.

    Sets ``frontmatter.updated_by`` to ``"curator"``, recomputes
    ``metadata.source_hash`` and ``metadata.interface_hash`` from the
    current source file at ``project_root / design_file.source_path``,
    serializes the result (which also computes ``metadata.design_hash``
    as part of the footer), and writes atomically.

    Mutates the in-memory ``design_file`` so the caller observes the
    final hash and authorship values after the call returns.

    Args:
        design_file: The fully-built :class:`DesignFile` to persist.
            ``source_path``, ``frontmatter``, ``summary``,
            ``interface_contract``, ``dependencies``, ``dependents``,
            ``preserved_sections``, and ``metadata`` MUST already be
            populated by the caller -- this helper does not fill in
            domain content.
        path: Absolute target path for the design file on disk
            (typically the mirrored path under ``.lexibrary/designs/``).
        project_root: Absolute project root.  Used to resolve the
            absolute source file path from the relative
            ``design_file.source_path``.

    Raises:
        OSError: If the source file cannot be hashed or the atomic
            write fails.  The helper deliberately propagates errors to
            the caller's dispatch try/except; it does not swallow or
            translate exceptions.
        Exception: Re-raised from :func:`compute_hashes` when AST
            parsing of the source file fails.
    """
    # Step 1: stamp authorship.  The curator owns blame for any
    # rewrite that flows through this contract.
    design_file.frontmatter.updated_by = "curator"

    # Step 2: recompute source_hash / interface_hash from the current
    # on-disk source.  design_file.source_path is relative to
    # project_root (canonical storage format).
    source_abs = project_root / design_file.source_path
    fresh_source_hash, fresh_interface_hash = compute_hashes(source_abs)
    design_file.metadata.source_hash = fresh_source_hash
    design_file.metadata.interface_hash = fresh_interface_hash

    # Step 3: serialize.  The serializer populates
    # metadata.design_hash from the rendered body text, so we do not
    # need to touch that field ourselves here.
    content = serialize_design_file(design_file)

    # Step 4: atomic write.  Readers never observe a partial file.
    atomic_write(path, content)
