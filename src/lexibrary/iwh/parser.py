"""Parser for IWH files from markdown format with YAML frontmatter."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from lexibrary.iwh.model import IWHFile

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def parse_iwh(path: Path) -> IWHFile | None:
    """Parse an IWH file into an IWHFile model.

    Follows the same frontmatter regex pattern as ``stack/parser.py``.

    Returns ``None`` if the file doesn't exist, has no valid frontmatter,
    or frontmatter fails validation.
    """
    if not path.exists():
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None

    try:
        data = yaml.safe_load(fm_match.group(1))
        if not isinstance(data, dict):
            return None
        iwh = IWHFile(**data)
    except (yaml.YAMLError, TypeError, ValueError):
        return None

    # Extract body: everything after the closing frontmatter delimiter
    body = text[fm_match.end() :]
    # Strip a single leading newline if present (frontmatter pattern may
    # consume the trailing newline of ``---``).
    return iwh.model_copy(update={"body": body.strip("\n") if body.strip() else ""})
