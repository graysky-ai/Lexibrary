"""Title collision detection for artifact creation.

Scans existing artifacts (concepts, conventions, playbooks, stack posts) for
title matches and returns same-type blocking matches and cross-type warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Lightweight regex for extracting title from frontmatter (avoids full YAML parse)
_FRONTMATTER_TITLE_RE = re.compile(r"^title:\s*['\"]?(.+?)['\"]?\s*$", re.MULTILINE)

# Artifact kind to directory name mapping
_KIND_DIRS: dict[str, str] = {
    "concept": "concepts",
    "convention": "conventions",
    "playbook": "playbooks",
    "stack": "stack",
}


@dataclass
class TitleMatch:
    """A matching artifact found during title collision scanning."""

    kind: str
    title: str
    file_path: Path


@dataclass
class TitleCheckResult:
    """Result of a title collision check.

    Attributes
    ----------
    same_type:
        Matches of the same artifact kind (should block creation).
    cross_type:
        Matches of different artifact kinds (should warn but not block).
    """

    same_type: list[TitleMatch] = field(default_factory=list)
    cross_type: list[TitleMatch] = field(default_factory=list)

    @property
    def has_same_type(self) -> bool:
        """Return True if there are same-type matches (creation should be blocked)."""
        return len(self.same_type) > 0

    @property
    def has_cross_type(self) -> bool:
        """Return True if there are cross-type matches (should warn)."""
        return len(self.cross_type) > 0


def _extract_title(md_file: Path) -> str | None:
    """Extract the ``title:`` field from a markdown file's YAML frontmatter.

    Uses a lightweight regex scan rather than a full YAML parse, reading only
    the frontmatter block (between the first two ``---`` delimiters).

    Returns ``None`` if no valid title is found.
    """
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError:
        return None

    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return None

    # Collect only frontmatter lines
    fm_lines: list[str] = []
    for line in lines[1:]:
        if line.rstrip() == "---":
            break
        fm_lines.append(line)
    else:
        # No closing --- found
        return None

    fm_text = "\n".join(fm_lines)
    m = _FRONTMATTER_TITLE_RE.search(fm_text)
    if m:
        return m.group(1).strip()
    return None


def _scan_directory(directory: Path, kind: str) -> list[TitleMatch]:
    """Scan all ``.md`` files in *directory* and return title matches."""
    matches: list[TitleMatch] = []
    if not directory.is_dir():
        return matches

    for md_file in sorted(directory.glob("*.md")):
        title = _extract_title(md_file)
        if title:
            matches.append(TitleMatch(kind=kind, title=title, file_path=md_file))

    return matches


def find_title_matches(
    title: str,
    kind: str,
    project_root: Path,
) -> TitleCheckResult:
    """Scan for existing artifacts with matching titles.

    Parameters
    ----------
    title:
        The title of the artifact being created.
    kind:
        The artifact kind being created (``"concept"``, ``"convention"``,
        ``"playbook"``, or ``"stack"``).
    project_root:
        The project root directory (parent of ``.lexibrary/``).

    Returns
    -------
    TitleCheckResult
        Contains ``same_type`` matches (should block creation) and
        ``cross_type`` matches (should warn).
    """
    result = TitleCheckResult()
    normalized_title = title.strip().lower()
    lib_dir = project_root / ".lexibrary"

    for scan_kind, dir_name in _KIND_DIRS.items():
        scan_dir = lib_dir / dir_name
        for match in _scan_directory(scan_dir, scan_kind):
            if match.title.strip().lower() == normalized_title:
                if scan_kind == kind:
                    result.same_type.append(match)
                else:
                    result.cross_type.append(match)

    return result
