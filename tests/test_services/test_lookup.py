"""Tests for lexibrary.services.lookup — lookup service module."""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from lexibrary.services.lookup import (
    ConceptSummary,
    DirectoryLookupResult,
    LookupResult,
    SiblingSummary,
    build_directory_lookup,
    build_file_lookup,
    estimate_tokens,
    truncate_lookup_sections,
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
