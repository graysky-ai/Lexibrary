"""Writer for IWH files with directory creation and overwrite semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.iwh.model import IWHFile, IWHScope
from lexibrary.iwh.serializer import serialize_iwh

IWH_FILENAME = ".iwh"


def write_iwh(
    directory: Path,
    *,
    author: str,
    scope: IWHScope,
    body: str = "",
) -> Path:
    """Write an IWH file to the specified directory.

    Creates parent directories if they do not exist.  Overwrites any
    existing ``.iwh`` file in the directory (latest signal wins).

    Args:
        directory: Target directory for the ``.iwh`` file.
        author: Agent identifier that created the signal.
        scope: Severity level of the signal.
        body: Free-form markdown body (may be empty).

    Returns:
        Path to the written ``.iwh`` file.
    """
    iwh = IWHFile(
        author=author,
        created=datetime.now(UTC),
        scope=scope,
        body=body,
    )
    text = serialize_iwh(iwh)

    directory.mkdir(parents=True, exist_ok=True)
    iwh_path = directory / IWH_FILENAME
    iwh_path.write_text(text, encoding="utf-8")
    return iwh_path
