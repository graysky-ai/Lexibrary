"""Wikilink resolver — maps ``[[wikilinks]]`` to concept files, conventions, or stack posts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path

from lexibrary.artifacts.concept import ConceptFile
from lexibrary.artifacts.convention import ConventionFile
from lexibrary.conventions.index import ConventionIndex
from lexibrary.wiki.index import ConceptIndex

_BRACKET_RE = re.compile(r"^\[\[(.+?)\]\]$")
_STACK_RE = re.compile(r"^ST-\d{3,}$", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedLink:
    """A wikilink that was successfully resolved to a concept, convention, or stack post."""

    raw: str
    name: str
    kind: str  # "concept", "stack", "alias", or "convention"
    path: Path | None = None


@dataclass(frozen=True)
class UnresolvedLink:
    """A wikilink that could not be resolved."""

    raw: str
    suggestions: list[str] = field(default_factory=list)


class WikilinkResolver:
    """Resolves wikilink references against concepts, conventions, and stack posts.

    Resolution chain (first match wins):

    1. Strip ``[[`` / ``]]`` brackets if present.
    2. If the text matches ``ST-NNN`` stack pattern, scan *stack_dir* for
       a matching ``ST-NNN-*.md`` file and resolve as stack post.
    3. Convention exact title match (case-insensitive) — convention-first.
    4. Convention alias match (case-insensitive).
    5. Exact concept name match (case-insensitive).
    6. Concept alias match (case-insensitive).
    7. Fuzzy match via :func:`difflib.get_close_matches` across all
       concept and convention names/aliases.
    8. Unresolved — attach up to 3 suggestions from fuzzy matching.
    """

    def __init__(
        self,
        index: ConceptIndex,
        stack_dir: Path | None = None,
        convention_dir: Path | None = None,
    ) -> None:
        self._index = index
        self._stack_dir = stack_dir
        self._convention_index: ConventionIndex | None = None

        if convention_dir is not None and convention_dir.is_dir():
            self._convention_index = ConventionIndex(convention_dir)
            self._convention_index.load()

    def resolve(self, raw: str) -> ResolvedLink | UnresolvedLink:
        """Resolve a single wikilink string.

        *raw* may include ``[[brackets]]`` or be plain text.
        """
        stripped = _strip_brackets(raw)

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

    def _all_names_and_aliases(self) -> list[str]:
        """Collect all concept and convention names and aliases for fuzzy matching."""
        result: list[str] = []
        for concept in self._iter_concepts():
            result.append(concept.frontmatter.title)
            result.extend(concept.frontmatter.aliases)
        if self._convention_index is not None:
            for conv in self._convention_index.conventions:
                result.append(conv.frontmatter.title)
                result.extend(conv.frontmatter.aliases)
        return result


def _strip_brackets(text: str) -> str:
    """Remove ``[[`` / ``]]`` brackets if present."""
    m = _BRACKET_RE.match(text.strip())
    if m:
        return m.group(1)
    return text.strip()
