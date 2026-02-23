"""In-memory index for searching and filtering Stack posts."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from lexibrary.stack.models import StackPost
from lexibrary.stack.parser import parse_stack_post


class StackIndex:
    """In-memory searchable index of Stack posts.

    Use :meth:`build` to scan the ``.lexibrary/stack/`` directory and
    construct an index, then query it with :meth:`search`, :meth:`by_tag`,
    :meth:`by_scope`, :meth:`by_status`, or :meth:`by_concept`.
    """

    def __init__(self, posts: list[StackPost]) -> None:
        self._posts = posts

    @classmethod
    def build(cls, project_root: Path) -> StackIndex:
        """Scan ``.lexibrary/stack/`` for ``ST-*-*.md`` files and build an index.

        Malformed files are silently skipped.
        """
        stack_dir = project_root / ".lexibrary" / "stack"
        posts: list[StackPost] = []
        if not stack_dir.is_dir():
            return cls(posts)
        for md_path in sorted(stack_dir.glob("ST-*-*.md")):
            post = parse_stack_post(md_path)
            if post is not None:
                posts.append(post)
        return cls(posts)

    # ------------------------------------------------------------------
    # Full-text search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[StackPost]:
        """Case-insensitive substring search across titles, problems, answers, and tags.

        Results are sorted by vote count descending.
        """
        needle = query.strip().lower()
        if not needle:
            return []
        matches: list[StackPost] = []
        for post in self._posts:
            if _matches_post(post, needle):
                matches.append(post)
        matches.sort(key=lambda p: p.frontmatter.votes, reverse=True)
        return matches

    # ------------------------------------------------------------------
    # Filter methods
    # ------------------------------------------------------------------

    def by_tag(self, tag: str) -> list[StackPost]:
        """Filter posts by tag (case-insensitive)."""
        needle = tag.strip().lower()
        return [p for p in self._posts if any(t.lower() == needle for t in p.frontmatter.tags)]

    def by_scope(self, path: str) -> list[StackPost]:
        """Filter posts by referenced file path using prefix matching.

        A post matches if any of its ``refs.files`` starts with *path*.
        """
        return [p for p in self._posts if any(f.startswith(path) for f in p.frontmatter.refs.files)]

    def by_status(self, status: str) -> list[StackPost]:
        """Filter posts by status value."""
        return [p for p in self._posts if p.frontmatter.status == status]

    def by_concept(self, concept: str) -> list[StackPost]:
        """Filter posts referencing a concept name (case-insensitive)."""
        needle = concept.strip().lower()
        return [
            p for p in self._posts if any(c.lower() == needle for c in p.frontmatter.refs.concepts)
        ]

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._posts)

    def __iter__(self) -> Iterator[StackPost]:
        return iter(self._posts)


def _matches_post(post: StackPost, needle: str) -> bool:
    """Check if *needle* is a substring of any searchable field in the post."""
    fm = post.frontmatter
    if needle in fm.title.lower():
        return True
    if needle in post.problem.lower():
        return True
    for tag in fm.tags:
        if needle in tag.lower():
            return True
    return any(needle in answer.body.lower() for answer in post.answers)
