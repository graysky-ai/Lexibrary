"""Reader functions for IWH files with optional consume-on-read."""

from __future__ import annotations

import contextlib
from pathlib import Path

from lexibrary.iwh.model import IWHFile
from lexibrary.iwh.parser import parse_iwh

IWH_FILENAME = ".iwh"


def read_iwh(directory: Path) -> IWHFile | None:
    """Read an IWH file from a directory without deleting it.

    Args:
        directory: Directory containing the ``.iwh`` file.

    Returns:
        Parsed ``IWHFile`` if the file exists and is valid, otherwise ``None``.
    """
    iwh_path = directory / IWH_FILENAME
    return parse_iwh(iwh_path)


def consume_iwh(directory: Path) -> IWHFile | None:
    """Read an IWH file from a directory and delete it.

    The file is always deleted, even if parsing fails (corrupt files are
    cleaned up rather than left to block subsequent agents).

    Args:
        directory: Directory containing the ``.iwh`` file.

    Returns:
        Parsed ``IWHFile`` if the file was valid, otherwise ``None``.
    """
    iwh_path = directory / IWH_FILENAME
    if not iwh_path.exists():
        return None

    result = parse_iwh(iwh_path)

    # Always delete the file, even if parsing failed
    with contextlib.suppress(OSError):
        iwh_path.unlink()

    return result
