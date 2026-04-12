"""Tests for lexibrary.services.lookup — lookup service module."""

from __future__ import annotations

import sqlite3
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from lexibrary.services.lookup import (
    ClassHierarchyEntry,
    ConceptSummary,
    DirectoryLookupResult,
    KeySymbolSummary,
    LookupResult,
    SiblingSummary,
    build_directory_lookup,
    build_file_lookup,
    estimate_tokens,
    truncate_lookup_sections,
)
from lexibrary.services.lookup_render import (
    render_call_path_notes,
    render_class_hierarchy,
    render_data_flow_notes,
    render_enum_notes,
    render_key_symbols,
)

# ---------------------------------------------------------------------------
# Dataclass construction tests
# ---------------------------------------------------------------------------


class TestLookupResultDataclass:
    """LookupResult and DirectoryLookupResult can be constructed and inspected."""

    def test_lookup_result_construction(self) -> None:
        """LookupResult can be constructed with all required fields."""
        result = LookupResult(
            file_path="src/main.py",
            description="Main entry point",
            is_stale=False,
            design_content="# Design\nSome content",
            conventions=[],
            conventions_total_count=0,
            display_limit=10,
            playbooks=[],
            playbook_display_limit=5,
            issues_text="",
            iwh_text="",
            links_text="",
            dependents=[],
            open_issue_count=0,
            siblings=[],
            concepts=[],
        )
        assert result.file_path == "src/main.py"
        assert result.description == "Main entry point"
        assert result.is_stale is False
        assert result.design_content is not None
        assert result.open_issue_count == 0
        assert result.siblings == []
        assert result.concepts == []

    def test_lookup_result_none_design(self) -> None:
        """LookupResult accepts None for design_content."""
        result = LookupResult(
            file_path="src/utils.py",
            description=None,
            is_stale=False,
            design_content=None,
            conventions=[],
            conventions_total_count=0,
            display_limit=10,
            playbooks=[],
            playbook_display_limit=5,
            issues_text="",
            iwh_text="",
            links_text="",
            dependents=[],
            open_issue_count=0,
            siblings=[],
            concepts=[],
        )
        assert result.design_content is None
        assert result.description is None

    def test_directory_lookup_result_construction(self) -> None:
        """DirectoryLookupResult can be constructed with all required fields."""
        result = DirectoryLookupResult(
            directory_path="src/lexibrary",
            aindex_content="# src/lexibrary\nSome content",
            conventions=[],
            conventions_total_count=0,
            display_limit=10,
            iwh_text="",
            playbooks=[],
            playbook_display_limit=5,
            import_count=0,
            imported_file_count=0,
        )
        assert result.directory_path == "src/lexibrary"
        assert result.aindex_content is not None
        assert result.iwh_text == ""
        assert result.playbooks == []
        assert result.import_count == 0
        assert result.imported_file_count == 0

    def test_directory_lookup_result_no_aindex(self) -> None:
        """DirectoryLookupResult accepts None for aindex_content."""
        result = DirectoryLookupResult(
            directory_path="src/tests",
            aindex_content=None,
            conventions=[],
            conventions_total_count=0,
            display_limit=10,
            iwh_text="",
            playbooks=[],
            playbook_display_limit=5,
            import_count=0,
            imported_file_count=0,
        )
        assert result.aindex_content is None


# ---------------------------------------------------------------------------
# Token estimation tests
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """Tests for estimate_tokens()."""

    def test_empty_string_returns_zero(self) -> None:
        """Empty string returns 0 tokens."""
        assert estimate_tokens("") == 0

    def test_nonempty_string_returns_positive(self) -> None:
        """Non-empty string returns positive token count."""
        assert estimate_tokens("hello world") > 0

    def test_four_chars_per_token_approximation(self) -> None:
        """Approximation uses ~4 characters per token."""
        assert estimate_tokens("a" * 400) == 100

    def test_minimum_one_token_for_short_text(self) -> None:
        """Very short text returns at least 1 token."""
        assert estimate_tokens("hi") >= 1


# ---------------------------------------------------------------------------
# Truncation tests
# ---------------------------------------------------------------------------


class TestTruncateLookupSections:
    """Tests for truncate_lookup_sections()."""

    def test_respects_priority_order(self) -> None:
        """Higher-priority sections are kept when budget is tight."""
        sections = [
            ("design", "x" * 400, 0),  # ~100 tokens
            ("conventions", "y" * 400, 1),  # ~100 tokens
            ("issues", "z" * 400, 2),  # ~100 tokens
            ("iwh", "w" * 400, 3),  # ~100 tokens
            ("links", "v" * 400, 4),  # ~100 tokens
        ]
        result = truncate_lookup_sections(sections, total_budget=200)
        names = [name for name, _ in result]
        assert "design" in names
        assert "conventions" in names
        assert len(result) <= 3  # at most design + conventions + partial

    def test_empty_sections_skipped(self) -> None:
        """Empty sections are not included in output."""
        sections = [
            ("design", "content here", 0),
            ("conventions", "", 1),
            ("issues", "", 2),
        ]
        result = truncate_lookup_sections(sections, total_budget=5000)
        names = [name for name, _ in result]
        assert "design" in names
        assert "conventions" not in names
        assert "issues" not in names

    def test_all_fit_within_budget(self) -> None:
        """When budget is large enough, all sections are included."""
        sections = [
            ("issues", "short text", 2),
            ("iwh", "more text", 3),
            ("links", "link data", 4),
        ]
        result = truncate_lookup_sections(sections, total_budget=100_000)
        names = [name for name, _ in result]
        assert "issues" in names
        assert "iwh" in names
        assert "links" in names

    def test_truncation_appends_notice(self) -> None:
        """When a section is truncated, a notice is appended."""
        sections = [
            ("issues", "x" * 1000, 2),  # ~250 tokens
        ]
        # Budget allows partial inclusion (> 50 tokens remaining)
        result = truncate_lookup_sections(sections, total_budget=100)
        assert len(result) == 1
        _name, content = result[0]
        assert "truncated due to token budget" in content

    def test_very_tight_budget_excludes_section(self) -> None:
        """When remaining budget is <= 50 tokens, section is excluded entirely."""
        sections = [
            ("issues", "x" * 1000, 2),  # ~250 tokens
        ]
        result = truncate_lookup_sections(sections, total_budget=10)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Import independence test
# ---------------------------------------------------------------------------


class TestImportIndependence:
    """Verify service module imports without CLI dependencies."""

    def test_import_without_cli_deps(self) -> None:
        """LookupResult is importable without pulling in CLI modules."""
        # This test verifies the spec requirement that dataclasses are
        # importable without typer, _output, or _format.
        import importlib

        mod = importlib.import_module("lexibrary.services.lookup")
        assert hasattr(mod, "LookupResult")
        assert hasattr(mod, "DirectoryLookupResult")
        assert hasattr(mod, "build_file_lookup")
        assert hasattr(mod, "build_directory_lookup")
        assert hasattr(mod, "estimate_tokens")
        assert hasattr(mod, "truncate_lookup_sections")


# ---------------------------------------------------------------------------
# 6.1 — SiblingSummary and ConceptSummary dataclass construction
# ---------------------------------------------------------------------------


class TestSiblingSummaryDataclass:
    """SiblingSummary dataclass construction and field access."""

    def test_construction_with_required_fields(self) -> None:
        """SiblingSummary can be constructed with name and description."""
        s = SiblingSummary(name="search.py", description="Cross-artifact search")
        assert s.name == "search.py"
        assert s.description == "Cross-artifact search"

    def test_field_names(self) -> None:
        """SiblingSummary has exactly name and description fields."""
        names = {f.name for f in dataclass_fields(SiblingSummary)}
        assert names == {"name", "description"}

    def test_field_types(self) -> None:
        """SiblingSummary fields are annotated as str."""
        field_map = {f.name: f.type for f in dataclass_fields(SiblingSummary)}
        assert field_map["name"] == "str"
        assert field_map["description"] == "str"

    def test_equality(self) -> None:
        """Two SiblingSummary with same fields are equal (dataclass default)."""
        a = SiblingSummary(name="a.py", description="desc")
        b = SiblingSummary(name="a.py", description="desc")
        assert a == b

    def test_inequality(self) -> None:
        """Different field values produce unequal instances."""
        a = SiblingSummary(name="a.py", description="desc A")
        b = SiblingSummary(name="b.py", description="desc B")
        assert a != b


