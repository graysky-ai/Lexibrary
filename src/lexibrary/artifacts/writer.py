"""Atomic artifact file writer.

Writes content to a target path atomically using a temporary file
alongside the target, then renames it into place.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_artifact(target: Path, content: str) -> Path:
    """Write content to target path atomically.

    Creates parent directories if needed, writes to a temporary file in the
    same directory as the target, then renames the temp file to the target
    (atomic on POSIX when on the same filesystem).

    Args:
        target: Destination file path.
        content: UTF-8 string content to write.

    Returns:
        The target path.
    """
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path_str = tempfile.mkstemp(
        suffix=".tmp",
        dir=target.parent,
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        tmp_path.rename(target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return target
