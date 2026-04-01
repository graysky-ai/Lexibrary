"""Tests for the unified artifact ID system."""

from __future__ import annotations

from pathlib import Path

from lexibrary.artifacts.ids import (
    ARTIFACT_PREFIXES,
    dir_for_kind,
    find_artifact_path,
    is_artifact_id,
    kind_for_prefix,
    next_artifact_id,
    next_design_id,
    parse_artifact_id,
    prefix_for_kind,
)

# ---------------------------------------------------------------------------
# prefix_for_kind
# ---------------------------------------------------------------------------


class TestPrefixForKind:
    """Scenario: prefix_for_kind returns the 2-letter prefix for known kinds."""

    def test_concept(self) -> None:
        assert prefix_for_kind("concept") == "CN"

    def test_convention(self) -> None:
        assert prefix_for_kind("convention") == "CV"

    def test_playbook(self) -> None:
        assert prefix_for_kind("playbook") == "PB"

    def test_design(self) -> None:
        assert prefix_for_kind("design") == "DS"

    def test_stack(self) -> None:
        assert prefix_for_kind("stack") == "ST"

    def test_unknown_raises_key_error(self) -> None:
        import pytest

        with pytest.raises(KeyError):
            prefix_for_kind("unknown")

    def test_registry_contains_all_types(self) -> None:
        expected_kinds = {"concept", "convention", "playbook", "design", "stack"}
        assert set(ARTIFACT_PREFIXES.keys()) == expected_kinds


# ---------------------------------------------------------------------------
# kind_for_prefix
# ---------------------------------------------------------------------------


class TestKindForPrefix:
    """Scenario: kind_for_prefix returns the kind name for known prefixes."""

    def test_concept(self) -> None:
        assert kind_for_prefix("CN") == "concept"

    def test_convention(self) -> None:
        assert kind_for_prefix("CV") == "convention"

    def test_playbook(self) -> None:
        assert kind_for_prefix("PB") == "playbook"

    def test_design(self) -> None:
        assert kind_for_prefix("DS") == "design"

    def test_stack(self) -> None:
        assert kind_for_prefix("ST") == "stack"

    def test_unknown_returns_none(self) -> None:
        assert kind_for_prefix("ZZ") is None

    def test_lowercase_returns_none(self) -> None:
        assert kind_for_prefix("cn") is None

    def test_empty_returns_none(self) -> None:
        assert kind_for_prefix("") is None

    def test_round_trip_with_prefix_for_kind(self) -> None:
        """kind_for_prefix is the inverse of prefix_for_kind."""
        for kind_name, prefix in ARTIFACT_PREFIXES.items():
            assert kind_for_prefix(prefix) == kind_name


# ---------------------------------------------------------------------------
# dir_for_kind
# ---------------------------------------------------------------------------


class TestDirForKind:
    """Scenario: dir_for_kind returns the .lexibrary/ subdirectory for a kind."""

    def test_concept(self) -> None:
        assert dir_for_kind("concept") == "concepts"

    def test_convention(self) -> None:
        assert dir_for_kind("convention") == "conventions"

    def test_playbook(self) -> None:
        assert dir_for_kind("playbook") == "playbooks"

    def test_design(self) -> None:
        assert dir_for_kind("design") == "designs"

    def test_stack(self) -> None:
        assert dir_for_kind("stack") == "stack"

    def test_unknown_raises_key_error(self) -> None:
        import pytest

        with pytest.raises(KeyError):
            dir_for_kind("unknown")


# ---------------------------------------------------------------------------
# is_artifact_id
# ---------------------------------------------------------------------------


class TestIsArtifactId:
    """Scenario: is_artifact_id validates XX-NNN format."""

    def test_valid_three_digit_id(self) -> None:
        assert is_artifact_id("CN-001") is True

    def test_valid_four_digit_id(self) -> None:
        assert is_artifact_id("ST-1234") is True

    def test_valid_all_prefixes(self) -> None:
        for prefix in ("CN", "CV", "PB", "DS", "ST"):
            assert is_artifact_id(f"{prefix}-001") is True

    def test_two_digits_invalid(self) -> None:
        assert is_artifact_id("CN-01") is False

    def test_one_digit_invalid(self) -> None:
        assert is_artifact_id("CN-1") is False

    def test_non_id_text(self) -> None:
        assert is_artifact_id("some-slug") is False

    def test_empty_string(self) -> None:
        assert is_artifact_id("") is False

    def test_lowercase_prefix_invalid(self) -> None:
        assert is_artifact_id("cn-001") is False

    def test_three_letter_prefix_invalid(self) -> None:
        assert is_artifact_id("ABC-001") is False

    def test_single_letter_prefix_invalid(self) -> None:
        assert is_artifact_id("C-001") is False

    def test_no_dash_invalid(self) -> None:
        assert is_artifact_id("CN001") is False

    def test_trailing_text_invalid(self) -> None:
        assert is_artifact_id("CN-001-slug") is False

    def test_leading_text_invalid(self) -> None:
        assert is_artifact_id("prefix-CN-001") is False


