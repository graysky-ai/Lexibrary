"""Tests for design comment file operations.

Tests design_comment_path(), append_design_comment(), read_design_comments(),
and design_comment_count() from ``lexibrary.lifecycle.design_comments``.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from lexibrary.lifecycle.design_comments import (
    append_design_comment,
    design_comment_count,
    design_comment_path,
    read_design_comments,
)
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_design_file(
    project_root: Path,
    source_rel: str,
    source_content: str = "def hello(): pass\n",
) -> Path:
    """Create a minimal design file in the mirror tree."""
    content_hash = hashlib.sha256(source_content.encode()).hexdigest()
    design_path = project_root / LEXIBRARY_DIR / DESIGNS_DIR / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC).isoformat()
    design_content = f"""---
description: Design file for {source_rel}
updated_by: archivist
---

# {source_rel}

Test design file content.

## Interface Contract

```python
def hello(): ...
```

## Dependencies

- (none)

## Dependents

*(see `lexi lookup` for live reverse references)*

(none)

<!-- lexibrary:meta
source: {source_rel}
source_hash: {content_hash}
design_hash: placeholder
generated: {now}
generator: lexibrary-v2
-->
"""
    design_path.write_text(design_content, encoding="utf-8")
    return design_path


def _setup_project_with_source(
    tmp_path: Path,
    source_rel: str = "src/foo.py",
    source_content: str = "def hello(): pass\n",
) -> tuple[Path, Path]:
    """Create project root with source file and design file.

    Returns (project_root, design_path).
    """
    project_root = tmp_path
    lexibrary_dir = project_root / LEXIBRARY_DIR
    lexibrary_dir.mkdir()

    # Create source file
    source_path = project_root / source_rel
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source_content, encoding="utf-8")

    # Create design file
    design_path = _create_design_file(project_root, source_rel, source_content)
    return project_root, design_path


# ---------------------------------------------------------------------------
# design_comment_path()
# ---------------------------------------------------------------------------


class TestDesignCommentPath:
    """Tests for design_comment_path()."""

    def test_replaces_md_suffix(self) -> None:
        """Replaces .md suffix with .comments.yaml."""
        dp = Path("/project/.lexibrary/designs/src/foo.py.md")
        result = design_comment_path(dp)
        assert result == Path("/project/.lexibrary/designs/src/foo.py.comments.yaml")

    def test_relative_path(self) -> None:
        """Works with relative paths."""
        dp = Path(".lexibrary/designs/src/module.py.md")
        result = design_comment_path(dp)
        assert result == Path(".lexibrary/designs/src/module.py.comments.yaml")

    def test_deeply_nested_path(self) -> None:
        """Works with deeply nested paths."""
        dp = Path("/project/.lexibrary/designs/src/deep/nested/module.py.md")
        result = design_comment_path(dp)
        assert result == Path("/project/.lexibrary/designs/src/deep/nested/module.py.comments.yaml")


# ---------------------------------------------------------------------------
# append_design_comment()
# ---------------------------------------------------------------------------


class TestAppendDesignComment:
    """Tests for append_design_comment()."""

    def test_appends_comment_to_new_file(self, tmp_path: Path) -> None:
        """Creates comment file and appends comment."""
        project_root, design_path = _setup_project_with_source(tmp_path)

        append_design_comment(project_root, tmp_path / "src" / "foo.py", "test comment")

        comments = read_design_comments(project_root, tmp_path / "src" / "foo.py")
        assert len(comments) == 1
        assert comments[0].body == "test comment"

    def test_comment_has_utc_date(self, tmp_path: Path) -> None:
        """Appended comment has a UTC date."""
        project_root, _ = _setup_project_with_source(tmp_path)

        append_design_comment(project_root, tmp_path / "src" / "foo.py", "date test")

        comments = read_design_comments(project_root, tmp_path / "src" / "foo.py")
        assert len(comments) == 1
        assert comments[0].date is not None

    def test_multiple_comments_accumulate(self, tmp_path: Path) -> None:
        """Multiple appends accumulate comments in order."""
        project_root, _ = _setup_project_with_source(tmp_path)
        source = tmp_path / "src" / "foo.py"

        append_design_comment(project_root, source, "first")
        append_design_comment(project_root, source, "second")
        append_design_comment(project_root, source, "third")

        comments = read_design_comments(project_root, source)
        assert len(comments) == 3
        assert comments[0].body == "first"
        assert comments[1].body == "second"
        assert comments[2].body == "third"

    def test_comment_file_is_sibling_of_design(self, tmp_path: Path) -> None:
        """Comment file is created next to the design file."""
        project_root, design_path = _setup_project_with_source(tmp_path)

        append_design_comment(project_root, tmp_path / "src" / "foo.py", "sibling test")

        expected_comment_path = design_comment_path(design_path)
        assert expected_comment_path.exists()


# ---------------------------------------------------------------------------
# read_design_comments()
# ---------------------------------------------------------------------------


class TestReadDesignComments:
    """Tests for read_design_comments()."""

    def test_returns_empty_when_no_comments(self, tmp_path: Path) -> None:
        """Returns empty list when no comment file exists."""
        project_root, _ = _setup_project_with_source(tmp_path)

        comments = read_design_comments(project_root, tmp_path / "src" / "foo.py")
        assert comments == []

    def test_reads_existing_comments(self, tmp_path: Path) -> None:
        """Reads comments from an existing comment file."""
        project_root, _ = _setup_project_with_source(tmp_path)
        source = tmp_path / "src" / "foo.py"

        append_design_comment(project_root, source, "existing comment")
        comments = read_design_comments(project_root, source)

        assert len(comments) == 1
        assert comments[0].body == "existing comment"


# ---------------------------------------------------------------------------
# design_comment_count()
# ---------------------------------------------------------------------------


class TestDesignCommentCount:
    """Tests for design_comment_count()."""

    def test_returns_zero_when_no_comments(self, tmp_path: Path) -> None:
        """Returns 0 when no comment file exists."""
        project_root, _ = _setup_project_with_source(tmp_path)

        count = design_comment_count(project_root, tmp_path / "src" / "foo.py")
        assert count == 0

    def test_counts_existing_comments(self, tmp_path: Path) -> None:
        """Returns correct count of existing comments."""
        project_root, _ = _setup_project_with_source(tmp_path)
        source = tmp_path / "src" / "foo.py"

        for i in range(4):
            append_design_comment(project_root, source, f"comment {i}")

        count = design_comment_count(project_root, source)
        assert count == 4

    def test_count_matches_read_length(self, tmp_path: Path) -> None:
        """Count matches the length of the read comments list."""
        project_root, _ = _setup_project_with_source(tmp_path)
        source = tmp_path / "src" / "foo.py"

        for i in range(3):
            append_design_comment(project_root, source, f"comment {i}")

        count = design_comment_count(project_root, source)
        comments = read_design_comments(project_root, source)
        assert count == len(comments)
