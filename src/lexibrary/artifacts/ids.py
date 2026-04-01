"""Unified artifact ID system for Lexibrary.

Provides prefix registry, ID parsing/validation, and sequential ID generation
for all artifact types: concepts (CN), conventions (CV), playbooks (PB),
designs (DS), and stack posts (ST).
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Prefix registry
# ---------------------------------------------------------------------------

ARTIFACT_PREFIXES: dict[str, str] = {
    "concept": "CN",
    "convention": "CV",
    "playbook": "PB",
    "design": "DS",
    "stack": "ST",
}

_PREFIX_SET = frozenset(ARTIFACT_PREFIXES.values())

# Reverse mapping: 2-letter prefix -> kind name (derived from ARTIFACT_PREFIXES).
_PREFIX_TO_KIND: dict[str, str] = {v: k for k, v in ARTIFACT_PREFIXES.items()}

# Kind -> subdirectory name under ``.lexibrary/``.
_KIND_TO_DIR: dict[str, str] = {
    "concept": "concepts",
    "convention": "conventions",
    "playbook": "playbooks",
    "design": "designs",
    "stack": "stack",
}

# XX-NNN where XX is exactly 2 uppercase letters, NNN is 3+ digits
_ARTIFACT_ID_RE = re.compile(r"^([A-Z]{2})-(\d{3,})$")

# Lightweight regex for extracting id from frontmatter lines (no full YAML parse)
_FRONTMATTER_ID_RE = re.compile(r"^id:\s*(\S+)")


def prefix_for_kind(kind: str) -> str:
    """Return the 2-letter prefix for a given artifact kind.

    Raises ``KeyError`` if the kind is not recognised.
    """
    return ARTIFACT_PREFIXES[kind]


def kind_for_prefix(prefix: str) -> str | None:
    """Return the artifact kind for a 2-letter prefix, or ``None`` if unknown.

    Example: ``kind_for_prefix("CN")`` returns ``"concept"``.
    """
    return _PREFIX_TO_KIND.get(prefix)


def dir_for_kind(kind: str) -> str:
    """Return the ``.lexibrary/`` subdirectory name for an artifact kind.

    Example: ``dir_for_kind("concept")`` returns ``"concepts"``.

    Raises ``KeyError`` if the kind is not recognised.
    """
    return _KIND_TO_DIR[kind]


# ---------------------------------------------------------------------------
# ID validation and parsing
# ---------------------------------------------------------------------------


def is_artifact_id(text: str) -> bool:
    """Return ``True`` if *text* matches the ``XX-NNN`` artifact ID format."""
    return _ARTIFACT_ID_RE.match(text) is not None


def parse_artifact_id(text: str) -> tuple[str, int] | None:
    """Parse an artifact ID into ``(prefix, number)`` or return ``None``."""
    m = _ARTIFACT_ID_RE.match(text)
    if m is None:
        return None
    return m.group(1), int(m.group(2))


# ---------------------------------------------------------------------------
# Sequential ID generation
# ---------------------------------------------------------------------------


def next_artifact_id(prefix: str, directory: Path, glob_pattern: str) -> str:
    """Generate the next sequential ID by scanning filenames in *directory*.

    Parameters
    ----------
    prefix:
        The 2-letter artifact prefix (e.g. ``"CN"``).
    directory:
        The directory to scan for existing files.
    glob_pattern:
        A glob pattern to match existing artifact files
        (e.g. ``"CN-*-*.md"``).

    Returns
    -------
    str
        The next ID in ``XX-NNN`` format (zero-padded to at least 3 digits).
    """
    max_num = 0
    if directory.is_dir():
        id_re = re.compile(rf"^{re.escape(prefix)}-(\d+)")
        for f in directory.glob(glob_pattern):
            m = id_re.match(f.name)
            if m:
                max_num = max(max_num, int(m.group(1)))
    return f"{prefix}-{max_num + 1:03d}"


def next_design_id(designs_dir: Path) -> str:
    """Generate the next design ID by scanning frontmatter ``id:`` fields.

    Design files keep their source-mirror paths (no ID in filename), so the
    ID is extracted from the YAML frontmatter of each ``.md`` file under
    *designs_dir*.

    Parameters
    ----------
    designs_dir:
        The ``.lexibrary/designs/`` directory to scan recursively.

    Returns
    -------
    str
        The next design ID in ``DS-NNN`` format.
    """
    max_num = 0
    if designs_dir.is_dir():
        for md_file in designs_dir.rglob("*.md"):
            max_num = max(max_num, _extract_design_id_number(md_file))
    return f"DS-{max_num + 1:03d}"


def _extract_design_id_number(md_file: Path) -> int:
    """Extract the numeric portion of a DS-NNN id from a file's frontmatter.

    Returns 0 if no valid design ID is found.
    """
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError:
        return 0

    # Only look within YAML frontmatter (between first two '---' lines)
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return 0

    for line in lines[1:]:
        if line.rstrip() == "---":
            break
        m = _FRONTMATTER_ID_RE.match(line)
        if m:
            parsed = parse_artifact_id(m.group(1))
            if parsed is not None and parsed[0] == "DS":
                return parsed[1]
    return 0


# ---------------------------------------------------------------------------
# Artifact path resolution
# ---------------------------------------------------------------------------


def find_artifact_path(project_root: Path, artifact_id: str) -> Path | None:
    """Resolve an artifact ID to its file path on disk.

    For non-design types (concepts, conventions, playbooks, stack posts),
    files are found by globbing for ``<ID>-*`` in the appropriate
    ``.lexibrary/<subdir>/`` directory.

    For design files, all ``.md`` files under ``.lexibrary/designs/`` are
    scanned for a frontmatter ``id:`` field matching *artifact_id*.

    Parameters
    ----------
    project_root:
        The project root directory (containing ``.lexibrary/``).
    artifact_id:
        An artifact ID in ``XX-NNN`` format (e.g. ``"CN-001"``).

    Returns
    -------
    Path | None
        The resolved file path, or ``None`` if no match is found.
    """
    parsed = parse_artifact_id(artifact_id)
    if parsed is None:
        return None

    prefix, _number = parsed
    kind = kind_for_prefix(prefix)
    if kind is None:
        return None

    subdir = dir_for_kind(kind)
    artifact_dir = project_root / ".lexibrary" / subdir

    if not artifact_dir.is_dir():
        return None

    if kind == "design":
        return _find_design_by_frontmatter_id(artifact_dir, artifact_id)

    # For non-design types, filenames start with the artifact ID.
    matches = list(artifact_dir.glob(f"{artifact_id}-*"))
    if matches:
        return matches[0]

    return None


def _find_design_by_frontmatter_id(designs_dir: Path, artifact_id: str) -> Path | None:
    """Scan design files for a frontmatter ``id:`` matching *artifact_id*.

    Uses lightweight regex scanning (no full YAML parse) for performance.
    """
    for md_file in designs_dir.rglob("*.md"):
        if _frontmatter_id_matches(md_file, artifact_id):
            return md_file
    return None


def _frontmatter_id_matches(md_file: Path, artifact_id: str) -> bool:
    """Return ``True`` if *md_file* has a frontmatter ``id:`` equal to *artifact_id*."""
    try:
        text = md_file.read_text(encoding="utf-8")
    except OSError:
        return False

    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        return False

    for line in lines[1:]:
        if line.rstrip() == "---":
            break
        m = _FRONTMATTER_ID_RE.match(line)
        if m and m.group(1) == artifact_id:
            return True
    return False
