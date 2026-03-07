"""Enrichment queue for deferred LLM processing of design file skeletons.

The queue is stored as a plain-text file at ``.lexibrary/queue/design-pending.txt``
with one entry per line.  Each line contains a relative source path and an ISO 8601
timestamp separated by a space.  Lines starting with ``#`` are comments.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from lexibrary.templates import read_template

QUEUE_REL_PATH = Path(".lexibrary") / "queue" / "design-pending.txt"
QUEUE_HEADER = read_template("lifecycle/queue_header.txt")


class QueueEntry(BaseModel):
    """A single entry in the enrichment queue."""

    source_path: Path
    """Relative path to the source file awaiting enrichment."""

    queued_at: datetime
    """Timestamp when the file was queued."""


def _queue_file(project_root: Path) -> Path:
    """Return the absolute path to the queue file."""
    return project_root / QUEUE_REL_PATH


def queue_for_enrichment(project_root: Path, source_path: Path) -> None:
    """Append a source file to the enrichment queue.

    Creates the queue file and parent directories if they do not exist.
    The *source_path* is stored as a POSIX relative path.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    source_path:
        Path to the source file, either absolute or relative to *project_root*.
    """
    queue_path = _queue_file(project_root)
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    # Normalise to a relative POSIX path.
    try:
        rel = source_path.relative_to(project_root)
    except ValueError:
        rel = source_path
    posix_rel = rel.as_posix()

    now = datetime.now(UTC).replace(microsecond=0).isoformat()

    # If the file doesn't exist yet, write the header first.
    if not queue_path.exists():
        queue_path.write_text(QUEUE_HEADER)

    with queue_path.open("a") as fh:
        fh.write(f"{posix_rel} {now}\n")


def read_queue(project_root: Path) -> list[QueueEntry]:
    """Read and deduplicate the enrichment queue.

    If the queue file does not exist or is empty, returns an empty list.
    When a source path appears more than once, only the entry with the
    latest timestamp is kept.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.

    Returns
    -------
    list[QueueEntry]
        Deduplicated queue entries sorted by timestamp (oldest first).
    """
    queue_path = _queue_file(project_root)
    if not queue_path.exists():
        return []

    latest: dict[str, datetime] = {}

    for line in queue_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Split on the last space -- paths cannot contain trailing spaces
        # but may theoretically contain internal spaces (rare for source).
        parts = stripped.rsplit(" ", maxsplit=1)
        if len(parts) != 2:
            continue  # malformed line, skip

        raw_path, raw_ts = parts
        try:
            ts = datetime.fromisoformat(raw_ts)
        except ValueError:
            continue  # unparseable timestamp, skip

        existing = latest.get(raw_path)
        if existing is None or ts > existing:
            latest[raw_path] = ts

    entries = [QueueEntry(source_path=Path(p), queued_at=ts) for p, ts in latest.items()]
    entries.sort(key=lambda e: e.queued_at)
    return entries


def clear_queue(project_root: Path, processed: list[Path]) -> None:
    """Remove processed entries from the queue.

    Entries whose source path is **not** in *processed* are preserved.
    If all entries are processed the queue file is emptied (retaining
    only the comment header).  The queue file is never deleted.

    Parameters
    ----------
    project_root:
        Absolute path to the project root.
    processed:
        Paths that have been successfully processed and should be removed.
    """
    queue_path = _queue_file(project_root)
    if not queue_path.exists():
        return

    processed_posix = {p.as_posix() for p in processed}

    surviving_data: list[str] = []
    for line in queue_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        parts = stripped.rsplit(" ", maxsplit=1)
        if len(parts) != 2:
            surviving_data.append(line)
            continue

        raw_path = parts[0]
        if raw_path not in processed_posix:
            surviving_data.append(line)

    # Always write the header.  Append surviving data lines after it.
    content = QUEUE_HEADER
    if surviving_data:
        content += "\n".join(surviving_data) + "\n"
    queue_path.write_text(content)