class TestConceptSummaryDataclass:
    """ConceptSummary dataclass construction and field access."""

    def test_construction_all_fields(self) -> None:
        """ConceptSummary can be constructed with all fields."""
        c = ConceptSummary(
            name="error-handling", status="active", summary="Error handling patterns"
        )
        assert c.name == "error-handling"
        assert c.status == "active"
        assert c.summary == "Error handling patterns"

    def test_status_none(self) -> None:
        """ConceptSummary accepts None for status."""
        c = ConceptSummary(name="my-concept", status=None, summary=None)
        assert c.status is None

    def test_summary_none(self) -> None:
        """ConceptSummary accepts None for summary."""
        c = ConceptSummary(name="my-concept", status="draft", summary=None)
        assert c.summary is None

    def test_field_names(self) -> None:
        """ConceptSummary has name, status, and summary fields."""
        names = {f.name for f in dataclass_fields(ConceptSummary)}
        assert names == {"name", "status", "summary"}

    def test_field_types(self) -> None:
        """ConceptSummary fields have correct type annotations."""
        field_map = {f.name: f.type for f in dataclass_fields(ConceptSummary)}
        assert field_map["name"] == "str"
        assert field_map["status"] == "str | None"
        assert field_map["summary"] == "str | None"


# ---------------------------------------------------------------------------
# 6.2 — LookupResult with new siblings, concepts, concepts_linkgraph_available
# ---------------------------------------------------------------------------


class TestLookupResultNewFields:
    """LookupResult construction with siblings, concepts, and linkgraph flag."""

    def _make_result(self, **overrides: object) -> LookupResult:
        """Build a LookupResult with defaults, overriding specified fields."""
        defaults: dict[str, object] = {
            "file_path": "src/foo.py",
            "description": "A module",
            "is_stale": False,
            "design_content": None,
            "conventions": [],
            "conventions_total_count": 0,
            "display_limit": 10,
            "playbooks": [],
            "playbook_display_limit": 5,
            "issues_text": "",
            "iwh_text": "",
            "links_text": "",
            "dependents": [],
            "open_issue_count": 0,
            "siblings": [],
            "concepts": [],
        }
        defaults.update(overrides)
        return LookupResult(**defaults)  # type: ignore[arg-type]

    def test_siblings_field_present(self) -> None:
        """LookupResult has a siblings field."""
        r = self._make_result()
        assert r.siblings == []

    def test_siblings_populated(self) -> None:
        """LookupResult accepts a list of SiblingSummary."""
        siblings = [
            SiblingSummary(name="a.py", description="Module A"),
            SiblingSummary(name="b.py", description="Module B"),
        ]
        r = self._make_result(siblings=siblings)
        assert len(r.siblings) == 2
        assert r.siblings[0].name == "a.py"
        assert r.siblings[1].description == "Module B"

    def test_concepts_field_present(self) -> None:
        """LookupResult has a concepts field."""
        r = self._make_result()
        assert r.concepts == []

    def test_concepts_populated(self) -> None:
        """LookupResult accepts a list of ConceptSummary."""
        concepts = [
            ConceptSummary(name="error-handling", status="active", summary="Patterns"),
        ]
        r = self._make_result(concepts=concepts)
        assert len(r.concepts) == 1
        assert r.concepts[0].name == "error-handling"

    def test_concepts_linkgraph_available_default_true(self) -> None:
        """concepts_linkgraph_available defaults to True."""
        r = self._make_result()
        assert r.concepts_linkgraph_available is True

    def test_concepts_linkgraph_available_false(self) -> None:
        """concepts_linkgraph_available can be set to False."""
        r = self._make_result(concepts_linkgraph_available=False)
        assert r.concepts_linkgraph_available is False


# ---------------------------------------------------------------------------
# 6.3 — DirectoryLookupResult with new fields
# ---------------------------------------------------------------------------


class TestDirectoryLookupResultNewFields:
    """DirectoryLookupResult construction with playbooks, import counts."""

    def _make_result(self, **overrides: object) -> DirectoryLookupResult:
        defaults: dict[str, object] = {
            "directory_path": "src/lexibrary",
            "aindex_content": None,
            "conventions": [],
            "conventions_total_count": 0,
            "display_limit": 10,
            "iwh_text": "",
            "playbooks": [],
            "playbook_display_limit": 5,
            "import_count": 0,
            "imported_file_count": 0,
        }
        defaults.update(overrides)
        return DirectoryLookupResult(**defaults)  # type: ignore[arg-type]

    def test_playbooks_field_default_empty(self) -> None:
        """playbooks field defaults to empty list."""
        r = self._make_result()
        assert r.playbooks == []

    def test_playbooks_populated(self) -> None:
        """playbooks field accepts a list of PlaybookFile-like objects."""
        mock_pb = MagicMock()
        mock_pb.frontmatter.title = "Deploy Guide"
        r = self._make_result(playbooks=[mock_pb])
        assert len(r.playbooks) == 1

    def test_playbook_display_limit(self) -> None:
        """playbook_display_limit holds the configured value."""
        r = self._make_result(playbook_display_limit=3)
        assert r.playbook_display_limit == 3

    def test_import_count_zero(self) -> None:
        """import_count defaults to 0."""
        r = self._make_result()
        assert r.import_count == 0

    def test_import_count_positive(self) -> None:
        """import_count can be set to a positive value."""
        r = self._make_result(import_count=15, imported_file_count=7)
        assert r.import_count == 15
        assert r.imported_file_count == 7

    def test_imported_file_count_zero(self) -> None:
        """imported_file_count defaults to 0."""
        r = self._make_result()
        assert r.imported_file_count == 0


# ---------------------------------------------------------------------------
# Helpers for build_file_lookup / build_directory_lookup tests
# ---------------------------------------------------------------------------


def _make_config(
    *,
    convention_limit: int = 10,
    playbook_limit: int = 5,
    stack_limit: int = 5,
    concept_limit: int = 10,
    scope_root: str = "project",
) -> object:
    """Create a real LexibraryConfig for testing service functions."""
    from lexibrary.config.schema import (  # noqa: PLC0415
        ConceptConfig,
        ConventionConfig,
        LexibraryConfig,
        PlaybookConfig,
        StackConfig,
    )

    return LexibraryConfig(
        scope_root=scope_root,
        conventions=ConventionConfig(lookup_display_limit=convention_limit),
        playbooks=PlaybookConfig(lookup_display_limit=playbook_limit),
        stack=StackConfig(lookup_display_limit=stack_limit),
        concepts=ConceptConfig(lookup_display_limit=concept_limit),
    )


def _setup_minimal_project(tmp_path: Path) -> Path:
    """Create a minimal project structure for build_file_lookup tests.

    Returns the project root (tmp_path itself).
    """
    # Create source file
    src_dir = tmp_path / "src" / "pkg"
    src_dir.mkdir(parents=True)
    (src_dir / "mymodule.py").write_text("# module code\n", encoding="utf-8")
    (src_dir / "sibling.py").write_text("# sibling\n", encoding="utf-8")
    (src_dir / "another.py").write_text("# another\n", encoding="utf-8")

    # Create .lexibrary structure
    lex_dir = tmp_path / ".lexibrary"
    (lex_dir / "conventions").mkdir(parents=True)
    (lex_dir / "concepts").mkdir(parents=True)
    (lex_dir / "playbooks").mkdir(parents=True)

    # Create designs mirror
    designs_dir = lex_dir / "designs" / "src" / "pkg"
    designs_dir.mkdir(parents=True)

    return tmp_path


def _write_aindex(designs_dir: Path, dir_rel_path: str, entries: list[dict[str, str]]) -> None:
    """Write a .aindex file with specified entries."""
    lines = [f"---\ndirectory_path: {dir_rel_path}\nbillboard: Test directory\n---\n"]
    for entry in entries:
        lines.append(
            f"- name: {entry['name']}\n"
            f"  entry_type: {entry['type']}\n"
            f"  description: {entry['description']}\n"
        )
    aindex_dir = designs_dir / dir_rel_path
    aindex_dir.mkdir(parents=True, exist_ok=True)
    (aindex_dir / ".aindex").write_text("".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 6.4 — Sibling population in build_file_lookup
# ---------------------------------------------------------------------------


class TestBuildFileLookupSiblings:
    """Tests for sibling population in build_file_lookup()."""

    def test_siblings_from_aindex_file_entries(self, tmp_path: Path) -> None:
        """Aindex with 3 file entries + 1 dir entry yields 3 siblings."""
        from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile  # noqa: PLC0415
        from lexibrary.artifacts.design_file import StalenessMetadata  # noqa: PLC0415

        project_root = _setup_minimal_project(tmp_path)

        # Write a real .aindex that parse_aindex can read, or mock it.
        # Since parse_aindex uses its own format, we mock at source module level.
        aindex = AIndexFile(
            directory_path="src/pkg",
            billboard="Package directory",
            entries=[
                AIndexEntry(name="mymodule.py", entry_type="file", description="Main module"),
                AIndexEntry(name="sibling.py", entry_type="file", description="Sibling module"),
                AIndexEntry(name="another.py", entry_type="file", description="Another module"),
                AIndexEntry(name="subdir", entry_type="dir", description="A subdirectory"),
            ],
            metadata=StalenessMetadata(
                source="src/pkg",
                source_hash="abc123",
                generated=datetime(2026, 1, 1),
                generator="test",
            ),
        )

        config = _make_config()

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=aindex),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=None,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=Path("/nonexistent"),
            ),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            target = project_root / "src" / "pkg" / "mymodule.py"
            result = build_file_lookup(target, project_root, config)

        assert result is not None
        assert len(result.siblings) == 3
        names = [s.name for s in result.siblings]
        assert "mymodule.py" in names
        assert "sibling.py" in names
        assert "another.py" in names
        # Dir entry should be excluded
        assert "subdir" not in names

    def test_siblings_empty_when_aindex_missing(self, tmp_path: Path) -> None:
        """Missing .aindex yields empty siblings list."""
        config = _make_config()
        project_root = _setup_minimal_project(tmp_path)

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=None,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=Path("/nonexistent"),
            ),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            target = project_root / "src" / "pkg" / "mymodule.py"
            result = build_file_lookup(target, project_root, config)

        assert result is not None
        assert result.siblings == []


