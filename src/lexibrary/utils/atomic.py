"""Atomic file write utility.

Uses temp-file + os.replace() to ensure readers never see partially-written files.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write(
    target: Path,
    content: str,
    encoding: str = "utf-8",
) -> None:
    """Write content to target path atomically.

    Creates a temp file in the same directory as the target, writes the
    content, then atomically replaces the target via ``os.replace()``.
    This guarantees readers see either the old or new version, never a
    partial write.

    Args:
        target: Destination file path.
        content: Text content to write.
        encoding: Text encoding (default ``"utf-8"``).

    Raises:
        OSError: On write failure (original file unchanged, temp cleaned up).
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd = -1
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp",
            dir=target.parent,
        )
        os.write(fd, content.encode(encoding))
        os.close(fd)
        fd = -1  # mark as closed so finally doesn't double-close
        os.replace(tmp_path, target)
        tmp_path = None  # replace succeeded; nothing to clean up
    finally:
        if fd >= 0:
            os.close(fd)
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
