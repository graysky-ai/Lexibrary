"""Parser for playbook file artifacts from markdown format."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from lexibrary.artifacts.playbook import PlaybookFile, PlaybookFileFrontmatter

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def extract_overview(body: str) -> str:
    """Extract the first paragraph from the body as the playbook overview.

    The overview is the text up to the first blank line.  If the body is
    empty or starts with a blank line, the overview is an empty string.
    """
    stripped = body.strip()
    if not stripped:
        return ""

    # Split on the first blank line (double newline)
    parts = re.split(r"\n\s*\n", stripped, maxsplit=1)
    return parts[0].strip()


def parse_playbook_file(path: Path) -> PlaybookFile | None:
    """Parse a playbook file into a PlaybookFile model.

    Returns None if the file doesn't exist, has no frontmatter, or
    frontmatter fails validation.
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
        frontmatter = PlaybookFileFrontmatter(**data)
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        # Pydantic validation errors are ValueError subclasses
        logger.debug("Failed to parse playbook frontmatter in %s: %s", path, exc)
        return None

    body = text[fm_match.end() :]
    overview = extract_overview(body)

    return PlaybookFile(
        frontmatter=frontmatter,
        body=body,
        overview=overview,
        file_path=path,
    )
