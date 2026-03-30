"""Tests for title collision detection."""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.title_check import (
    TitleCheckResult,
    TitleMatch,
    _extract_title,
    find_title_matches,
)

# ---------------------------------------------------------------------------
# Helper: create a minimal artifact file with frontmatter
# ---------------------------------------------------------------------------


def _write_artifact(path: Path, title: str, extra_fields: str = "") -> None:
    """Write a minimal markdown file with YAML frontmatter containing a title."""
    content = f"---\ntitle: {title}\n{extra_fields}---\n\nBody text.\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# _extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    """Unit tests for the lightweight frontmatter title extractor."""

    def test_simple_title(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        _write_artifact(f, "Error Handling")
        assert _extract_title(f) == "Error Handling"

    def test_quoted_title(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text('---\ntitle: "Quoted Title"\n---\n', encoding="utf-8")
        assert _extract_title(f) == "Quoted Title"

    def test_single_quoted_title(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("---\ntitle: 'Single Quoted'\nid: CN-001\n---\n", encoding="utf-8")
        assert _extract_title(f) == "Single Quoted"

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("No frontmatter here.\n", encoding="utf-8")
        assert _extract_title(f) is None

    def test_no_title_field(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("---\nstatus: active\n---\n", encoding="utf-8")
        assert _extract_title(f) is None

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.md"
        assert _extract_title(f) is None

    def test_no_closing_delimiter(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("---\ntitle: Unclosed\n", encoding="utf-8")
        assert _extract_title(f) is None

    def test_title_with_extra_fields(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("---\nid: CN-001\ntitle: My Concept\ntags: []\n---\n", encoding="utf-8")
        assert _extract_title(f) == "My Concept"


# ---------------------------------------------------------------------------
# TitleCheckResult properties
# ---------------------------------------------------------------------------


class TestTitleCheckResult:
    """Tests for TitleCheckResult dataclass properties."""

    def test_empty_result(self) -> None:
        result = TitleCheckResult()
        assert result.has_same_type is False
        assert result.has_cross_type is False

    def test_same_type_present(self, tmp_path: Path) -> None:
        result = TitleCheckResult(
            same_type=[TitleMatch(kind="concept", title="Foo", file_path=tmp_path / "foo.md")]
        )
        assert result.has_same_type is True
        assert result.has_cross_type is False

    def test_cross_type_present(self, tmp_path: Path) -> None:
        result = TitleCheckResult(
            cross_type=[TitleMatch(kind="convention", title="Foo", file_path=tmp_path / "foo.md")]
        )
        assert result.has_same_type is False
        assert result.has_cross_type is True


# ---------------------------------------------------------------------------
# find_title_matches — same-type blocking
# ---------------------------------------------------------------------------


class TestFindTitleMatchesSameType:
    """Scenario: Same-type title duplicates should block creation."""

    def test_duplicate_concept_title_blocks(self, tmp_path: Path) -> None:
        """WHEN a concept 'Error Handling' exists, creating another concept
        with the same title THEN returns a same-type match."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        _write_artifact(concepts_dir / "CN-001-error-handling.md", "Error Handling")

        result = find_title_matches("Error Handling", "concept", tmp_path)
        assert result.has_same_type is True
        assert len(result.same_type) == 1
        assert result.same_type[0].kind == "concept"
        assert result.same_type[0].title == "Error Handling"

    def test_case_insensitive_match(self, tmp_path: Path) -> None:
        """Title comparison is case-insensitive."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        _write_artifact(concepts_dir / "CN-001-error-handling.md", "error handling")

        result = find_title_matches("Error Handling", "concept", tmp_path)
        assert result.has_same_type is True

    def test_unique_concept_title_passes(self, tmp_path: Path) -> None:
        """WHEN no concept shares the title, THEN no same-type match."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        _write_artifact(concepts_dir / "CN-001-other-topic.md", "Other Topic")

        result = find_title_matches("New Topic", "concept", tmp_path)
        assert result.has_same_type is False

    def test_duplicate_convention_title_blocks(self, tmp_path: Path) -> None:
        """Same-type blocking works for conventions too."""
        conventions_dir = tmp_path / ".lexibrary" / "conventions"
        _write_artifact(conventions_dir / "CV-001-use-utc.md", "Use UTC Everywhere")

        result = find_title_matches("Use UTC Everywhere", "convention", tmp_path)
        assert result.has_same_type is True
        assert result.same_type[0].kind == "convention"

    def test_duplicate_playbook_title_blocks(self, tmp_path: Path) -> None:
        """Same-type blocking works for playbooks too."""
        playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
        _write_artifact(playbooks_dir / "PB-001-version-bump.md", "Version Bump")

        result = find_title_matches("Version Bump", "playbook", tmp_path)
        assert result.has_same_type is True
        assert result.same_type[0].kind == "playbook"

    def test_duplicate_stack_title_blocks(self, tmp_path: Path) -> None:
        """Same-type blocking works for stack posts too."""
        stack_dir = tmp_path / ".lexibrary" / "stack"
        _write_artifact(
            stack_dir / "ST-001-mypy-error.md",
            "Mypy Type Error",
            "id: ST-001\ntags: [mypy]\nstatus: open\ncreated: 2024-01-01\nauthor: agent\n",
        )

        result = find_title_matches("Mypy Type Error", "stack", tmp_path)
        assert result.has_same_type is True
        assert result.same_type[0].kind == "stack"