# ---------------------------------------------------------------------------
# parse_artifact_id
# ---------------------------------------------------------------------------


class TestParseArtifactId:
    """Scenario: parse_artifact_id splits IDs into (prefix, number)."""

    def test_parse_valid_id(self) -> None:
        result = parse_artifact_id("CV-042")
        assert result == ("CV", 42)

    def test_parse_three_digit(self) -> None:
        result = parse_artifact_id("CN-001")
        assert result == ("CN", 1)

    def test_parse_large_number(self) -> None:
        result = parse_artifact_id("ST-9999")
        assert result == ("ST", 9999)

    def test_parse_leading_zeros(self) -> None:
        result = parse_artifact_id("PB-007")
        assert result == ("PB", 7)

    def test_parse_invalid_returns_none(self) -> None:
        assert parse_artifact_id("not-an-id") is None

    def test_parse_empty_returns_none(self) -> None:
        assert parse_artifact_id("") is None

    def test_parse_two_digits_returns_none(self) -> None:
        assert parse_artifact_id("CN-01") is None

    def test_parse_with_slug_suffix_returns_none(self) -> None:
        assert parse_artifact_id("CN-001-slug") is None


# ---------------------------------------------------------------------------
# next_artifact_id
# ---------------------------------------------------------------------------


class TestNextArtifactId:
    """Scenario: next_artifact_id generates sequential IDs from filenames."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = next_artifact_id("CN", tmp_path, "CN-*-*.md")
        assert result == "CN-001"

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does-not-exist"
        result = next_artifact_id("PB", nonexistent, "PB-*-*.md")
        assert result == "PB-001"

    def test_existing_files_sequential(self, tmp_path: Path) -> None:
        (tmp_path / "CN-001-foo.md").touch()
        (tmp_path / "CN-002-bar.md").touch()
        result = next_artifact_id("CN", tmp_path, "CN-*-*.md")
        assert result == "CN-003"

    def test_existing_files_with_gaps(self, tmp_path: Path) -> None:
        (tmp_path / "CN-001-foo.md").touch()
        (tmp_path / "CN-003-bar.md").touch()
        result = next_artifact_id("CN", tmp_path, "CN-*-*.md")
        assert result == "CN-004"

    def test_ignores_non_matching_files(self, tmp_path: Path) -> None:
        (tmp_path / "CN-002-valid.md").touch()
        (tmp_path / "README.md").touch()
        (tmp_path / "PB-005-other.md").touch()
        result = next_artifact_id("CN", tmp_path, "CN-*-*.md")
        assert result == "CN-003"

    def test_large_numbers(self, tmp_path: Path) -> None:
        (tmp_path / "ST-099-large.md").touch()
        result = next_artifact_id("ST", tmp_path, "ST-*-*.md")
        assert result == "ST-100"

    def test_zero_padding_three_digits(self, tmp_path: Path) -> None:
        result = next_artifact_id("CV", tmp_path, "CV-*-*.md")
        assert result == "CV-001"

    def test_beyond_three_digits(self, tmp_path: Path) -> None:
        (tmp_path / "CV-999-last.md").touch()
        result = next_artifact_id("CV", tmp_path, "CV-*-*.md")
        assert result == "CV-1000"

    def test_stack_post_compatibility(self, tmp_path: Path) -> None:
        """next_artifact_id should work as a drop-in for next_stack_id."""
        (tmp_path / "ST-001-some-title.md").touch()
        (tmp_path / "ST-003-another-title.md").touch()
        result = next_artifact_id("ST", tmp_path, "ST-*-*.md")
        assert result == "ST-004"


# ---------------------------------------------------------------------------
# next_design_id
# ---------------------------------------------------------------------------


class TestNextDesignId:
    """Scenario: next_design_id scans frontmatter id: fields in .md files."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = next_design_id(tmp_path)
        assert result == "DS-001"

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does-not-exist"
        result = next_design_id(nonexistent)
        assert result == "DS-001"

    def test_no_frontmatter_ids(self, tmp_path: Path) -> None:
        (tmp_path / "file.md").write_text("---\ntitle: Hello\nid: CN-001\n---\nBody\n")
        result = next_design_id(tmp_path)
        assert result == "DS-001"

    def test_single_design_id(self, tmp_path: Path) -> None:
        (tmp_path / "file.md").write_text("---\nid: DS-005\ntitle: Hello\n---\nBody\n")
        result = next_design_id(tmp_path)
        assert result == "DS-006"

    def test_multiple_design_ids(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("---\nid: DS-005\n---\n")
        (tmp_path / "b.md").write_text("---\nid: DS-012\n---\n")
        result = next_design_id(tmp_path)
        assert result == "DS-013"

    def test_recursive_scanning(self, tmp_path: Path) -> None:
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        (subdir / "nested.md").write_text("---\nid: DS-020\n---\n")
        (tmp_path / "top.md").write_text("---\nid: DS-003\n---\n")
        result = next_design_id(tmp_path)
        assert result == "DS-021"

    def test_ignores_non_design_ids(self, tmp_path: Path) -> None:
        (tmp_path / "file.md").write_text("---\nid: CN-005\n---\n")
        result = next_design_id(tmp_path)
        assert result == "DS-001"

    def test_ignores_files_without_frontmatter(self, tmp_path: Path) -> None:
        (tmp_path / "plain.md").write_text("No frontmatter here\nid: DS-999\n")
        result = next_design_id(tmp_path)
        assert result == "DS-001"

    def test_ignores_id_outside_frontmatter(self, tmp_path: Path) -> None:
        content = "---\ntitle: Hello\nid: CN-002\n---\nBody with id: DS-050 in it\n"
        (tmp_path / "file.md").write_text(content)
        result = next_design_id(tmp_path)
        assert result == "DS-001"

    def test_handles_mixed_files(self, tmp_path: Path) -> None:
        (tmp_path / "with_id.md").write_text("---\nid: DS-007\ntitle: A\n---\n")
        (tmp_path / "without_id.md").write_text("---\ntitle: B\nid: CN-003\n---\n")
        (tmp_path / "not_markdown.txt").write_text("id: DS-999\n")
        result = next_design_id(tmp_path)
        assert result == "DS-008"


# ---------------------------------------------------------------------------
# find_artifact_path
# ---------------------------------------------------------------------------


class TestFindArtifactPath:
    """Scenario: find_artifact_path resolves artifact IDs to file paths."""

    def _setup_lexibrary(self, tmp_path: Path) -> Path:
        """Create a .lexibrary/ directory structure for testing."""
        lib = tmp_path / ".lexibrary"
        for subdir in ("concepts", "conventions", "playbooks", "designs", "stack"):
            (lib / subdir).mkdir(parents=True)
        return tmp_path

    # -- Concept --

    def test_find_concept_by_id(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        concept_file = root / ".lexibrary" / "concepts" / "CN-001-example-concept.md"
        concept_file.write_text("---\nid: CN-001\ntitle: Example\n---\n")
        result = find_artifact_path(root, "CN-001")
        assert result == concept_file

    # -- Convention --

    def test_find_convention_by_id(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        conv_file = root / ".lexibrary" / "conventions" / "CV-002-naming.md"
        conv_file.write_text("---\nid: CV-002\ntitle: Naming\n---\n")
        result = find_artifact_path(root, "CV-002")
        assert result == conv_file

    # -- Playbook --

    def test_find_playbook_by_id(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        pb_file = root / ".lexibrary" / "playbooks" / "PB-003-setup.md"
        pb_file.write_text("---\nid: PB-003\ntitle: Setup\n---\n")
        result = find_artifact_path(root, "PB-003")
        assert result == pb_file

    # -- Stack post --

    def test_find_stack_post_by_id(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        st_file = root / ".lexibrary" / "stack" / "ST-001-debug-issue.md"
        st_file.write_text("---\nid: ST-001\ntitle: Debug\n---\n")
        result = find_artifact_path(root, "ST-001")
        assert result == st_file

    # -- Design file (frontmatter scan) --

    def test_find_design_by_frontmatter_id(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        # Design files use source-mirror paths, not ID-prefixed names
        design_dir = root / ".lexibrary" / "designs" / "src" / "lexibrary"
        design_dir.mkdir(parents=True)
        design_file = design_dir / "main.py.md"
        design_file.write_text("---\nid: DS-001\ndescription: Main module\n---\nBody\n")
        result = find_artifact_path(root, "DS-001")
        assert result == design_file

    def test_find_design_recursive(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        nested_dir = root / ".lexibrary" / "designs" / "src" / "pkg" / "sub"
        nested_dir.mkdir(parents=True)
        nested_file = nested_dir / "module.py.md"
        nested_file.write_text("---\nid: DS-042\ndescription: Nested\n---\n")
        result = find_artifact_path(root, "DS-042")
        assert result == nested_file

    # -- Not found --

    def test_no_matching_file_returns_none(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        result = find_artifact_path(root, "CN-999")
        assert result is None

    def test_missing_directory_returns_none(self, tmp_path: Path) -> None:
        # No .lexibrary/ at all
        result = find_artifact_path(tmp_path, "CN-001")
        assert result is None

    # -- Invalid input --

    def test_invalid_id_format_returns_none(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        result = find_artifact_path(root, "not-an-id")
        assert result is None

    def test_unknown_prefix_returns_none(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        result = find_artifact_path(root, "ZZ-001")
        assert result is None

    def test_design_file_without_matching_id_returns_none(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        design_dir = root / ".lexibrary" / "designs"
        (design_dir / "file.md").write_text("---\nid: DS-010\n---\n")
        result = find_artifact_path(root, "DS-999")
        assert result is None

    def test_design_file_without_frontmatter_skipped(self, tmp_path: Path) -> None:
        root = self._setup_lexibrary(tmp_path)
        design_dir = root / ".lexibrary" / "designs"
        (design_dir / "no-fm.md").write_text("No frontmatter\nid: DS-001\n")
        result = find_artifact_path(root, "DS-001")
        assert result is None
