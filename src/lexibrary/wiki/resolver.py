"""Wikilink resolver — maps ``[[wikilinks]]`` to artifacts.

Supports concepts, conventions, stack posts, and playbooks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.artifacts.concept import ConceptFile
from lexibrary.artifacts.convention import ConventionFile
from lexibrary.conventions.index import ConventionIndex
from lexibrary.wiki.index import ConceptIndex

if TYPE_CHECKING:
    from lexibrary.playbooks.index import PlaybookIndex

_BRACKET_RE = re.compile(r"^\[\[(.+?)\]\]$")
_STACK_RE = re.compile(r"^ST-\d{3,}$", re.IGNORECASE)
_PLAYBOOK_PREFIX_RE = re.compile(r"^playbook:\s*(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedLink:
    """A wikilink resolved to a concept, convention, stack post, or playbook."""

    raw: str
    name: str
    kind: str  # "concept", "stack", "alias", "convention", or "playbook"
    path: Path | None = None


@dataclass(frozen=True)
class UnresolvedLink:
    """A wikilink that could not be resolved."""

    raw: str
    suggestions: list[str] = field(default_factory=list)


class WikilinkResolver:
    """Resolves wikilink references against concepts, conventions, stack posts, and playbooks.

    Resolution chain (first match wins):

    1. Strip ``[[`` / ``]]`` brackets if present.
    2. If the text has a ``playbook:`` prefix, resolve against playbooks only
       (title match, alias fallback, fuzzy suggestions).
    3. If the text matches ``ST-NNN`` stack pattern, scan *stack_dir* for
       a matching ``ST-NNN-*.md`` file and resolve as stack post.
    4. Convention exact title match (case-insensitive) — convention-first.
    5. Convention alias match (case-insensitive).
    6. Exact concept name match (case-insensitive).
    7. Concept alias match (case-insensitive).
    8. Fuzzy match via :func:`difflib.get_close_matches` across all
       concept, convention, and playbook names/aliases.
    9. Unresolved — attach up to 3 suggestions from fuzzy matching.
    """

    def __init__(
        self,
        index: ConceptIndex,
        stack_dir: Path | None = None,
        convention_dir: Path | None = None,
        playbook_dir: Path | None = None,
    ) -> None:
        self._index = index
        self._stack_dir = stack_dir
        self._convention_index: ConventionIndex | None = None
        self._playbook_index: PlaybookIndex | None = None

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

        # Stack post pattern (ST-001, ST-042, etc.)
        if _STACK_RE.match(stripped):
            stack_id = stripped.upper()
            path = self._find_stack_file(stack_id)
            if path is not None:
                return ResolvedLink(
                    raw=raw,
                    name=stack_id,
                    kind="stack",
                    path=path,
                )
            # Stack ID pattern matched but no file found — unresolved
            return UnresolvedLink(raw=raw)

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

        # Fuzzy match (concepts + conventions)
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

    def _find_stack_file(self, stack_id: str) -> Path | None:
        """Find a stack post file matching the given ID via glob."""
        if self._stack_dir is None or not self._stack_dir.is_dir():
            return None
        pattern = f"{stack_id}-*.md"
        matches = list(self._stack_dir.glob(pattern))
        if matches:
            return matches[0]
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