# ---------------------------------------------------------------------------
# 6.5 — Concept population in build_file_lookup
# ---------------------------------------------------------------------------


class TestBuildFileLookupConcepts:
    """Tests for concept population in build_file_lookup()."""

    def test_brief_mode_concepts_from_wikilinks(self, tmp_path: Path) -> None:
        """Brief mode extracts concepts from design file wikilinks, summary is None."""
        config = _make_config()
        project_root = _setup_minimal_project(tmp_path)

        mock_design_file = MagicMock()
        mock_design_file.wikilinks = ["error-handling", "logging"]

        mock_design_path = MagicMock(spec=Path)
        mock_design_path.exists.return_value = True

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=mock_design_file,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=mock_design_path,
            ),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            target = project_root / "src" / "pkg" / "mymodule.py"
            result = build_file_lookup(target, project_root, config, full=False)

        assert result is not None
        assert len(result.concepts) == 2
        assert result.concepts[0].name == "error-handling"
        assert result.concepts[0].summary is None  # Brief mode: no summary
        assert result.concepts[1].name == "logging"

    def test_full_mode_concepts_from_linkgraph(self, tmp_path: Path) -> None:
        """Full mode with link graph populates concepts with status and summary."""
        config = _make_config()
        project_root = _setup_minimal_project(tmp_path)

        mock_design_path = MagicMock(spec=Path)
        mock_design_path.exists.return_value = True
        mock_design_path.read_text.return_value = "# Design\nContent"
        mock_design_path.relative_to.return_value = Path(".lexibrary/designs/src/pkg/mymodule.md")

        # Create a mock link graph
        mock_link_graph = MagicMock()

        wikilink_link = MagicMock()
        wikilink_link.link_type = "wikilink"
        wikilink_link.link_context = "error-handling"
        wikilink_link.source_path = ".lexibrary/concepts/error-handling.md"

        concept_ref_link = MagicMock()
        concept_ref_link.link_type = "concept_file_ref"
        concept_ref_link.link_context = "logging"
        concept_ref_link.source_path = ".lexibrary/concepts/logging.md"

        def reverse_deps_side_effect(path: str, link_type: str | None = None) -> list[object]:
            if link_type == "ast_import":
                return []
            if link_type == "stack_file_ref":
                return []
            # All links (no link_type filter)
            return [wikilink_link, concept_ref_link]

        mock_link_graph.reverse_deps = MagicMock(side_effect=reverse_deps_side_effect)
        mock_link_graph.close = MagicMock()

        # Concept index with known concepts
        mock_concept_index = MagicMock()

        def find_side_effect(name: str) -> object | None:
            if name == "error-handling":
                cf = MagicMock()
                cf.frontmatter.status = "active"
                cf.summary = "Error handling patterns"
                return cf
            if name == "logging":
                cf = MagicMock()
                cf.frontmatter.status = "draft"
                cf.summary = None
                return cf
            return None

        mock_concept_index.find = MagicMock(side_effect=find_side_effect)

        open_index_patch = patch("lexibrary.linkgraph.open_index", return_value=mock_link_graph)

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=None,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=mock_design_path,
            ),
            open_index_patch,
            patch("lexibrary.wiki.index.ConceptIndex.load", return_value=mock_concept_index),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            target = project_root / "src" / "pkg" / "mymodule.py"
            result = build_file_lookup(target, project_root, config, full=True)

        assert result is not None
        assert result.concepts_linkgraph_available is True
        assert len(result.concepts) == 2
        assert result.concepts[0].name == "error-handling"
        assert result.concepts[0].status == "active"
        assert result.concepts[0].summary == "Error handling patterns"
        assert result.concepts[1].name == "logging"
        assert result.concepts[1].status == "draft"
        assert result.concepts[1].summary is None

    def test_full_mode_fallback_when_no_linkgraph(self, tmp_path: Path) -> None:
        """Full mode without link graph falls back to wikilinks, linkgraph_available=False."""
        config = _make_config()
        project_root = _setup_minimal_project(tmp_path)

        mock_design_file = MagicMock()
        mock_design_file.wikilinks = ["my-concept"]

        mock_design_path = MagicMock(spec=Path)
        mock_design_path.exists.return_value = True
        mock_design_path.read_text.return_value = "# Design"

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=mock_design_file,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=mock_design_path,
            ),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            target = project_root / "src" / "pkg" / "mymodule.py"
            result = build_file_lookup(target, project_root, config, full=True)

        assert result is not None
        assert result.concepts_linkgraph_available is False
        assert len(result.concepts) == 1
        assert result.concepts[0].name == "my-concept"
        assert result.concepts[0].status is None

    def test_concept_display_limit_respected(self, tmp_path: Path) -> None:
        """Concepts list is capped at lookup_display_limit."""
        config = _make_config(concept_limit=2)
        project_root = _setup_minimal_project(tmp_path)

        mock_design_file = MagicMock()
        mock_design_file.wikilinks = ["concept-a", "concept-b", "concept-c", "concept-d"]

        mock_design_path = MagicMock(spec=Path)
        mock_design_path.exists.return_value = True

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=mock_design_file,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=mock_design_path,
            ),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            target = project_root / "src" / "pkg" / "mymodule.py"
            result = build_file_lookup(target, project_root, config, full=False)

        assert result is not None
        assert len(result.concepts) == 2


# ---------------------------------------------------------------------------
# 6.10 — Directory lookup with new fields
# ---------------------------------------------------------------------------


