"""Concept index for searching and retrieving parsed concept files."""

from __future__ import annotations

import difflib
from pathlib import Path

from lexibrary.artifacts.concept import ConceptFile
from lexibrary.wiki.parser import parse_concept_file


class ConceptIndex:
    """In-memory index of concept files for search and retrieval.

    Use :meth:`load` to build an index from a directory of concept markdown
    files, then :meth:`search`, :meth:`find`, :meth:`names`, and
    :meth:`by_tag` to query it.
    """

    def __init__(self, concepts: dict[str, ConceptFile]) -> None:
        self._concepts = concepts

    @classmethod
    def load(cls, concepts_dir: Path) -> ConceptIndex:
        """Load all concept files from *concepts_dir* and return an index.

        Scans for ``*.md`` files, parses each one, and indexes by the
        frontmatter title.  Files that fail to parse are silently skipped.
        """
        concepts: dict[str, ConceptFile] = {}
        if not concepts_dir.is_dir():
            return cls(concepts)
        for md_path in sorted(concepts_dir.glob("*.md")):
            concept = parse_concept_file(md_path)
            if concept is not None:
                concepts[concept.frontmatter.title] = concept
        return cls(concepts)

    def names(self) -> list[str]:
        """Return a sorted list of all concept titles in the index."""
        return sorted(self._concepts.keys())

    def find(self, name: str) -> ConceptFile | None:
        """Find a concept by exact title or alias (case-insensitive).

        Returns the first match or ``None``.
        """
        needle = _normalize(name)
        for concept in self._concepts.values():
            if _normalize(concept.frontmatter.title) == needle:
                return concept
            for alias in concept.frontmatter.aliases:
                if _normalize(alias) == needle:
                    return concept
        return None

    def find_by_id(self, artifact_id: str) -> ConceptFile | None:
        """Find a concept by its artifact ID (e.g. ``CN-001``).

        Performs a case-insensitive match against the ``id`` field in each
        concept's frontmatter.  Returns the first match or ``None``.
        """
        needle = artifact_id.strip().upper()
        for concept in self._concepts.values():
            if concept.frontmatter.id is not None and concept.frontmatter.id.upper() == needle:
                return concept
        return None

    def search(self, query: str) -> list[ConceptFile]:
        """Search concepts by normalized substring match with fuzzy fallback.

        First attempts exact substring matching against titles, aliases,
        tags, and summaries.  If no exact matches are found, falls back to
        fuzzy matching (via :func:`difflib.get_close_matches`) against
        concept titles and aliases that are at least 5 characters long.

        Returns a list of matching :class:`ConceptFile` instances (no
        duplicates, ordered by title).
        """
        needle = _normalize(query)
        if not needle:
            return []
        matches: dict[str, ConceptFile] = {}
        for concept in self._concepts.values():
            if _matches_concept(concept, needle):
                matches[concept.frontmatter.title] = concept
        if matches:
            return [matches[k] for k in sorted(matches.keys())]

        # Fuzzy fallback: only when exact substring matching returns nothing.
        candidates: list[str] = []
        candidate_to_concept: dict[str, ConceptFile] = {}
        for concept in self._concepts.values():
            title = concept.frontmatter.title
            if len(title) >= 5:
                lower_title = title.lower()
                candidates.append(lower_title)
                candidate_to_concept[lower_title] = concept
            for alias in concept.frontmatter.aliases:
                if len(alias) >= 5:
                    lower_alias = alias.lower()
                    candidates.append(lower_alias)
                    candidate_to_concept[lower_alias] = concept

        fuzzy_hits = difflib.get_close_matches(needle, candidates, n=5, cutoff=0.6)
        fuzzy_matches: dict[str, ConceptFile] = {}
        for hit in fuzzy_hits:
            concept = candidate_to_concept[hit]
            fuzzy_matches[concept.frontmatter.title] = concept
        return [fuzzy_matches[k] for k in sorted(fuzzy_matches.keys())]

    def by_tag(self, tag: str) -> list[ConceptFile]:
        """Return all concepts that have *tag* (case-insensitive).

        Results are ordered by title.
        """
        needle = _normalize(tag)
        results: dict[str, ConceptFile] = {}
        for concept in self._concepts.values():
            for t in concept.frontmatter.tags:
                if _normalize(t) == needle:
                    results[concept.frontmatter.title] = concept
                    break
        return [results[k] for k in sorted(results.keys())]

    def __len__(self) -> int:
        return len(self._concepts)

    def __contains__(self, name: str) -> bool:
        return self.find(name) is not None


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase and strip separators.

    Note: search._normalize_tag() in src/lexibrary/search.py uses a different
    strategy (replaces underscores with hyphens). The two serve different
    purposes — wiki index matching vs tag filtering. Check both if changing either.
    """
    return text.strip().lower().replace("-", "").replace("_", "").replace(" ", "")


def _matches_concept(concept: ConceptFile, needle: str) -> bool:
    """Check if *needle* is a substring of any searchable field."""
    if needle in _normalize(concept.frontmatter.title):
        return True
    for alias in concept.frontmatter.aliases:
        if needle in _normalize(alias):
            return True
    for tag in concept.frontmatter.tags:
        if needle in _normalize(tag):
            return True
    return needle in _normalize(concept.summary)
