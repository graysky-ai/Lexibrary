"""Reader functions for IWH files with optional consume-on-read."""

from __future__ import annotations

import contextlib
from pathlib import Path

from lexibrary.iwh.model import IWHFile
from lexibrary.iwh.parser import parse_iwh
from lexibrary.utils.paths import LEXIBRARY_DIR

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


def find_all_iwh(project_root: Path) -> list[tuple[Path, IWHFile]]:
    """Discover all IWH files under ``.lexibrary/``.

    Walks the ``.lexibrary/`` directory tree for ``.iwh`` files, parses
    each, and returns a list of ``(source_directory_relative, IWHFile)``
    tuples.  The ``source_directory_relative`` is the mirror path reversed
    back to the corresponding source directory, relative to *project_root*.

    Under the design-file mirror layout, IWH files live under
    ``.lexibrary/designs/<src-path>/.iwh``.  This function strips the
    ``designs/`` prefix so the returned path is source-relative (e.g.,
    ``src/auth``) and can be joined directly to ``project_root`` to point
    at a valid source directory.

    Unparseable ``.iwh`` files are silently skipped.

    Args:
        project_root: Absolute path to the project root.

    Returns:
        List of ``(relative_source_dir, IWHFile)`` tuples, sorted by path.
    """
    lexibrary_dir = project_root / LEXIBRARY_DIR
    if not lexibrary_dir.is_dir():
        return []

    results: list[tuple[Path, IWHFile]] = []
    for iwh_file_path in sorted(lexibrary_dir.rglob(IWH_FILENAME)):
        parsed = parse_iwh(iwh_file_path)
        if parsed is None:
            continue
        # Reverse the mirror path: .lexibrary/designs/src/auth/.iwh → src/auth
        try:
            relative = iwh_file_path.parent.relative_to(lexibrary_dir)
        except ValueError:
            continue
        # Strip 'designs/' prefix so callers get source-relative paths that
        # can be joined back to project_root to reach the source tree.
        if relative.parts[:1] == ("designs",):
            relative = Path(*relative.parts[1:])
        results.append((relative, parsed))

    return results