class TestBuildDirectoryLookupNewFields:
    """Tests for build_directory_lookup() with playbooks, import counts."""

    def test_populates_playbooks_via_by_trigger_dir(self, tmp_path: Path) -> None:
        """build_directory_lookup() populates playbooks via by_trigger_dir()."""
        config = _make_config()
        project_root = _setup_minimal_project(tmp_path)

        mock_pb = MagicMock()
        mock_pb.frontmatter.title = "CLI Playbook"

        mock_playbook_index = MagicMock()
        mock_playbook_index.by_trigger_dir.return_value = [mock_pb]

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
            patch("lexibrary.conventions.index.ConventionIndex") as mock_conv_cls,
            patch("lexibrary.playbooks.index.PlaybookIndex") as mock_pb_cls,
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            mock_conv_inst = MagicMock()
            mock_conv_inst.__len__ = MagicMock(return_value=0)
            mock_conv_cls.return_value = mock_conv_inst

            mock_pb_cls.return_value = mock_playbook_index
            target = project_root / "src" / "pkg"
            result = build_directory_lookup(target, project_root, config)

        assert result is not None
        assert len(result.playbooks) == 1
        assert result.playbooks[0].frontmatter.title == "CLI Playbook"
        mock_playbook_index.by_trigger_dir.assert_called_once_with("src/pkg")

    def test_populates_import_counts_from_linkgraph(self, tmp_path: Path) -> None:
        """build_directory_lookup() populates import counts from link graph."""
        from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile  # noqa: PLC0415
        from lexibrary.artifacts.design_file import StalenessMetadata  # noqa: PLC0415

        config = _make_config()
        project_root = _setup_minimal_project(tmp_path)

        aindex = AIndexFile(
            directory_path="src/pkg",
            billboard="Package",
            entries=[
                AIndexEntry(name="a.py", entry_type="file", description="Module A"),
                AIndexEntry(name="b.py", entry_type="file", description="Module B"),
            ],
            metadata=StalenessMetadata(
                source="src/pkg",
                source_hash="abc",
                generated=datetime(2026, 1, 1),
                generator="test",
            ),
        )

        # Mock link graph with import links
        mock_link_graph = MagicMock()
        link_from_x = MagicMock()
        link_from_x.source_path = "src/other/x.py"
        link_from_y = MagicMock()
        link_from_y.source_path = "src/other/y.py"
        link_from_x2 = MagicMock()
        link_from_x2.source_path = "src/other/x.py"  # same file importing both a.py and b.py

        def reverse_deps_side_effect(path: str, link_type: str | None = None) -> list[object]:
            if path == "src/pkg/a.py":
                return [link_from_x, link_from_y]  # 2 imports from 2 files
            if path == "src/pkg/b.py":
                return [link_from_x2]  # 1 import from same file as a.py
            return []

        mock_link_graph.reverse_deps = MagicMock(side_effect=reverse_deps_side_effect)
        mock_link_graph.close = MagicMock()

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=aindex),
            patch("lexibrary.linkgraph.open_index", return_value=mock_link_graph),
            patch("lexibrary.conventions.index.ConventionIndex") as mock_conv_cls,
            patch("lexibrary.playbooks.index.PlaybookIndex") as mock_pb_cls,
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            mock_conv_inst = MagicMock()
            mock_conv_inst.__len__ = MagicMock(return_value=0)
            mock_conv_cls.return_value = mock_conv_inst

            mock_pb_inst = MagicMock()
            mock_pb_inst.by_trigger_dir.return_value = []
            mock_pb_cls.return_value = mock_pb_inst

            target = project_root / "src" / "pkg"
            result = build_directory_lookup(target, project_root, config)

        assert result is not None
        assert result.import_count == 3  # 2 + 1
        assert result.imported_file_count == 2  # x.py and y.py (deduplicated)
        mock_link_graph.close.assert_called_once()

    def test_import_counts_zero_when_no_linkgraph(self, tmp_path: Path) -> None:
        """build_directory_lookup() sets import counts to 0 when link graph unavailable."""
        config = _make_config()
        project_root = _setup_minimal_project(tmp_path)

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
            patch("lexibrary.conventions.index.ConventionIndex") as mock_conv_cls,
            patch("lexibrary.playbooks.index.PlaybookIndex") as mock_pb_cls,
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            mock_conv_inst = MagicMock()
            mock_conv_inst.__len__ = MagicMock(return_value=0)
            mock_conv_cls.return_value = mock_conv_inst

            mock_pb_inst = MagicMock()
            mock_pb_inst.by_trigger_dir.return_value = []
            mock_pb_cls.return_value = mock_pb_inst

            target = project_root / "src" / "pkg"
            result = build_directory_lookup(target, project_root, config)

        assert result is not None
        assert result.import_count == 0
        assert result.imported_file_count == 0


# ---------------------------------------------------------------------------
# 14 — Key symbols section (symbol-graph-2 Group 14)
# ---------------------------------------------------------------------------
#
# These tests exercise the ``key_symbols`` field on ``LookupResult`` end to
# end by standing up a real ``.lexibrary/symbols.db`` seeded with the exact
# symbol rows each scenario needs. They do **not** mock the
# ``SymbolQueryService`` — doing so would sidestep the "exactly one
# ``symbol_call_counts`` query" guarantee, which is the main perf contract
# for this feature.


def _seed_key_symbols_fixture(
    project_root: Path,
    rel_file: str,
    *,
    symbols: list[dict[str, object]],
    calls: list[tuple[int, int]] | None = None,
) -> dict[str, int]:
    """Seed ``symbols.db`` with the rows needed for a Key symbols test.

    *symbols* is a list of dicts with keys ``name``, ``qualified_name``,
    ``symbol_type``, ``line_start``, ``line_end``, ``visibility`` (plus
    optional ``parent_class``). *calls* is a list of ``(caller_idx,
    callee_idx)`` index pairs referring to positions in *symbols* — each
    tuple inserts one resolved call edge so the
    ``symbol_call_counts`` query returns non-zero caller/callee counts
    for the linked symbols.

    Returns a ``{name: symbol_id}`` map so callers can cross-reference
    the inserted rows (for the "single-query" spy test that wants the
    exact id set).
    """
    from lexibrary.symbolgraph.query import open_symbol_graph  # noqa: PLC0415

    # ``open_symbol_graph`` creates ``.lexibrary/symbols.db`` with an
    # empty schema when the file does not yet exist. We deliberately
    # skip the full ``build_symbol_graph`` walker so the test controls
    # exactly which files / symbols end up in the DB (otherwise the
    # walker would scan ``tmp_path`` and insert any ``*.py`` files it
    # finds, which collides with our explicit inserts below).
    graph = open_symbol_graph(project_root)
    assert graph is not None
    try:
        conn: sqlite3.Connection = graph._conn  # noqa: SLF001

        cur = conn.execute(
            "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
            (rel_file, "python", "deadbeef"),
        )
        file_id = int(cur.lastrowid or 0)

        ids: dict[str, int] = {}
        symbol_ids_in_order: list[int] = []
        for row in symbols:
            cur = conn.execute(
                "INSERT INTO symbols "
                "(file_id, name, qualified_name, symbol_type, line_start, "
                "line_end, visibility, parent_class) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file_id,
                    row["name"],
                    row.get("qualified_name"),
                    row["symbol_type"],
                    row["line_start"],
                    row.get("line_end"),
                    row["visibility"],
                    row.get("parent_class"),
                ),
            )
            sid = int(cur.lastrowid or 0)
            ids[str(row["name"])] = sid
            symbol_ids_in_order.append(sid)

        for line_offset, (caller_idx, callee_idx) in enumerate(calls or []):
            conn.execute(
                "INSERT INTO calls (caller_id, callee_id, line, call_context) VALUES (?, ?, ?, ?)",
                (
                    symbol_ids_in_order[caller_idx],
                    symbol_ids_in_order[callee_idx],
                    100 + line_offset,  # arbitrary distinct line per edge
                    "call",
                ),
            )

        conn.commit()
    finally:
        graph.close()

    return ids


def _make_linkgraph_db(project_root: Path) -> None:
    """Create an empty but schema-valid ``index.db`` for lookup tests.

    ``build_file_lookup`` calls :func:`lexibrary.linkgraph.open_index`
    under the hood; the service returns ``None`` unless a valid
    ``index.db`` exists, which disables the dependents / concept-link
    code paths we don't care about here. Providing an empty but valid
    DB keeps those paths on the happy-no-results branch without affecting
    key_symbols assertions.
    """
    from lexibrary.linkgraph.schema import (  # noqa: PLC0415
        ensure_schema as ensure_linkgraph_schema,
    )

    db_path = project_root / ".lexibrary" / "index.db"
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_linkgraph_schema(conn)
        conn.commit()
    finally:
        conn.close()


def _seed_class_hierarchy_fixture(
    project_root: Path,
    *,
    files: list[dict[str, object]],
    class_edges: list[dict[str, object]] | None = None,
    unresolved_edges: list[dict[str, object]] | None = None,
) -> dict[str, int]:
    """Seed ``symbols.db`` with the rows needed for a Class hierarchy test.

    *files* is a list of ``{"path": ..., "symbols": [...]}`` dicts. Each
    symbol dict matches :func:`_seed_key_symbols_fixture`'s schema (name,
    qualified_name, symbol_type, line_start, line_end, visibility,
    optional parent_class). *class_edges* is a list of
    ``{"source_name": ..., "target_name": ..., "edge_type": ...,
    "line": ...}`` dicts referring to symbol names that were inserted in
    *files*. *unresolved_edges* is a list of
    ``{"source_name": ..., "target_name": ..., "edge_type": ...,
    "line": ...}`` dicts, with ``target_name`` as a plain string (e.g.
    ``"BaseModel"``).

    Returns a ``{name: symbol_id}`` map merged across every file so the
    caller can cross-reference any seeded row by its bare ``name``.
    """
    from lexibrary.symbolgraph.query import open_symbol_graph  # noqa: PLC0415

    graph = open_symbol_graph(project_root)
    assert graph is not None
    try:
        conn: sqlite3.Connection = graph._conn  # noqa: SLF001

        ids: dict[str, int] = {}
        for file_entry in files:
            rel_path = str(file_entry["path"])
            cur = conn.execute(
                "INSERT INTO files (path, language, last_hash) VALUES (?, ?, ?)",
                (rel_path, "python", "deadbeef"),
            )
            file_id = int(cur.lastrowid or 0)

            symbols_in_file = file_entry.get("symbols", [])
            assert isinstance(symbols_in_file, list)
            for row in symbols_in_file:
                cur = conn.execute(
                    "INSERT INTO symbols "
                    "(file_id, name, qualified_name, symbol_type, line_start, "
                    "line_end, visibility, parent_class) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        file_id,
                        row["name"],
                        row.get("qualified_name"),
                        row["symbol_type"],
                        row["line_start"],
                        row.get("line_end"),
                        row["visibility"],
                        row.get("parent_class"),
                    ),
                )
                ids[str(row["name"])] = int(cur.lastrowid or 0)

        for edge in class_edges or []:
            src_name = str(edge["source_name"])
            tgt_name = str(edge["target_name"])
            conn.execute(
                "INSERT INTO class_edges "
                "(source_id, target_id, edge_type, line, context) "
                "VALUES (?, ?, ?, ?, NULL)",
                (
                    ids[src_name],
                    ids[tgt_name],
                    str(edge["edge_type"]),
                    edge.get("line"),
                ),
            )

        for unresolved in unresolved_edges or []:
            src_name = str(unresolved["source_name"])
            conn.execute(
                "INSERT INTO class_edges_unresolved "
                "(source_id, target_name, edge_type, line) "
                "VALUES (?, ?, ?, ?)",
                (
                    ids[src_name],
                    str(unresolved["target_name"]),
                    str(unresolved["edge_type"]),
                    unresolved.get("line"),
                ),
            )

        conn.commit()
    finally:
        graph.close()

    return ids


