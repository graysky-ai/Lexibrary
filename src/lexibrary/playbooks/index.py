"""Playbook index for in-memory query, search, and trigger-file matching."""

from __future__ import annotations

import logging
from pathlib import Path

import pathspec

from lexibrary.artifacts.playbook import PlaybookFile, playbook_slug
from lexibrary.playbooks.parser import parse_playbook_file

logger = logging.getLogger(__name__)


class PlaybookIndex:
    """In-memory index of playbook files with query, search, and trigger matching.

    Use :meth:`load` to build an index from a ``.lexibrary/playbooks/``
    directory, then query with :meth:`find`, :meth:`search`, :meth:`by_tag`,
    :meth:`by_status`, :meth:`by_trigger_file`, and :meth:`names`.

    Iteration is explicitly disallowed (consistent with ``ConventionIndex``).
    """

    def __init__(self, playbooks_dir: Path) -> None:
        self._playbooks_dir = playbooks_dir
        self.playbooks: list[PlaybookFile] = []

    def load(self) -> None:
        """Scan the playbooks directory and parse all ``.md`` files.

        Malformed files are silently skipped.  If the directory does not
        exist, :attr:`playbooks` is left as an empty list.
        """
        self.playbooks = []
        if not self._playbooks_dir.is_dir():
            return

        for md_path in sorted(self._playbooks_dir.glob("*.md")):
            playbook = parse_playbook_file(md_path)
            if playbook is not None:
                self.playbooks.append(playbook)

    # -- Query methods --------------------------------------------------------

    def find(self, slug: str) -> PlaybookFile | None:
        """Return the playbook matching *slug*, or ``None``.

        The slug is compared against ``playbook_slug(title)`` for each
        loaded playbook.
        """
        norm = slug.strip().lower()
        for pb in self.playbooks:
            if playbook_slug(pb.frontmatter.title) == norm:
                return pb
        return None

    def search(self, query: str) -> list[PlaybookFile]:
        """Search playbooks by case-insensitive substring against title, tags, and overview.

        Returns matching playbooks ordered by title.
        """
        needle = query.strip().lower()
        if not needle:
            return []

        matches: dict[str, PlaybookFile] = {}
        for pb in self.playbooks:
            if _matches_playbook(pb, needle):
                matches[pb.frontmatter.title] = pb

        return [matches[k] for k in sorted(matches.keys())]

    def by_tag(self, tag: str) -> list[PlaybookFile]:
        """Return all playbooks with *tag* (case-insensitive comparison).

        Results are ordered by title.
        """
        needle = tag.strip().lower()
        results: dict[str, PlaybookFile] = {}
        for pb in self.playbooks:
            for t in pb.frontmatter.tags:
                if t.strip().lower() == needle:
                    results[pb.frontmatter.title] = pb
                    break
        return [results[k] for k in sorted(results.keys())]

    def by_status(self, status: str) -> list[PlaybookFile]:
        """Return all playbooks with the given *status*.

        Results are ordered by title.
        """
        norm = status.strip().lower()
        results: dict[str, PlaybookFile] = {}
        for pb in self.playbooks:
            if pb.frontmatter.status == norm:
                results[pb.frontmatter.title] = pb
        return [results[k] for k in sorted(results.keys())]

    def by_trigger_file(self, file_path: str) -> list[PlaybookFile]:
        """Return playbooks whose ``trigger_files`` globs match *file_path*.

        Uses ``pathspec`` with ``"gitignore"`` pattern style.  Results are
        ordered by glob specificity: patterns with more path segments rank
        higher (more specific).  Within the same specificity, playbooks are
        ordered by title.
        """
        norm_path = file_path.strip("/")
        if not norm_path:
            return []

        scored: list[tuple[int, str, PlaybookFile]] = []
        for pb in self.playbooks:
            if not pb.frontmatter.trigger_files:
                continue
            best_specificity = _best_matching_specificity(pb.frontmatter.trigger_files, norm_path)
            if best_specificity >= 0:
                scored.append((best_specificity, pb.frontmatter.title, pb))

        # Sort by specificity descending (more specific first), then title ascending
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [entry[2] for entry in scored]

    def names(self) -> list[str]:
        """Return a sorted list of all playbook titles."""
        return sorted(pb.frontmatter.title for pb in self.playbooks)

    def __len__(self) -> int:
        return len(self.playbooks)

    def __iter__(self) -> None:
        raise TypeError(
            "PlaybookIndex is not iterable. Use .playbooks, .names(), or query methods instead."
        )


# -- Private helpers ----------------------------------------------------------


def _matches_playbook(pb: PlaybookFile, needle: str) -> bool:
    """Check if *needle* is a case-insensitive substring of any searchable field."""
    if needle in pb.frontmatter.title.lower():
        return True
    for alias in pb.frontmatter.aliases:
        if needle in alias.lower():
            return True
    for tag in pb.frontmatter.tags:
        if needle in tag.lower():
            return True
    return needle in pb.overview.lower()


def _glob_specificity(pattern: str) -> int:
    """Return a specificity score for a glob pattern.

    Specificity is the number of literal path segments (parts separated by
    ``/``).  ``**`` segments are not counted.  Higher scores indicate more
    specific patterns.
    """
    parts = pattern.strip("/").split("/")
    return sum(1 for p in parts if p != "**")


def _best_matching_specificity(patterns: list[str], file_path: str) -> int:
    """Return the highest specificity among *patterns* that match *file_path*.

    Returns ``-1`` if no pattern matches.
    """
    best = -1
    for pattern in patterns:
        spec = pathspec.PathSpec.from_lines("gitignore", [pattern])
        if spec.match_file(file_path):
            score = _glob_specificity(pattern)
            if score > best:
                best = score
    return best
