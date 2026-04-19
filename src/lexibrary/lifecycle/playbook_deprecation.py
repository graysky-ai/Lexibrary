"""Soft-deprecate playbook helper (status flip + body note).

Provides a reusable primitive for soft-deprecating a playbook by flipping
``status`` to ``"deprecated"``, stamping ``deprecated_at`` with the current
UTC timestamp, recording the deprecation reason, and appending a visible
``> **Deprecated: ...`` note to the body.

Used by the ``lexi playbook deprecate`` CLI command and the
``lexi validate --fix --interactive`` escalation flow so both code paths
share one implementation.

Public API
----------
- :func:`deprecate_playbook` -- idempotent soft-deprecate primitive.

Notes
-----
The helper is intentionally free of ``lexibrary._output`` calls (``info``,
``warn``, ``error``, ``hint``, ``markdown_table``) per the lifecycle-helper
constraint (SHARED_BLOCK_A). User-facing messages belong in the CLI layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.playbooks.parser import parse_playbook_file
from lexibrary.playbooks.serializer import serialize_playbook_file
from lexibrary.utils.atomic import atomic_write


def deprecate_playbook(
    playbook_path: Path,
    *,
    reason: str,
    superseded_by: str | None = None,
) -> None:
    """Soft-deprecate a playbook by updating its frontmatter and body.

    On the first call the playbook is mutated as follows:

    1. ``frontmatter.status`` is set to ``"deprecated"``.
    2. ``frontmatter.deprecated_at`` is set to the current UTC timestamp
       (microseconds stripped, parity with :func:`deprecate_design`).
    3. ``frontmatter.deprecated_reason`` is set to *reason*.
    4. ``frontmatter.superseded_by`` is set to *superseded_by* when
       provided.
    5. A ``> **Deprecated: {reason}`` blockquote is appended to the body so
       the status is visible to anyone reading the rendered playbook.

    The helper is **idempotent**: calling it on an already-deprecated
    playbook is a silent no-op. It does *not* re-stamp ``deprecated_at``
    (preserving downstream TTL math) and does *not* re-append the body
    note. Callers that want a user-facing "already deprecated" message
    should pre-check the parsed frontmatter at their layer.

    The helper returns ``None`` on parse failure (parity with
    :func:`deprecate_design` and the other lifecycle deprecation helpers).

    Parameters
    ----------
    playbook_path:
        Absolute path to the playbook ``.md`` file.
    reason:
        Free-text reason for deprecation (e.g. ``"past_last_verified"``).
    superseded_by:
        Optional slug of the playbook that replaces this one.

    Returns
    -------
    None
        The updated frontmatter + body is persisted via an atomic write
        (temp file + ``os.replace``). ``None`` is also returned on parse
        failure or when the playbook is already deprecated.
    """
    playbook = parse_playbook_file(playbook_path)
    if playbook is None:
        return

    # Idempotent: already-deprecated input is a silent no-op.
    # Do NOT re-stamp deprecated_at (preserves TTL math downstream).
    # Do NOT re-append the body note.
    if playbook.frontmatter.status == "deprecated":
        return

    playbook.frontmatter.status = "deprecated"
    playbook.frontmatter.deprecated_at = datetime.now(UTC).replace(microsecond=0)
    playbook.frontmatter.deprecated_reason = reason
    if superseded_by is not None:
        playbook.frontmatter.superseded_by = superseded_by

    # Append a visible deprecation note to the body.
    deprecation_note = f"\n\n> **Deprecated:** {reason}\n"
    playbook.body = (
        playbook.body.rstrip("\n") + deprecation_note
        if playbook.body
        else deprecation_note.lstrip("\n")
    )

    atomic_write(playbook_path, serialize_playbook_file(playbook))
