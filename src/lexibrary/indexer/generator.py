"""Index generator: produces AIndexFile models from directory contents."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_parser import parse_aindex
from lexibrary.artifacts.design_file import StalenessMetadata
from lexibrary.artifacts.design_file_parser import parse_design_file_frontmatter
from lexibrary.ignore.matcher import IgnoreMatcher
from lexibrary.utils.hashing import hash_string
from lexibrary.utils.languages import EXTENSION_MAP
from lexibrary.utils.paths import aindex_path, mirror_path

_GENERATOR_ID = "lexibrary-v2"

# ---------------------------------------------------------------------------
# Structural-description detection (Task 1.1)
# ---------------------------------------------------------------------------

_STRUCTURAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^.+ source \(\d+ lines\)$"),  # "{Language} source ({N} lines)"
    re.compile(r"^Binary file \(\.\w+\)$"),  # "Binary file (.ext)"
    re.compile(r"^Unknown file type$"),  # "Unknown file type"
    re.compile(r"^Contains \d+ files$"),  # "Contains {N} files"
    re.compile(r"^Contains \d+ files, \d+ subdirectories$"),
    re.compile(r"^Contains \d+ items$"),  # "Contains {N} items"
    re.compile(r"^Empty directory\.$"),  # "Empty directory."
    re.compile(r"^Directory containing .+\.$"),  # Legacy billboard patterns
    re.compile(r"^Mixed-language directory \(.+\)\.$"),  # Legacy billboard patterns
    re.compile(r"^\d+ .+ files$"),  # Extension-based summary: "{N} Python files"
    re.compile(r"^Mixed: .+$"),  # Extension-based summary: "Mixed: ..."
    re.compile(r"^\d+ files$"),  # Count fallback: "{N} files"
    re.compile(r"^\d+ subdirectories$"),  # Count fallback: "{N} subdirectories"
    re.compile(r"^\d+ files, \d+ subdirectories$"),
    re.compile(r"^\d+ entries$"),  # Extension fallback: "{N} entries"
]


def is_structural_description(description: str) -> bool:
    """Return True if *description* was produced by structural generators."""
    if not description:
        return False
    return any(pat.match(description) for pat in _STRUCTURAL_PATTERNS)


# ---------------------------------------------------------------------------
# Role-fragment extraction (Task 1.2)
# ---------------------------------------------------------------------------

_LEADING_VERB_RE = re.compile(
    r"^(?:"
    r"Acts?\s+as"  # "Acts as / Act as"
    r"|Defines?"  # "Defines / Define" (suffix ides? misses -ines)
    r"|Reads?"  # "Reads / Read"
    r"|Wraps?"  # "Wraps / Wrap"
    r"|[A-Z][a-zA-Z]+(?:"
    r"izes?"  # Initializes, Organizes
    r"|ates?"  # Generates, Creates, Coordinates, Validates
    r"|ures?"  # Ensures, Configures, Captures
    r"|ides?"  # Provides, Defines, Guides
    r"|dles?"  # Handles, Bundles
    r"|oses?"  # Exposes, Composes
    r"|ages?"  # Manages, Packages
    r"|ers?\b"  # Registers, Renders, Discovers
    r"|ains\b"  # Maintains, Contains
    r"|ites\b"  # Writes
    r"|ilds\b"  # Builds
    r"|ments\b"  # Implements
    r")"
    r")"
    r"(?:\s+(?:a|an|the|and|or|is|its|all|this|that|any))?\s+",
    re.IGNORECASE,
)

_CLAUSE_MARKERS = (
    " that ",
    " so ",
    " which ",
    " without ",
    " keeping ",
    " used by ",
    " used to ",
)

_TRAILING_STRIP: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "to",
        "by",
        "for",
        "of",
        "and",
        "or",
        "how",
        "that",
        "with",
        "from",
        "is",
        "its",
        "as",
        "in",
        "on",
        "at",
        "so",
        "but",
        "because",
        "when",
        "where",
        "which",
        "while",
        "if",
    }
)


def _extract_role_fragment(description: str) -> str:
    """Strip leading verb phrases and truncate at clause markers."""
    fragment = _LEADING_VERB_RE.sub("", description)
    # Truncate at the first clause marker that appears after at least 10 chars
    for marker in _CLAUSE_MARKERS:
        pos = fragment.find(marker)
        if pos >= 10:
            fragment = fragment[:pos]
            break
    # Strip trailing functional words that add no meaning
    words = fragment.split()
    while words and words[-1].lower() in _TRAILING_STRIP:
        words.pop()
    return " ".join(words)


# ---------------------------------------------------------------------------
# Stop words for keyword scoring (Task 1.3)
# ---------------------------------------------------------------------------

_STOP_WORDS: set[str] = {
    "the",
    "a",
    "an",
    "for",
    "in",
    "of",
    "to",
    "as",
    "by",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "with",
    "from",
    "on",
    "at",
    "it",
    "its",
    "this",
    "that",
    "small",
    "stable",
    "simple",
    "single",
    "centralized",
    "lightweight",
    "reusable",
    "focused",
    "strict",
    "tolerant",
    "function",
    "utility",
    "helper",
    "module",
    "package",
    "file",
}


def _keywords(text: str) -> set[str]:
    """Extract scoring keywords: words >= 3 chars, not stop words."""
    return {
        w.lower()
        for w in re.findall(r"[A-Za-z0-9_]+", text)
        if len(w) >= 3 and w.lower() not in _STOP_WORDS
    }


def _candidate_fragments(descriptions: list[str]) -> list[str]:
    """Pre-split descriptions on embedded semicolons before fragment extraction.

    Many design-file descriptions already encode multiple sub-clauses separated
    by semicolons (e.g. "configuration schema; two-tier loader; public namespace").
    Passing these as a single string to _extract_role_fragment() causes the
    8-word cap to fire mid-sub-clause.  Splitting first lets each sub-clause
    be extracted cleanly as its own candidate.
    """
    candidates: list[str] = []
    for d in descriptions:
        parts = [p.strip() for p in d.split(";") if p.strip()]
        candidates.extend(parts)
    return candidates


def _synthesize_summary(descriptions: list[str]) -> str:
    """Produce a concise directory summary from rich descriptions.

    - <=3 descriptions: join fragments with "; "
    - >3 descriptions: keyword-frequency scoring, top 3, overlap dedup

    Fragments are extracted with leading verbs stripped and clause markers
    truncated; no post-join truncation is applied so every fragment is
    always a complete atomic phrase.
    """
    if not descriptions:
        return ""

    fragments = [_extract_role_fragment(d) for d in _candidate_fragments(descriptions)]

    if len(fragments) <= 3:
        result = "; ".join(fragments)
    else:
        # Score by keyword frequency across all fragments
        all_kw_counts: Counter[str] = Counter()
        frag_keywords = [_keywords(f) for f in fragments]
        for kws in frag_keywords:
            all_kw_counts.update(kws)

        scored = []
        for i, frag in enumerate(fragments):
            score = sum(all_kw_counts[kw] for kw in frag_keywords[i])
            scored.append((score, i, frag))
        scored.sort(key=lambda t: (-t[0], t[1]))

        selected: list[str] = []
        selected_kws: list[set[str]] = []
        for _, idx, frag in scored:
            if len(selected) >= 3:
                break
            kws = frag_keywords[idx]
            # Check overlap dedup: skip if >50% overlap with already selected
            if kws and any(len(kws & sel_kw) / len(kws) > 0.5 for sel_kw in selected_kws if sel_kw):
                continue
            selected.append(frag)
            selected_kws.append(kws)

        result = "; ".join(selected)

    return result


# ---------------------------------------------------------------------------
# Extension-based summary (Task 1.4)
# ---------------------------------------------------------------------------


def _extension_based_summary(extensions: Counter[str], total_entries: int) -> str:
    """Produce an extension-based summary for Tier 2 fallback."""
    lang_counts: Counter[str] = Counter()
    for ext, count in extensions.items():
        lang = EXTENSION_MAP.get(ext)
        if lang is not None:
            lang_counts[lang] += count

    if not lang_counts:
        return f"{total_entries} entries"

    if len(lang_counts) == 1:
        lang, count = next(iter(lang_counts.items()))
        noun = "file" if count == 1 else "files"
        return f"{count} {lang} {noun}"

    top = lang_counts.most_common(3)
    parts = [f"{count} {lang}" for lang, count in top]
    return f"Mixed: {', '.join(parts)}"


def _get_structural_description(file_path: Path, binary_extensions: set[str]) -> str:
    """Return a structural description string for a file entry."""
    ext = file_path.suffix.lower()
    if ext in binary_extensions:
        return f"Binary file ({ext})"
    language = EXTENSION_MAP.get(ext)
    if language is None:
        return "Unknown file type"
    try:
        line_count = len(file_path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        line_count = 0
    return f"{language} source ({line_count} lines)"


def _get_file_description(
    file_path: Path,
    binary_extensions: set[str],
    project_root: Path,
) -> str:
    """Return a description for a file entry.

    Checks the design file frontmatter in the .lexibrary mirror tree first.
    If a non-empty description is found there, it is used. Otherwise falls
    back to a structural description (language + line count).
    """
    design_path = mirror_path(project_root, file_path)
    frontmatter = parse_design_file_frontmatter(design_path)
    if frontmatter is not None and frontmatter.description.strip():
        return frontmatter.description.strip()

    return _get_structural_description(file_path, binary_extensions)


def _get_dir_description(subdir: Path, project_root: Path) -> str:
    """Return a description for a subdirectory entry.

    Uses the child .aindex billboard when it is non-structural; otherwise
    falls back to file/dir counts from the child .aindex; if no child
    .aindex exists, counts direct filesystem children.
    """
    mirror_aindex = aindex_path(project_root, subdir)
    child_aindex = parse_aindex(mirror_aindex)
    if child_aindex is not None:
        # Tier 1: use child billboard if non-structural
        if child_aindex.billboard and not is_structural_description(child_aindex.billboard):
            return child_aindex.billboard
        # Tier 2: count-based from child .aindex entries
        file_count = sum(1 for e in child_aindex.entries if e.entry_type == "file")
        dir_count = sum(1 for e in child_aindex.entries if e.entry_type == "dir")
        if dir_count:
            return f"Contains {file_count} files, {dir_count} subdirectories"
        return f"Contains {file_count} files"
    # Tier 3: count direct children in the filesystem
    try:
        count = sum(1 for _ in subdir.iterdir())
    except OSError:
        count = 0
    return f"Contains {count} items"


def _generate_billboard(entries: list[AIndexEntry]) -> str:
    """Generate a billboard using three-tier fallback.

    Tier 1: synthesize from rich (non-structural) descriptions.
    Tier 2: extension-based summary from file entries.
    Tier 3: count-based fallback.
    """
    if not entries:
        return "Empty directory."

    # Collect rich descriptions (Tier 1 candidates)
    rich_descriptions: list[str] = []
    extensions: Counter[str] = Counter()
    file_count = 0
    dir_count = 0

    for entry in entries:
        if entry.entry_type == "file":
            file_count += 1
            ext = Path(entry.name).suffix.lower()
            if ext:
                extensions[ext] += 1
            if not is_structural_description(entry.description):
                rich_descriptions.append(entry.description)
        elif entry.entry_type == "dir":
            dir_count += 1

    # Tier 1: rich descriptions available
    if rich_descriptions:
        summary = _synthesize_summary(rich_descriptions)
        if summary:
            return summary

    # Tier 2: extension-based summary
    if extensions:
        ext_summary = _extension_based_summary(extensions, len(entries))
        # Only use if we got a language-based summary (not just "{N} entries")
        if not ext_summary.endswith(" entries"):
            return ext_summary

    # Tier 3: count fallback
    if file_count and dir_count:
        return f"{file_count} files, {dir_count} subdirectories"
    if file_count:
        return f"{file_count} files"
    if dir_count:
        return f"{dir_count} subdirectories"
    return f"{len(entries)} files"


def _compute_dir_hash(names: list[str]) -> str:
    """SHA-256 of the sorted directory listing."""
    content = "\n".join(sorted(names))
    return hash_string(content)


def generate_aindex(
    directory: Path,
    project_root: Path,
    ignore_matcher: IgnoreMatcher,
    binary_extensions: set[str],
) -> AIndexFile:
    """Generate an AIndexFile model for *directory* without any I/O side effects.

    Lists directory contents, filters ignored entries, builds structural
    descriptions for files and subdirs, and computes a staleness hash.
    """
    try:
        children = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        children = []

    entries: list[AIndexEntry] = []
    all_names: list[str] = []

    for child in children:
        if child.is_dir():
            if not ignore_matcher.should_descend(child):
                continue
        elif ignore_matcher.is_ignored(child):
            continue
        all_names.append(child.name)
        if child.is_file():
            description = _get_file_description(child, binary_extensions, project_root)
            entries.append(
                AIndexEntry(
                    name=child.name,
                    entry_type="file",
                    description=description,
                )
            )
        elif child.is_dir():
            description = _get_dir_description(child, project_root)
            entries.append(
                AIndexEntry(
                    name=child.name,
                    entry_type="dir",
                    description=description,
                )
            )

    billboard = _generate_billboard(entries)
    source_hash = _compute_dir_hash(all_names)

    try:
        rel_source = str(directory.relative_to(project_root))
    except ValueError:
        rel_source = str(directory)

    metadata = StalenessMetadata(
        source=rel_source,
        source_hash=source_hash,
        generated=datetime.now(UTC).replace(tzinfo=None),
        generator=_GENERATOR_ID,
    )

    return AIndexFile(
        directory_path=rel_source,
        billboard=billboard,
        entries=entries,
        metadata=metadata,
    )
