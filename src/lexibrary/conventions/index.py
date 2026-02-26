"""Convention index for scope-aware retrieval, search, and filtering."""

from __future__ import annotations

import logging
from pathlib import Path

from lexibrary.artifacts.convention import ConventionFile
from lexibrary.conventions.parser import parse_convention_file

logger = logging.getLogger(__name__)


class ConventionIndex:
    """In-memory index of convention files with scope-aware retrieval.

    Use :meth:`load` to build an index from a ``.lexibrary/conventions/``
    directory, then query with :meth:`find_by_scope`, :meth:`search`,
    :meth:`by_tag`, :meth:`by_status`, and :meth:`names`.
    """

    def __init__(self, conventions_dir: Path) -> None:
        self._conventions_dir = conventions_dir
        self.conventions: list[ConventionFile] = []

    def load(self) -> None:
        """Scan the conventions directory and parse all ``.md`` files.

        Malformed files are silently skipped. If the directory does not
        exist, :attr:`conventions` is left as an empty list.
        """
        self.conventions = []
        if not self._conventions_dir.is_dir():
            return

        for md_path in sorted(self._conventions_dir.glob("*.md")):
            convention = parse_convention_file(md_path)
            if convention is not None:
                self.conventions.append(convention)

    # -- Scope-aware retrieval ------------------------------------------------

    def find_by_scope(
        self, file_path: str, scope_root: str = "."
    ) -> list[ConventionFile]:
        """Return conventions applicable to *file_path*, ordered by specificity.

        The algorithm:

        1. Build an ancestry chain from the file's parent directory up to
           *scope_root* (inclusive).
        2. Collect conventions where ``scope == "project"`` or where the
           normalised file path starts with the convention's scope directory
           (with trailing ``/``).
        3. Order scopes root-to-leaf: ``"project"`` first, then ``"."``, then
           deeper directories.
        4. Within the same scope, order by priority descending, then title
           alphabetically.
        """
        # Normalise paths: strip trailing slashes, use forward slashes
        norm_file = file_path.strip("/")
        norm_root = scope_root.strip("/")

        # Build ancestry set from file's parent up to scope_root
        ancestry = _build_ancestry(norm_file, norm_root)

        matching: list[ConventionFile] = []
        for conv in self.conventions:
            scope = conv.frontmatter.scope
            if scope == "project" or _normalise_scope(scope) in ancestry:
                matching.append(conv)

        # Sort: root-to-leaf by scope depth, then priority desc, then title asc
        matching.sort(key=lambda c: _scope_sort_key(c))
        return matching

    def find_by_scope_limited(
        self,
        file_path: str,
        scope_root: str = ".",
        limit: int = 5,
    ) -> tuple[list[ConventionFile], int]:
        """Return at most *limit* conventions for *file_path* plus total count.

        When truncating, the most-specific (leaf-ward) conventions are kept
        and the most-general (root-ward) ones are dropped.

        Returns ``(conventions, total_count)``.
        """
        all_conventions = self.find_by_scope(file_path, scope_root)
        total = len(all_conventions)

        if limit <= 0:
            return [], total
        if total <= limit:
            return all_conventions, total

        # Keep the tail (most-specific / leaf-ward)
        return all_conventions[-limit:], total

    # -- Search and filter ----------------------------------------------------

    def search(self, query: str) -> list[ConventionFile]:
        """Search conventions by case-insensitive substring against title, body, and tags.

        Returns matching conventions ordered by title.
        """
        needle = query.strip().lower()
        if not needle:
            return []

        matches: dict[str, ConventionFile] = {}
        for conv in self.conventions:
            if _matches_convention(conv, needle):
                matches[conv.frontmatter.title] = conv

        return [matches[k] for k in sorted(matches.keys())]

    def by_tag(self, tag: str) -> list[ConventionFile]:
        """Return all conventions with *tag* (case-insensitive comparison).

        Results are ordered by title.
        """
        needle = tag.strip().lower()
        results: dict[str, ConventionFile] = {}
        for conv in self.conventions:
            for t in conv.frontmatter.tags:
                if t.strip().lower() == needle:
                    results[conv.frontmatter.title] = conv
                    break
        return [results[k] for k in sorted(results.keys())]

    def by_status(self, status: str) -> list[ConventionFile]:
        """Return all conventions with the given *status*.

        Results are ordered by title.
        """
        norm = status.strip().lower()
        results: dict[str, ConventionFile] = {}
        for conv in self.conventions:
            if conv.frontmatter.status == norm:
                results[conv.frontmatter.title] = conv
        return [results[k] for k in sorted(results.keys())]

    def names(self) -> list[str]:
        """Return a sorted list of all convention titles."""
        return sorted(c.frontmatter.title for c in self.conventions)

    def __len__(self) -> int:
        return len(self.conventions)


# -- Private helpers ----------------------------------------------------------


def _normalise_scope(scope: str) -> str:
    """Normalise a scope path for comparison: strip slashes."""
    return scope.strip("/")


def _build_ancestry(file_path: str, scope_root: str) -> set[str]:
    """Build the set of ancestor directory paths from *file_path* up to *scope_root*.

    Includes *scope_root* itself. Uses POSIX-style forward-slash paths.
    The file's own parent directory is included; the file itself is not.
    """
    ancestors: set[str] = set()

    # The file's parent directory
    parts = file_path.split("/")
    # Walk from the file's parent directory up to (and including) scope_root
    for i in range(len(parts) - 1, 0, -1):
        ancestor = "/".join(parts[:i])
        ancestors.add(ancestor)
        if ancestor == scope_root:
            break

    # Always include scope_root itself (handles the "." case)
    ancestors.add(scope_root)

    # Filter out ancestors above scope_root
    if scope_root == ".":
        # Everything is within project root
        return ancestors

    # Only keep ancestors that are scope_root or within it
    return {a for a in ancestors if a == scope_root or a.startswith(scope_root + "/")}


def _scope_sort_key(conv: ConventionFile) -> tuple[int, int, int, str]:
    """Return a sort key for root-to-leaf ordering.

    Tuple: (scope_type_order, scope_depth, -priority, title)
    - scope_type_order: 0 for "project", 1 for directory scopes
    - scope_depth: number of path segments (root "." = 0)
    - -priority: negated so higher priority sorts first
    - title: alphabetical tiebreak
    """
    scope = conv.frontmatter.scope
    if scope == "project":
        return (0, 0, -conv.frontmatter.priority, conv.frontmatter.title)

    norm = _normalise_scope(scope)
    depth = 0 if norm == "." else norm.count("/") + 1
    return (1, depth, -conv.frontmatter.priority, conv.frontmatter.title)


def _matches_convention(conv: ConventionFile, needle: str) -> bool:
    """Check if *needle* is a case-insensitive substring of any searchable field."""
    if needle in conv.frontmatter.title.lower():
        return True
    for tag in conv.frontmatter.tags:
        if needle in tag.lower():
            return True
    return needle in conv.body.lower()