# ---------------------------------------------------------------------------
# find_title_matches — cross-type warnings
# ---------------------------------------------------------------------------


class TestFindTitleMatchesCrossType:
    """Scenario: Cross-type title matches should warn but not block."""

    def test_cross_type_concept_vs_convention(self, tmp_path: Path) -> None:
        """WHEN a concept 'Error Handling' exists and user creates a convention
        with the same title, THEN cross-type match is returned."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        _write_artifact(concepts_dir / "CN-001-error-handling.md", "Error Handling")

        result = find_title_matches("Error Handling", "convention", tmp_path)
        assert result.has_same_type is False
        assert result.has_cross_type is True
        assert len(result.cross_type) == 1
        assert result.cross_type[0].kind == "concept"

    def test_multiple_cross_type_matches(self, tmp_path: Path) -> None:
        """WHEN both a concept and a stack post share a title with a new
        convention, THEN both are returned as cross-type matches."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        stack_dir = tmp_path / ".lexibrary" / "stack"
        _write_artifact(concepts_dir / "CN-001-error-handling.md", "Error Handling")
        _write_artifact(
            stack_dir / "ST-001-error-handling.md",
            "Error Handling",
            "id: ST-001\ntags: [errors]\nstatus: open\ncreated: 2024-01-01\nauthor: agent\n",
        )

        result = find_title_matches("Error Handling", "convention", tmp_path)
        assert result.has_same_type is False
        assert len(result.cross_type) == 2
        kinds = {m.kind for m in result.cross_type}
        assert kinds == {"concept", "stack"}

    def test_no_cross_type_matches(self, tmp_path: Path) -> None:
        """WHEN no other artifact shares the title, THEN no warnings."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        _write_artifact(concepts_dir / "CN-001-other.md", "Other Topic")

        result = find_title_matches("Unique Title", "convention", tmp_path)
        assert result.has_same_type is False
        assert result.has_cross_type is False


# ---------------------------------------------------------------------------
# find_title_matches — edge cases
# ---------------------------------------------------------------------------


class TestFindTitleMatchesEdgeCases:
    """Edge cases for title collision scanning."""

    def test_empty_library(self, tmp_path: Path) -> None:
        """No .lexibrary directory at all should return empty results."""
        result = find_title_matches("Anything", "concept", tmp_path)
        assert result.has_same_type is False
        assert result.has_cross_type is False

    def test_empty_directories(self, tmp_path: Path) -> None:
        """Empty artifact directories should return empty results."""
        (tmp_path / ".lexibrary" / "concepts").mkdir(parents=True)
        (tmp_path / ".lexibrary" / "conventions").mkdir(parents=True)

        result = find_title_matches("Anything", "concept", tmp_path)
        assert result.has_same_type is False
        assert result.has_cross_type is False

    def test_whitespace_normalization(self, tmp_path: Path) -> None:
        """Leading/trailing whitespace in titles should not prevent matching."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        _write_artifact(concepts_dir / "CN-001-foo.md", "  Error Handling  ")

        result = find_title_matches("Error Handling", "concept", tmp_path)
        assert result.has_same_type is True

    def test_files_without_frontmatter_are_skipped(self, tmp_path: Path) -> None:
        """Non-frontmatter markdown files should not cause errors."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        concepts_dir.mkdir(parents=True)
        (concepts_dir / "README.md").write_text("# Just a readme\n", encoding="utf-8")

        result = find_title_matches("Anything", "concept", tmp_path)
        assert result.has_same_type is False
        assert result.has_cross_type is False

    def test_same_and_cross_type_simultaneously(self, tmp_path: Path) -> None:
        """Both same-type and cross-type matches can coexist."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        conventions_dir = tmp_path / ".lexibrary" / "conventions"
        _write_artifact(concepts_dir / "CN-001-shared-topic.md", "Shared Topic")
        _write_artifact(conventions_dir / "CV-001-shared-topic.md", "Shared Topic")

        result = find_title_matches("Shared Topic", "concept", tmp_path)
        assert result.has_same_type is True
        assert result.has_cross_type is True
        assert result.same_type[0].kind == "concept"
        assert result.cross_type[0].kind == "convention"