class TestKeySymbolSummaryDataclass:
    """Covers the KeySymbolSummary dataclass surface (task 14.1 / scenario 1)."""

    def test_construction_with_all_fields(self) -> None:
        """KeySymbolSummary exposes every spec-mandated field."""
        summary = KeySymbolSummary(
            name="foo",
            qualified_name=None,
            symbol_type="function",
            line_start=1,
            caller_count=0,
            callee_count=0,
        )
        assert summary.name == "foo"
        assert summary.qualified_name is None
        assert summary.symbol_type == "function"
        assert summary.line_start == 1
        assert summary.caller_count == 0
        assert summary.callee_count == 0

    def test_field_names(self) -> None:
        """The dataclass field names match the spec verbatim."""
        names = {f.name for f in dataclass_fields(KeySymbolSummary)}
        assert names == {
            "name",
            "qualified_name",
            "symbol_type",
            "line_start",
            "caller_count",
            "callee_count",
        }


class TestBuildFileLookupKeySymbols:
    """Exercise build_file_lookup()'s ``key_symbols`` population."""

    def _patched_lookup(
        self,
        *,
        target: Path,
        project_root: Path,
        config: object,
        full: bool = False,
    ) -> LookupResult | None:
        """Run build_file_lookup with the ambient aindex / design patches.

        The ``key_symbols`` tests don't care about siblings, conventions,
        concepts, or issues — the patches here short-circuit those code
        paths so only the symbol-graph branch stays live.
        """
        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=None,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=Path("/nonexistent"),
            ),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            return build_file_lookup(target, project_root, config, full=full)

    def test_lookup_includes_key_symbols_section(self, tmp_path: Path) -> None:
        """A file with two public functions yields two KeySymbolSummary entries."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        _seed_key_symbols_fixture(
            project_root,
            rel_file="src/pkg/mymodule.py",
            symbols=[
                {
                    "name": "foo",
                    "qualified_name": "pkg.mymodule.foo",
                    "symbol_type": "function",
                    "line_start": 10,
                    "line_end": 20,
                    "visibility": "public",
                },
                {
                    "name": "bar",
                    "qualified_name": "pkg.mymodule.bar",
                    "symbol_type": "function",
                    "line_start": 30,
                    "line_end": 40,
                    "visibility": "public",
                },
            ],
            calls=[(0, 1)],  # foo calls bar -> bar has caller_count 1, foo callee_count 1
        )

        config = _make_config()
        target = project_root / "src" / "pkg" / "mymodule.py"

        result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert len(result.key_symbols) == 2
        assert result.key_symbols_total == 2
        by_name = {s.name: s for s in result.key_symbols}
        assert set(by_name) == {"foo", "bar"}
        assert by_name["foo"].symbol_type == "function"
        assert by_name["foo"].line_start == 10
        assert by_name["foo"].qualified_name == "pkg.mymodule.foo"
        # foo -> bar was the only edge, so bar has one caller and foo has
        # one callee; everybody else is at 0.
        assert by_name["bar"].caller_count == 1
        assert by_name["bar"].callee_count == 0
        assert by_name["foo"].caller_count == 0
        assert by_name["foo"].callee_count == 1

    def test_lookup_skips_key_symbols_when_disabled(self, tmp_path: Path) -> None:
        """config.symbols.enabled = False ⇒ key_symbols is [] without opening the service."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        # Seed the DB so we'd notice if the service opened it anyway.
        _seed_key_symbols_fixture(
            project_root,
            rel_file="src/pkg/mymodule.py",
            symbols=[
                {
                    "name": "foo",
                    "qualified_name": "pkg.mymodule.foo",
                    "symbol_type": "function",
                    "line_start": 10,
                    "line_end": 20,
                    "visibility": "public",
                },
            ],
        )

        from lexibrary.config.schema import (  # noqa: PLC0415
            ConceptConfig,
            ConventionConfig,
            LexibraryConfig,
            PlaybookConfig,
            StackConfig,
            SymbolGraphConfig,
        )

        config = LexibraryConfig(
            scope_root="project",
            conventions=ConventionConfig(),
            playbooks=PlaybookConfig(),
            stack=StackConfig(),
            concepts=ConceptConfig(),
            symbols=SymbolGraphConfig(enabled=False),
        )

        target = project_root / "src" / "pkg" / "mymodule.py"

        # A tripwire patch on the service class itself — the disabled
        # branch MUST short-circuit before constructing the service.
        with patch(
            "lexibrary.services.symbols.SymbolQueryService.__init__",
            side_effect=AssertionError(
                "SymbolQueryService was constructed even though config.symbols.enabled is False"
            ),
        ):
            result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert result.key_symbols == []
        assert result.key_symbols_total == 0

    def test_lookup_skips_key_symbols_when_db_missing(self, tmp_path: Path) -> None:
        """Missing symbols.db ⇒ key_symbols is [] and no exception is raised."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        # Deliberately do NOT call _seed_key_symbols_fixture — no
        # symbols.db exists for this test.
        assert not (project_root / ".lexibrary" / "symbols.db").exists()

        config = _make_config()
        target = project_root / "src" / "pkg" / "mymodule.py"

        result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert result.key_symbols == []
        assert result.key_symbols_total == 0

    def test_lookup_uses_single_call_counts_query(self, tmp_path: Path) -> None:
        """symbol_call_counts must be called exactly once per lookup_file."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        _seed_key_symbols_fixture(
            project_root,
            rel_file="src/pkg/mymodule.py",
            symbols=[
                {
                    "name": "foo",
                    "qualified_name": "pkg.mymodule.foo",
                    "symbol_type": "function",
                    "line_start": 1,
                    "line_end": 5,
                    "visibility": "public",
                },
                {
                    "name": "bar",
                    "qualified_name": "pkg.mymodule.bar",
                    "symbol_type": "function",
                    "line_start": 7,
                    "line_end": 12,
                    "visibility": "public",
                },
                {
                    "name": "baz",
                    "qualified_name": "pkg.mymodule.baz",
                    "symbol_type": "function",
                    "line_start": 14,
                    "line_end": 18,
                    "visibility": "public",
                },
            ],
            # Three call edges give each symbol a non-zero count so the
            # test notices if the implementation short-circuited the
            # count-fetch for zero-count rows.
            calls=[(0, 1), (1, 2), (0, 2)],
        )

        config = _make_config()
        target = project_root / "src" / "pkg" / "mymodule.py"

        from lexibrary.symbolgraph.query import SymbolGraph  # noqa: PLC0415

        original = SymbolGraph.symbol_call_counts
        call_count = 0

        def spy(self: SymbolGraph, file_path: str) -> dict[int, tuple[int, int]]:
            nonlocal call_count
            call_count += 1
            return original(self, file_path)

        with patch.object(SymbolGraph, "symbol_call_counts", spy):
            result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert len(result.key_symbols) == 3
        # Exactly one aggregation query — no N+1 per symbol.
        assert call_count == 1


