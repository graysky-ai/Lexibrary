"""Wikilink resolver — maps ``[[wikilinks]]`` to artifacts.

Supports concepts, conventions, stack posts, playbooks, and designs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.artifacts.concept import ConceptFile
from lexibrary.artifacts.convention import ConventionFile
from lexibrary.artifacts.ids import parse_artifact_id
from lexibrary.conventions.index import ConventionIndex
from lexibrary.wiki.index import ConceptIndex

if TYPE_CHECKING:
    from lexibrary.artifacts.playbook import PlaybookFile
    from lexibrary.playbooks.index import PlaybookIndex

_BRACKET_RE = re.compile(r"^\[\[(.+?)\]\]$")
_ARTIFACT_ID_RE = re.compile(r"^[A-Z]{2}-\d{3,}$", re.IGNORECASE)
_PLAYBOOK_PREFIX_RE = re.compile(r"^playbook:\s*(.+)$", re.IGNORECASE)

# Maps artifact prefix to (kind name, directory basename under .lexibrary/)
_PREFIX_TO_DIR: dict[str, tuple[str, str]] = {
    "CN": ("concept", "concepts"),
    "CV": ("convention", "conventions"),
    "PB": ("playbook", "playbooks"),
    "ST": ("stack", "stack"),
    "DS": ("design", "designs"),
}


@dataclass(frozen=True)
class ResolvedLink:
    """A wikilink resolved to a concept, convention, stack post, playbook, or design."""

    raw: str
    name: str
    kind: str  # "concept", "stack", "alias", "convention", "playbook", or "design"
    path: Path | None = None


@dataclass(frozen=True)
class UnresolvedLink:
    """A wikilink that could not be resolved."""

    raw: str
    suggestions: list[str] = field(default_factory=list)


class WikilinkResolver:
    """Resolves wikilink references against concepts, conventions, stack posts,
    playbooks, and designs.

    Resolution chain (first match wins):

    1. Strip ``[[`` / ``]]`` brackets if present.
    2. If the text has a ``playbook:`` prefix, resolve against playbooks only
       (title match, alias fallback, fuzzy suggestions).
    3. If the text matches an artifact ID pattern (``CN-NNN``, ``CV-NNN``,
       ``PB-NNN``, ``DS-NNN``, ``ST-NNN``), resolve by scanning the
       appropriate artifact directory for a matching file.
    4. Convention exact title match (case-insensitive) -- convention-first.
    5. Convention alias match (case-insensitive).
    6. Exact concept name match (case-insensitive).
    7. Concept alias match (case-insensitive).
    8. Fuzzy match via :func:`difflib.get_close_matches` across all
       concept, convention, and playbook names/aliases.
    9. Unresolved -- attach up to 3 suggestions from fuzzy matching.
    """

    def __init__(
        self,
        index: ConceptIndex,
        stack_dir: Path | None = None,
        convention_dir: Path | None = None,
        playbook_dir: Path | None = None,
        designs_dir: Path | None = None,
    ) -> None:
        self._index = index
        self._stack_dir = stack_dir
        self._designs_dir = designs_dir
        self._convention_index: ConventionIndex | None = None
        self._playbook_index: PlaybookIndex | None = None

        # Build a lookup from prefix to directory for ID-based resolution
        self._prefix_dirs: dict[str, Path] = {}
        if stack_dir is not None:
            self._prefix_dirs["ST"] = stack_dir
        if convention_dir is not None:
            self._prefix_dirs["CV"] = convention_dir
        if playbook_dir is not None:
            self._prefix_dirs["PB"] = playbook_dir
        if designs_dir is not None:
            self._prefix_dirs["DS"] = designs_dir
        # CN is resolved via the ConceptIndex, not directory scanning

        if convention_dir is not None and convention_dir.is_dir():
            self._convention_index = ConventionIndex(convention_dir)
            self._convention_index.load()

        if playbook_dir is not None and playbook_dir.is_dir():
            from lexibrary.playbooks.index import PlaybookIndex as _PlaybookIndex  # noqa: PLC0415

            self._playbook_index = _PlaybookIndex(playbook_dir)
            self._playbook_index.load()

    def resolve(self, raw: str) -> ResolvedLink | UnresolvedLink:
        """Resolve a single wikilink string.

        *raw* may include ``[[brackets]]`` or be plain text.
        """
        stripped = _strip_brackets(raw)

        # Typed playbook prefix: [[playbook: Title]]
        playbook_match = _PLAYBOOK_PREFIX_RE.match(stripped)
        if playbook_match is not None:
            return self._resolve_playbook(raw, playbook_match.group(1).strip())

        # Universal artifact ID pattern (CN-001, CV-002, PB-003, DS-042, ST-001)
        if _ARTIFACT_ID_RE.match(stripped):
            return self._resolve_by_id(raw, stripped.upper())

        # Convention exact title match (convention-first)
        conv = self._find_convention_exact(stripped)
        if conv is not None:
            return ResolvedLink(
                raw=raw,
                name=conv.frontmatter.title,
                kind="convention",
                path=None,
            )

        # Convention alias match
        conv = self._find_convention_alias(stripped)
        if conv is not None:
            return ResolvedLink(
                raw=raw,
                name=conv.frontmatter.title,
                kind="convention",
                path=None,
            )

        # Exact concept name match
        concept = self._find_exact(stripped)
        if concept is not None:
            return ResolvedLink(
                raw=raw,
                name=concept.frontmatter.title,
                kind="concept",
                path=None,
            )

        # Concept alias match
        concept = self._find_alias(stripped)
        if concept is not None:
            return ResolvedLink(
                raw=raw,
                name=concept.frontmatter.title,
                kind="alias",
                path=None,
            )

        # Playbook exact title match (case-insensitive) — no prefix required
        pb = self._find_playbook_exact(stripped)
        if pb is not None:
            return ResolvedLink(
                raw=raw,
                name=pb.frontmatter.title,
                kind="playbook",
                path=pb.file_path,
            )

        # Fuzzy match (concepts + conventions + playbooks)
        all_names = self._all_names_and_aliases()
        close = get_close_matches(stripped.lower(), [n.lower() for n in all_names], n=3, cutoff=0.6)

        if close:
            # Map lowered matches back to original names
            lower_to_orig = {n.lower(): n for n in all_names}
            best = lower_to_orig.get(close[0])
            if best is not None:
                concept = self._index.find(best)
                if concept is not None:
                    return ResolvedLink(
                        raw=raw,
                        name=concept.frontmatter.title,
                        kind="concept",
                        path=None,
                    )
                # The fuzzy best match may be a playbook title; resolve it
                # rather than emitting it as a nonsensical suggestion.
                playbook_hit = self._find_playbook_exact(best)
                if playbook_hit is not None:
                    return ResolvedLink(
                        raw=raw,
                        name=playbook_hit.frontmatter.title,
                        kind="playbook",
                        path=playbook_hit.file_path,
                    )

            # Return as unresolved with suggestions
            suggestions = [lower_to_orig.get(c, c) for c in close]
            return UnresolvedLink(raw=raw, suggestions=suggestions)

        return UnresolvedLink(raw=raw)

    def resolve_all(self, links: list[str]) -> tuple[list[ResolvedLink], list[UnresolvedLink]]:
        """Resolve a batch of wikilink strings.

        Returns a tuple of (resolved, unresolved) lists.
        """
        resolved: list[ResolvedLink] = []
        unresolved: list[UnresolvedLink] = []
        for link in links:
            result = self.resolve(link)
            if isinstance(result, ResolvedLink):
                resolved.append(result)
            else:
                unresolved.append(result)
        return resolved, unresolved

    def _resolve_by_id(self, raw: str, artifact_id: str) -> ResolvedLink | UnresolvedLink:
        """Resolve an artifact ID (``XX-NNN``) to a concrete artifact.

        Dispatches to the appropriate resolution strategy based on prefix:
        - **CN**: Delegates to :meth:`ConceptIndex.find_by_id`.
        - **DS**: Scans design file frontmatter for a matching ``id:`` field.
        - **ST/CV/PB**: Scans the artifact directory for a file whose name
          starts with the ID.

        Returns :class:`UnresolvedLink` when the prefix is unrecognised or
        no matching artifact exists.
        """
        parsed = parse_artifact_id(artifact_id)
        if parsed is None:
            return UnresolvedLink(raw=raw)
        prefix, _ = parsed

        # Resolve prefix to kind name
        dir_info = _PREFIX_TO_DIR.get(prefix)
        if dir_info is None:
            return UnresolvedLink(raw=raw)
        kind, _ = dir_info

        # Concepts: delegate to ConceptIndex.find_by_id
        if prefix == "CN":
            concept = self._index.find_by_id(artifact_id)
            if concept is not None:
                return ResolvedLink(
                    raw=raw,
                    name=artifact_id,
                    kind="concept",
                    path=concept.file_path,
                )
            return UnresolvedLink(raw=raw)

        # Designs: scan frontmatter for matching id field
        if prefix == "DS":
            path = self._find_design_by_id(artifact_id)
            if path is not None:
                return ResolvedLink(
                    raw=raw,
                    name=artifact_id,
                    kind="design",
                    path=path,
                )
            return UnresolvedLink(raw=raw)

        # ST, CV, PB: filename-prefix scan in the appropriate directory
        directory = self._prefix_dirs.get(prefix)
        if directory is None or not directory.is_dir():
            return UnresolvedLink(raw=raw)

        pattern = f"{artifact_id}-*.md"
        matches = list(directory.glob(pattern))
        if matches:
            return ResolvedLink(
                raw=raw,
                name=artifact_id,
                kind=kind,
                path=matches[0],
            )
        return UnresolvedLink(raw=raw)

    def _find_design_by_id(self, design_id: str) -> Path | None:
        """Scan design file frontmatter for a matching ``id:`` field.

        Design files keep source-mirror paths (no ID in filename), so the
        ID is extracted from YAML frontmatter.
        """
        if self._designs_dir is None or not self._designs_dir.is_dir():
            return None
        from lexibrary.artifacts.ids import _FRONTMATTER_ID_RE  # noqa: PLC0415

        for md_file in self._designs_dir.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue
            lines = text.split("\n")
            if not lines or lines[0].rstrip() != "---":
                continue
            for line in lines[1:]:
                if line.rstrip() == "---":
                    break
                m = _FRONTMATTER_ID_RE.match(line)
                if m and m.group(1).upper() == design_id.upper():
                    return md_file
        return None

    def _find_playbook_exact(self, name: str) -> PlaybookFile | None:
        """Find a playbook by exact title (case-insensitive)."""
        if self._playbook_index is None:
            return None
        needle = name.strip().lower()
        for pb in self._playbook_index.playbooks:
            if pb.frontmatter.title.strip().lower() == needle:
                return pb
        return None

    def _find_convention_exact(self, name: str) -> ConventionFile | None:
        """Find convention by exact title (case-insensitive)."""
        if self._convention_index is None:
            return None
        needle = name.strip().lower()
        for conv in self._convention_index.conventions:
            if conv.frontmatter.title.strip().lower() == needle:
                return conv
        return None

    def _find_convention_alias(self, name: str) -> ConventionFile | None:
        """Find convention by alias (case-insensitive)."""
        if self._convention_index is None:
            return None
        needle = name.strip().lower()
        for conv in self._convention_index.conventions:
            for alias in conv.frontmatter.aliases:
                if alias.strip().lower() == needle:
                    return conv
        return None

    def _find_exact(self, name: str) -> ConceptFile | None:
        """Find concept by exact title (case-insensitive)."""
        needle = name.strip().lower()
        for concept in self._iter_concepts():
            if concept.frontmatter.title.strip().lower() == needle:
                return concept
        return None

    def _find_alias(self, name: str) -> ConceptFile | None:
        """Find concept by alias (case-insensitive)."""
        needle = name.strip().lower()
        for concept in self._iter_concepts():
            for alias in concept.frontmatter.aliases:
                if alias.strip().lower() == needle:
                    return concept
        return None

    def _iter_concepts(self) -> list[ConceptFile]:
        """Return all concepts from the index.

        Accesses the internal ``_concepts`` dict directly to avoid
        alias-collision issues with :meth:`ConceptIndex.find`.
        """
        # pylint: disable=protected-access
        return list(self._index._concepts.values())

    def _resolve_playbook(self, raw: str, title: str) -> ResolvedLink | UnresolvedLink:
        """Resolve a ``playbook:``-prefixed wikilink.

        Resolution order: exact title match, alias fallback, fuzzy suggestions.
        """
        if self._playbook_index is None:
            return UnresolvedLink(raw=raw)

        needle = title.strip().lower()

        # Exact title match (case-insensitive)
        for pb in self._playbook_index.playbooks:
            if pb.frontmatter.title.strip().lower() == needle:
                return ResolvedLink(
                    raw=raw,
                    name=pb.frontmatter.title,
                    kind="playbook",
                    path=pb.file_path,
                )

        # Alias match (case-insensitive)
        for pb in self._playbook_index.playbooks:
            for alias in pb.frontmatter.aliases:
                if alias.strip().lower() == needle:
                    return ResolvedLink(
                        raw=raw,
                        name=pb.frontmatter.title,
                        kind="playbook",
                        path=pb.file_path,
                    )

        # Fuzzy suggestions
        all_pb_names = self._all_playbook_names_and_aliases()
        close = get_close_matches(needle, [n.lower() for n in all_pb_names], n=3, cutoff=0.6)
        if close:
            lower_to_orig = {n.lower(): n for n in all_pb_names}
            suggestions = [lower_to_orig.get(c, c) for c in close]
            return UnresolvedLink(raw=raw, suggestions=suggestions)

        return UnresolvedLink(raw=raw)

    def _all_playbook_names_and_aliases(self) -> list[str]:
        """Collect all playbook titles and aliases for fuzzy matching."""
        result: list[str] = []
        if self._playbook_index is not None:
            for pb in self._playbook_index.playbooks:
                result.append(pb.frontmatter.title)
                result.extend(pb.frontmatter.aliases)
        return result

    def _all_names_and_aliases(self) -> list[str]:
        """Collect all concept, convention, and playbook names and aliases for fuzzy matching."""
        result: list[str] = []
        for concept in self._iter_concepts():
            result.append(concept.frontmatter.title)
            result.extend(concept.frontmatter.aliases)
        if self._convention_index is not None:
            for conv in self._convention_index.conventions:
                result.append(conv.frontmatter.title)
                result.extend(conv.frontmatter.aliases)
        result.extend(self._all_playbook_names_and_aliases())
        return result


def _strip_brackets(text: str) -> str:
    """Remove ``[[`` / ``]]`` brackets if present."""
    m = _BRACKET_RE.match(text.strip())
    if m:
        return m.group(1)
    return text.strip()