class TestRenderKeySymbols:
    """Covers render_key_symbols() format + overflow marker."""

    def test_render_key_symbols_table_format(self) -> None:
        """Three-symbol render output includes the markdown header and every row."""
        symbols = [
            KeySymbolSummary(
                name="foo",
                qualified_name="pkg.mymodule.foo",
                symbol_type="function",
                line_start=10,
                caller_count=2,
                callee_count=0,
            ),
            KeySymbolSummary(
                name="bar",
                qualified_name="pkg.mymodule.bar",
                symbol_type="function",
                line_start=25,
                caller_count=0,
                callee_count=3,
            ),
            KeySymbolSummary(
                name="run",
                qualified_name="pkg.mymodule.Runner.run",
                symbol_type="method",
                line_start=50,
                caller_count=1,
                callee_count=1,
            ),
        ]

        output = render_key_symbols(symbols, key_symbols_total=3)

        # Header + table columns present
        assert "### Key symbols" in output
        assert "| Symbol" in output
        assert "| Type" in output
        assert "| Line" in output
        assert "| Callers → Callees" in output

        # Each symbol row is present
        assert "foo" in output
        assert "bar" in output
        # Methods render as ``Class.method`` (the last two dotted segments).
        assert "Runner.run" in output

        # Count arrows rendered as ``callers → callees``
        assert "2 → 0" in output
        assert "0 → 3" in output
        assert "1 → 1" in output

        # Line numbers surfaced as plain strings
        assert " 10 " in output or "| 10" in output or " 10\n" in output
        assert "25" in output
        assert "50" in output

        # No overflow marker when displayed count == total.
        assert "more" not in output

    def test_render_key_symbols_overflow_marker(self) -> None:
        """Ten rendered entries with a total of fifteen appends '… and 5 more'."""
        symbols = [
            KeySymbolSummary(
                name=f"sym{i}",
                qualified_name=f"pkg.mymodule.sym{i}",
                symbol_type="function",
                line_start=i,
                caller_count=0,
                callee_count=0,
            )
            for i in range(10)
        ]

        output = render_key_symbols(symbols, key_symbols_total=15)

        assert "### Key symbols" in output
        for i in range(10):
            assert f"sym{i}" in output
        # sym10..sym14 are the ones omitted — they are not in the render
        # output because only 10 rows were supplied.
        for i in range(10, 15):
            assert f"sym{i}" not in output
        assert "… and 5 more" in output

    def test_render_key_symbols_empty_returns_empty_string(self) -> None:
        """Empty key_symbols returns empty string so the CLI can omit the section."""
        assert render_key_symbols([], key_symbols_total=0) == ""

    def test_render_key_symbols_non_summary_objects_filtered(self) -> None:
        """Non-KeySymbolSummary objects are filtered (parallels render_siblings)."""
        assert render_key_symbols(["not a summary"], key_symbols_total=0) == ""


# ---------------------------------------------------------------------------
# 6 — Class hierarchy section (symbol-graph-3 Group 6)
# ---------------------------------------------------------------------------
#
# Exercise ``LookupResult.classes`` end to end against a real
# ``.lexibrary/symbols.db`` seeded via :func:`_seed_class_hierarchy_fixture`.
# The tests never mock ``SymbolQueryService`` because the "graceful
# degradation when the DB is missing" guarantee is part of the service
# contract.


class TestClassHierarchyEntryDataclass:
    """Covers the :class:`ClassHierarchyEntry` dataclass surface."""

    def test_construction_with_all_fields(self) -> None:
        """ClassHierarchyEntry exposes every spec-mandated field."""
        entry = ClassHierarchyEntry(
            class_name="Foo",
            bases=["Base"],
            unresolved_bases=["BaseModel"],
            subclass_count=2,
            method_count=5,
            line_start=10,
        )
        assert entry.class_name == "Foo"
        assert entry.bases == ["Base"]
        assert entry.unresolved_bases == ["BaseModel"]
        assert entry.subclass_count == 2
        assert entry.method_count == 5
        assert entry.line_start == 10

    def test_field_names(self) -> None:
        """The dataclass field names match the spec verbatim."""
        names = {f.name for f in dataclass_fields(ClassHierarchyEntry)}
        assert names == {
            "class_name",
            "bases",
            "unresolved_bases",
            "subclass_count",
            "method_count",
            "line_start",
        }


class TestBuildFileLookupClassHierarchy:
    """Exercise build_file_lookup()'s ``classes`` population."""

    def _patched_lookup(
        self,
        *,
        target: Path,
        project_root: Path,
        config: object,
        full: bool = False,
    ) -> LookupResult | None:
        """Run build_file_lookup with the ambient aindex / design patches.

        The class-hierarchy tests don't care about siblings, conventions,
        concepts, or issues — the patches here short-circuit those code
        paths so only the symbol-graph branch stays live.
        """
        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=None,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=Path("/nonexistent"),
            ),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            return build_file_lookup(target, project_root, config, full=full)

    def test_lookup_includes_class_hierarchy(self, tmp_path: Path) -> None:
        """A class with a resolved base in another file renders the base."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        _seed_class_hierarchy_fixture(
            project_root,
            files=[
                {
                    "path": "src/pkg/base.py",
                    "symbols": [
                        {
                            "name": "Base",
                            "qualified_name": "pkg.base.Base",
                            "symbol_type": "class",
                            "line_start": 1,
                            "line_end": 5,
                            "visibility": "public",
                        },
                    ],
                },
                {
                    "path": "src/pkg/derived.py",
                    "symbols": [
                        {
                            "name": "Derived",
                            "qualified_name": "pkg.derived.Derived",
                            "symbol_type": "class",
                            "line_start": 3,
                            "line_end": 12,
                            "visibility": "public",
                        },
                        {
                            "name": "greet",
                            "qualified_name": "pkg.derived.Derived.greet",
                            "symbol_type": "method",
                            "line_start": 5,
                            "line_end": 7,
                            "visibility": "public",
                            "parent_class": "Derived",
                        },
                        {
                            "name": "shout",
                            "qualified_name": "pkg.derived.Derived.shout",
                            "symbol_type": "method",
                            "line_start": 9,
                            "line_end": 11,
                            "visibility": "public",
                            "parent_class": "Derived",
                        },
                    ],
                },
            ],
            class_edges=[
                {
                    "source_name": "Derived",
                    "target_name": "Base",
                    "edge_type": "inherits",
                    "line": 3,
                },
            ],
        )

        config = _make_config()
        target = project_root / "src" / "pkg" / "derived.py"

        result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert len(result.classes) == 1
        entry = result.classes[0]
        assert entry.class_name == "Derived"
        assert entry.bases == ["Base"]
        assert entry.unresolved_bases == []
        assert entry.subclass_count == 0
        assert entry.method_count == 2
        assert entry.line_start == 3

    def test_lookup_class_hierarchy_missing_when_no_classes(self, tmp_path: Path) -> None:
        """A file with only functions populates an empty ``classes`` list."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        _seed_class_hierarchy_fixture(
            project_root,
            files=[
                {
                    "path": "src/pkg/mymodule.py",
                    "symbols": [
                        {
                            "name": "foo",
                            "qualified_name": "pkg.mymodule.foo",
                            "symbol_type": "function",
                            "line_start": 1,
                            "line_end": 5,
                            "visibility": "public",
                        },
                        {
                            "name": "bar",
                            "qualified_name": "pkg.mymodule.bar",
                            "symbol_type": "function",
                            "line_start": 7,
                            "line_end": 12,
                            "visibility": "public",
                        },
                    ],
                },
            ],
        )

        config = _make_config()
        target = project_root / "src" / "pkg" / "mymodule.py"

        result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert result.classes == []
        assert render_class_hierarchy(result.classes) == ""

    def test_lookup_class_hierarchy_subclass_count(self, tmp_path: Path) -> None:
        """A base class with two derived subclasses reports ``subclass_count == 2``."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        _seed_class_hierarchy_fixture(
            project_root,
            files=[
                {
                    "path": "src/pkg/base.py",
                    "symbols": [
                        {
                            "name": "Base",
                            "qualified_name": "pkg.base.Base",
                            "symbol_type": "class",
                            "line_start": 1,
                            "line_end": 5,
                            "visibility": "public",
                        },
                    ],
                },
                {
                    "path": "src/pkg/sub_one.py",
                    "symbols": [
                        {
                            "name": "SubOne",
                            "qualified_name": "pkg.sub_one.SubOne",
                            "symbol_type": "class",
                            "line_start": 1,
                            "line_end": 5,
                            "visibility": "public",
                        },
                    ],
                },
                {
                    "path": "src/pkg/sub_two.py",
                    "symbols": [
                        {
                            "name": "SubTwo",
                            "qualified_name": "pkg.sub_two.SubTwo",
                            "symbol_type": "class",
                            "line_start": 1,
                            "line_end": 5,
                            "visibility": "public",
                        },
                    ],
                },
            ],
            class_edges=[
                {
                    "source_name": "SubOne",
                    "target_name": "Base",
                    "edge_type": "inherits",
                    "line": 1,
                },
                {
                    "source_name": "SubTwo",
                    "target_name": "Base",
                    "edge_type": "inherits",
                    "line": 1,
                },
            ],
        )

        config = _make_config()
        target = project_root / "src" / "pkg" / "base.py"

        result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert len(result.classes) == 1
        entry = result.classes[0]
        assert entry.class_name == "Base"
        assert entry.bases == []
        assert entry.unresolved_bases == []
        assert entry.subclass_count == 2
        assert entry.method_count == 0

    def test_lookup_class_hierarchy_unresolved_bases(self, tmp_path: Path) -> None:
        """External bases (``BaseModel``) appear in ``unresolved_bases``."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        _seed_class_hierarchy_fixture(
            project_root,
            files=[
                {
                    "path": "src/pkg/models.py",
                    "symbols": [
                        {
                            "name": "Thing",
                            "qualified_name": "pkg.models.Thing",
                            "symbol_type": "class",
                            "line_start": 1,
                            "line_end": 3,
                            "visibility": "public",
                        },
                    ],
                },
            ],
            unresolved_edges=[
                {
                    "source_name": "Thing",
                    "target_name": "BaseModel",
                    "edge_type": "inherits",
                    "line": 1,
                },
                {
                    "source_name": "Thing",
                    "target_name": "Enum",
                    "edge_type": "inherits",
                    "line": 1,
                },
            ],
        )

        config = _make_config()
        target = project_root / "src" / "pkg" / "models.py"

        result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert len(result.classes) == 1
        entry = result.classes[0]
        assert entry.class_name == "Thing"
        assert entry.bases == []
        assert entry.unresolved_bases == ["BaseModel", "Enum"]
        assert entry.subclass_count == 0

    def test_lookup_class_hierarchy_skipped_when_db_missing(self, tmp_path: Path) -> None:
        """Missing symbols.db ⇒ ``classes`` is ``[]`` without raising."""
        project_root = _setup_minimal_project(tmp_path)
        _make_linkgraph_db(project_root)

        # Deliberately do NOT seed a symbols.db — ``build_file_lookup``
        # must degrade gracefully and return an empty ``classes`` list.

        config = _make_config()
        target = project_root / "src" / "pkg" / "mymodule.py"

        result = self._patched_lookup(target=target, project_root=project_root, config=config)

        assert result is not None
        assert result.classes == []


class TestRenderClassHierarchy:
    """Covers ``render_class_hierarchy()`` format + edge cases."""

    def test_empty_returns_empty_string(self) -> None:
        """Empty ``classes`` returns an empty string so the CLI can omit it."""
        assert render_class_hierarchy([]) == ""

    def test_non_entry_objects_filtered(self) -> None:
        """Non-ClassHierarchyEntry objects are filtered (parallels render_key_symbols)."""
        assert render_class_hierarchy(["not an entry"]) == ""

    def test_render_single_row_with_resolved_base(self) -> None:
        """A class with a resolved base renders the base in the ``Bases`` column."""
        entries = [
            ClassHierarchyEntry(
                class_name="Derived",
                bases=["Base"],
                unresolved_bases=[],
                subclass_count=0,
                method_count=2,
                line_start=3,
            )
        ]
        output = render_class_hierarchy(entries)

        assert "### Class hierarchy" in output
        assert "| Class" in output
        assert "| Bases" in output
        assert "| Subclasses" in output
        assert "| Methods" in output
        assert "| Line" in output
        assert "Derived" in output
        assert "Base" in output
        # No unresolved marker
        assert "*" not in output.split("### Class hierarchy", 1)[1].split("\n| Class")[0]

    def test_render_unresolved_bases_get_star_marker(self) -> None:
        """Unresolved bases are rendered with a trailing ``*``."""
        entries = [
            ClassHierarchyEntry(
                class_name="Thing",
                bases=[],
                unresolved_bases=["BaseModel", "Enum"],
                subclass_count=0,
                method_count=0,
                line_start=1,
            )
        ]
        output = render_class_hierarchy(entries)

        assert "### Class hierarchy" in output
        assert "BaseModel*" in output
        assert "Enum*" in output

    def test_render_mixed_resolved_and_unresolved_bases(self) -> None:
        """Resolved bases come first, then unresolved bases with ``*`` marker."""
        entries = [
            ClassHierarchyEntry(
                class_name="Hybrid",
                bases=["Animal"],
                unresolved_bases=["Serializable"],
                subclass_count=0,
                method_count=0,
                line_start=2,
            )
        ]
        output = render_class_hierarchy(entries)

        assert "Animal" in output
        assert "Serializable*" in output
        # Resolved base comes before the unresolved one
        assert output.index("Animal") < output.index("Serializable*")

    def test_render_dash_when_no_bases(self) -> None:
        """A class with zero bases renders ``—`` in the ``Bases`` column."""
        entries = [
            ClassHierarchyEntry(
                class_name="Root",
                bases=[],
                unresolved_bases=[],
                subclass_count=3,
                method_count=1,
                line_start=5,
            )
        ]
        output = render_class_hierarchy(entries)

        assert "Root" in output
        assert "—" in output

    def test_render_multiple_rows(self) -> None:
        """Every entry appears as its own row."""
        entries = [
            ClassHierarchyEntry(
                class_name="Foo",
                bases=[],
                unresolved_bases=[],
                subclass_count=0,
                method_count=0,
                line_start=1,
            ),
            ClassHierarchyEntry(
                class_name="Bar",
                bases=["Foo"],
                unresolved_bases=[],
                subclass_count=0,
                method_count=0,
                line_start=10,
            ),
            ClassHierarchyEntry(
                class_name="Baz",
                bases=["Bar"],
                unresolved_bases=["BaseModel"],
                subclass_count=0,
                method_count=0,
                line_start=20,
            ),
        ]
        output = render_class_hierarchy(entries)

        assert "Foo" in output
        assert "Bar" in output
        assert "Baz" in output
        assert "BaseModel*" in output


# ---------------------------------------------------------------------------
# 7 — Lookup rendering for enrichment sections (symbol-graph-5 Group 7)
# ---------------------------------------------------------------------------
#
# These tests cover the new ``### Enums & constants`` and ``### Call paths``
# sections that ``lexi lookup`` surfaces from the parsed design file.  The
# direct ``render_*`` tests parallel ``TestRenderKeySymbols`` and
# ``TestRenderClassHierarchy``, while ``TestLookupRendersEnrichment`` exercises
# the end-to-end population path through ``build_file_lookup``.


class TestRenderEnumNotes:
    """Covers ``render_enum_notes()`` format + edge cases."""

    def test_empty_returns_empty_string(self) -> None:
        """Empty list yields an empty string so the CLI can omit the section."""
        assert render_enum_notes([]) == ""

    def test_non_enum_note_objects_filtered(self) -> None:
        """Non-EnumNote items are filtered (parallels render_key_symbols)."""
        assert render_enum_notes(["not a note"]) == ""

    def test_render_single_note_with_values(self) -> None:
        """A note with values renders the bullet plus an indented Values line."""
        from lexibrary.artifacts.design_file import EnumNote  # noqa: PLC0415

        notes = [
            EnumNote(
                name="BuildStatus",
                role="Tracks pipeline execution state.",
                values=["PENDING", "RUNNING", "SUCCESS"],
            )
        ]
        output = render_enum_notes(notes)

        assert "### Enums & constants" in output
        assert "- **BuildStatus** — Tracks pipeline execution state." in output
        assert "  Values: PENDING, RUNNING, SUCCESS" in output

    def test_render_note_without_values_omits_values_line(self) -> None:
        """A note with no values omits the indented continuation line."""
        from lexibrary.artifacts.design_file import EnumNote  # noqa: PLC0415

        notes = [
            EnumNote(name="MAX_RETRIES", role="Cap on retry attempts.", values=[]),
        ]
        output = render_enum_notes(notes)

        assert "### Enums & constants" in output
        assert "- **MAX_RETRIES** — Cap on retry attempts." in output
        assert "Values:" not in output

    def test_render_multiple_notes(self) -> None:
        """Every note appears in the output in order."""
        from lexibrary.artifacts.design_file import EnumNote  # noqa: PLC0415

        notes = [
            EnumNote(name="Color", role="UI palette key.", values=["RED", "BLUE"]),
            EnumNote(name="Mode", role="Run mode.", values=["FAST", "SAFE"]),
            EnumNote(name="LIMIT", role="Cap.", values=[]),
        ]
        output = render_enum_notes(notes)

        assert "Color" in output
        assert "Mode" in output
        assert "LIMIT" in output
        assert output.index("Color") < output.index("Mode") < output.index("LIMIT")
        assert "  Values: RED, BLUE" in output
        assert "  Values: FAST, SAFE" in output


class TestRenderCallPathNotes:
    """Covers ``render_call_path_notes()`` format + edge cases."""

    def test_empty_returns_empty_string(self) -> None:
        """Empty list yields an empty string so the CLI can omit the section."""
        assert render_call_path_notes([]) == ""

    def test_non_call_path_note_objects_filtered(self) -> None:
        """Non-CallPathNote items are filtered (parallels render_key_symbols)."""
        assert render_call_path_notes(["not a note"]) == ""

    def test_render_single_note_with_key_hops(self) -> None:
        """A note with key_hops renders the bullet plus the indented Key hops line."""
        from lexibrary.artifacts.design_file import CallPathNote  # noqa: PLC0415

        notes = [
            CallPathNote(
                entry="update_project()",
                narrative=(
                    "Orchestrates a full project build: discovers source files, "
                    "regenerates changed design files, refreshes aindexes, rebuilds "
                    "the link graph, then the symbol graph."
                ),
                key_hops=[
                    "discover_source_files",
                    "update_file",
                    "build_index",
                    "build_symbol_graph",
                ],
            )
        ]
        output = render_call_path_notes(notes)

        assert "### Call paths" in output
        assert "- **update_project()** — Orchestrates a full project build" in output
        assert (
            "  Key hops: discover_source_files, update_file, build_index, build_symbol_graph"
        ) in output

    def test_render_note_without_key_hops_omits_hops_line(self) -> None:
        """A note with no key_hops omits the indented continuation line."""
        from lexibrary.artifacts.design_file import CallPathNote  # noqa: PLC0415

        notes = [
            CallPathNote(entry="seed()", narrative="Seeds the database.", key_hops=[]),
        ]
        output = render_call_path_notes(notes)

        assert "### Call paths" in output
        assert "- **seed()** — Seeds the database." in output
        assert "Key hops:" not in output

    def test_render_multiple_notes(self) -> None:
        """Every note appears in the output in order."""
        from lexibrary.artifacts.design_file import CallPathNote  # noqa: PLC0415

        notes = [
            CallPathNote(entry="alpha()", narrative="First.", key_hops=["a"]),
            CallPathNote(entry="beta()", narrative="Second.", key_hops=["b"]),
        ]
        output = render_call_path_notes(notes)

        assert "alpha()" in output
        assert "beta()" in output
        assert output.index("alpha()") < output.index("beta()")


class TestLookupRendersEnrichment:
    """End-to-end tests covering the enrichment surface in build_file_lookup.

    These tests verify that the parsed design file's enum_notes and
    call_path_notes flow through to the resulting LookupResult and that
    rendering through render_enum_notes / render_call_path_notes yields the
    expected sections (or remains empty when enrichment is absent).
    """

    def _build_design_file(
        self,
        *,
        enum_notes: list[object] | None = None,
        call_path_notes: list[object] | None = None,
    ) -> object:
        """Construct a minimal DesignFile that build_file_lookup can consume."""
        from lexibrary.artifacts.design_file import (  # noqa: PLC0415
            DesignFile,
            DesignFileFrontmatter,
            StalenessMetadata,
        )

        return DesignFile(
            source_path="src/pkg/mymodule.py",
            frontmatter=DesignFileFrontmatter(
                description="A module",
                id="design-mymodule",
            ),
            summary="Test module summary.",
            interface_contract="No public contract.",
            dependencies=[],
            dependents=[],
            tests=None,
            complexity_warning=None,
            enum_notes=enum_notes or [],  # type: ignore[arg-type]
            call_path_notes=call_path_notes or [],  # type: ignore[arg-type]
            wikilinks=[],
            tags=[],
            stack_refs=[],
            preserved_sections={},
            metadata=StalenessMetadata(
                source="src/pkg/mymodule.py",
                source_hash="abc123",
                generated=datetime(2026, 1, 1),
                generator="test",
            ),
        )

    def _run_build_file_lookup(
        self,
        tmp_path: Path,
        design_file: object,
    ) -> LookupResult | None:
        """Invoke build_file_lookup with the supplied design file mocked in."""
        project_root = _setup_minimal_project(tmp_path)
        target = project_root / "src" / "pkg" / "mymodule.py"
        # Use a real design path so design_path.exists() returns True.
        design_path = project_root / ".lexibrary" / "designs" / "src" / "pkg" / "mymodule.py.md"
        design_path.parent.mkdir(parents=True, exist_ok=True)
        design_path.write_text("placeholder", encoding="utf-8")

        config = _make_config()

        with (
            patch("lexibrary.artifacts.aindex_parser.parse_aindex", return_value=None),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_frontmatter",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file_metadata",
                return_value=None,
            ),
            patch(
                "lexibrary.artifacts.design_file_parser.parse_design_file",
                return_value=design_file,
            ),
            patch(
                "lexibrary.utils.paths.mirror_path",
                return_value=design_path,
            ),
            patch("lexibrary.linkgraph.query.open_index", return_value=None),
            patch("lexibrary.services.lookup._build_iwh_peek", return_value=""),
        ):
            return build_file_lookup(target, project_root, config)

    def test_lookup_renders_enum_notes(self, tmp_path: Path) -> None:
        """build_file_lookup populates enum_notes; renderer emits the section."""
        from lexibrary.artifacts.design_file import EnumNote  # noqa: PLC0415

        design_file = self._build_design_file(
            enum_notes=[
                EnumNote(
                    name="BuildStatus",
                    role="Tracks pipeline execution state.",
                    values=["PENDING", "RUNNING", "SUCCESS"],
                )
            ]
        )

        result = self._run_build_file_lookup(tmp_path, design_file)

        assert result is not None
        assert len(result.enum_notes) == 1
        assert result.enum_notes[0].name == "BuildStatus"

        output = render_enum_notes(result.enum_notes)
        assert "### Enums & constants" in output
        assert "BuildStatus" in output
        assert "Values: PENDING, RUNNING, SUCCESS" in output

    def test_lookup_renders_call_paths(self, tmp_path: Path) -> None:
        """build_file_lookup populates call_path_notes; renderer emits the section."""
        from lexibrary.artifacts.design_file import CallPathNote  # noqa: PLC0415

        design_file = self._build_design_file(
            call_path_notes=[
                CallPathNote(
                    entry="update_project()",
                    narrative="Orchestrates a full project build.",
                    key_hops=["discover_source_files", "update_file"],
                )
            ]
        )

        result = self._run_build_file_lookup(tmp_path, design_file)

        assert result is not None
        assert len(result.call_path_notes) == 1
        assert result.call_path_notes[0].entry == "update_project()"

        output = render_call_path_notes(result.call_path_notes)
        assert "### Call paths" in output
        assert "update_project()" in output
        assert "Key hops: discover_source_files, update_file" in output

    def test_lookup_skips_enrichment_sections_when_empty(self, tmp_path: Path) -> None:
        """Empty enum_notes / call_path_notes yield empty rendered output."""
        design_file = self._build_design_file(enum_notes=[], call_path_notes=[])

        result = self._run_build_file_lookup(tmp_path, design_file)

        assert result is not None
        assert result.enum_notes == []
        assert result.call_path_notes == []

        # Renderer returns empty string so the CLI omits both headings.
        assert render_enum_notes(result.enum_notes) == ""
        assert render_call_path_notes(result.call_path_notes) == ""


# ---------------------------------------------------------------------------
# Data flow notes rendering (symbol-graph-7)
# ---------------------------------------------------------------------------


class TestRenderDataFlowNotes:
    """Covers ``render_data_flow_notes()`` format + edge cases."""

    def test_lookup_renders_data_flows(self) -> None:
        """Non-empty data_flow_notes render a ``### Data flows`` section."""
        from lexibrary.artifacts.design_file import DataFlowNote  # noqa: PLC0415

        notes = [
            DataFlowNote(
                parameter="changed_paths",
                location="build_index()",
                effect=(
                    "`None` triggers a full build; a non-None list triggers incremental update."
                ),
            ),
            DataFlowNote(
                parameter="config",
                location="render()",
                effect="Controls output format and verbosity.",
            ),
        ]
        output = render_data_flow_notes(notes)

        assert "### Data flows" in output
        assert (
            "- **changed_paths** in **build_index()** \u2014 `None` triggers a full build"
        ) in output
        assert "- **config** in **render()** \u2014 Controls output format" in output
        # Verify ordering matches input
        assert output.index("changed_paths") < output.index("config")

    def test_lookup_skips_data_flows_when_empty(self) -> None:
        """Empty data_flow_notes yield an empty string so the CLI omits it."""
        assert render_data_flow_notes([]) == ""

    def test_non_data_flow_note_objects_filtered(self) -> None:
        """Non-DataFlowNote items are filtered out defensively."""
        assert render_data_flow_notes(["not a note"]) == ""

    def test_render_single_data_flow_note(self) -> None:
        """A single note renders correctly with heading and bullet."""
        from lexibrary.artifacts.design_file import DataFlowNote  # noqa: PLC0415

        notes = [
            DataFlowNote(
                parameter="mode",
                location="process()",
                effect="Selects processing strategy.",
            ),
        ]
        output = render_data_flow_notes(notes)

        assert "### Data flows" in output
        assert "- **mode** in **process()** \u2014 Selects processing strategy." in output
