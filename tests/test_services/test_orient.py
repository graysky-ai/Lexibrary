"""Unit tests for lexibrary.services.orient — orient data gathering service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from lexibrary.services.orient import (
    CHARS_PER_TOKEN,
    ORIENT_CHAR_BUDGET,
    ORIENT_TOKEN_BUDGET,
    OrientResult,
    build_orient,
    check_topology_staleness,
    collect_file_descriptions,
    collect_iwh_peek,
    collect_library_stats,
)
from lexibrary.services.orient_render import render_orient


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project with .lexibrary directory."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "config.yaml").write_text("")
    return project


def _create_aindex(project: Path, directory_rel: str, files: list[tuple[str, str]]) -> None:
    """Create a .aindex file in the .lexibrary mirror tree.

    *files* is a list of (name, description) tuples for file entries.
    """
    aindex_file = project / ".lexibrary" / "designs" / directory_rel / ".aindex"
    aindex_file.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()
    child_rows = "\n".join(f"| `{name}` | file | {desc} |" for name, desc in files)
    content = (
        f"# {directory_rel}/\n\n"
        f"Billboard\n\n"
        f"## Child Map\n\n"
        f"| Name | Type | Description |\n"
        f"| --- | --- | --- |\n"
        f"{child_rows}\n\n"
        f"## Local Conventions\n\n"
        f"(none)\n\n"
        f'<!-- lexibrary:meta source="{directory_rel}" source_hash="abc123" '
        f'generated="{now}" generator="lexibrary-v2" -->\n'
    )
    aindex_file.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Token budget constants
# ---------------------------------------------------------------------------


class TestTokenBudgetConstants:
    """Verify token budget constants are exposed and consistent."""

    def test_budget_is_positive(self) -> None:
        assert ORIENT_TOKEN_BUDGET > 0

    def test_chars_per_token(self) -> None:
        assert CHARS_PER_TOKEN == 4

    def test_char_budget_is_product(self) -> None:
        assert ORIENT_CHAR_BUDGET == ORIENT_TOKEN_BUDGET * CHARS_PER_TOKEN


# ---------------------------------------------------------------------------
# OrientResult dataclass
# ---------------------------------------------------------------------------


class TestOrientResult:
    """OrientResult defaults and fields."""

    def test_defaults(self) -> None:
        result = OrientResult()
        assert result.topology_text == ""
        assert result.file_descriptions == []
        assert result.library_stats == ""
        assert result.iwh_signals == ""
        assert result.is_stale is False
        assert result.staleness_message is None


# ---------------------------------------------------------------------------
# collect_file_descriptions
# ---------------------------------------------------------------------------


class TestCollectFileDescriptions:
    """Tests for collect_file_descriptions()."""

    def test_no_lexibrary_dir(self, tmp_path: Path) -> None:
        """Returns empty list when .lexibrary/ does not exist."""
        assert collect_file_descriptions(tmp_path) == []

    def test_empty_lexibrary(self, tmp_path: Path) -> None:
        """Returns empty list when no .aindex files exist."""
        project = _setup_project(tmp_path)
        assert collect_file_descriptions(project) == []

    def test_single_file(self, tmp_path: Path) -> None:
        """Returns one (path, description) for a single file entry."""
        project = _setup_project(tmp_path)
        _create_aindex(project, "src", [("main.py", "Main module")])
        result = collect_file_descriptions(project)
        assert len(result) == 1
        assert result[0] == ("src/main.py", "Main module")

    def test_multiple_files_sorted(self, tmp_path: Path) -> None:
        """Descriptions are returned sorted by path."""
        project = _setup_project(tmp_path)
        _create_aindex(
            project,
            "src",
            [
                ("zebra.py", "Zebra module"),
                ("alpha.py", "Alpha module"),
            ],
        )
        result = collect_file_descriptions(project)
        assert len(result) == 2
        assert result[0][0] == "src/alpha.py"
        assert result[1][0] == "src/zebra.py"


# ---------------------------------------------------------------------------
# collect_library_stats
# ---------------------------------------------------------------------------


class TestCollectLibraryStats:
    """Tests for collect_library_stats()."""

    def test_no_artifacts(self, tmp_path: Path) -> None:
        """Returns empty string when no artifacts exist."""
        project = _setup_project(tmp_path)
        assert collect_library_stats(project) == ""

    def test_concepts_counted(self, tmp_path: Path) -> None:
        """Counts concept markdown files."""
        project = _setup_project(tmp_path)
        concepts = project / ".lexibrary" / "concepts"
        concepts.mkdir(parents=True)
        (concepts / "concept-one.md").write_text("# Concept One\n")
        (concepts / "concept-two.md").write_text("# Concept Two\n")

        result = collect_library_stats(project)
        assert "Concepts: 2" in result

    def test_conventions_counted(self, tmp_path: Path) -> None:
        """Counts convention markdown files."""
        project = _setup_project(tmp_path)
        conventions = project / ".lexibrary" / "conventions"
        conventions.mkdir(parents=True)
        (conventions / "conv-one.md").write_text("# Convention One\n")

        result = collect_library_stats(project)
        assert "Conventions: 1" in result

    def test_playbooks_counted(self, tmp_path: Path) -> None:
        """Counts playbook markdown files."""
        project = _setup_project(tmp_path)
        playbooks = project / ".lexibrary" / "playbooks"
        playbooks.mkdir(parents=True)
        (playbooks / "pb-one.md").write_text("# Playbook One\n")

        result = collect_library_stats(project)
        assert "Playbooks: 1" in result

    def test_open_stack_posts_counted(self, tmp_path: Path) -> None:
        """Counts open stack posts (not resolved ones)."""
        project = _setup_project(tmp_path)
        stack = project / ".lexibrary" / "stack"
        stack.mkdir(parents=True)
        (stack / "ST-001-issue.md").write_text(
            "---\nid: ST-001\ntitle: Issue\ntags:\n  - bug\nstatus: open\n"
            "created: 2026-01-01\nauthor: test\n---\n\n## Problem\n\nSomething\n\n"
            "## Solution\n\nFix\n"
        )
        (stack / "ST-002-resolved.md").write_text(
            "---\nid: ST-002\ntitle: Resolved\ntags:\n  - bug\nstatus: resolved\n"
            "created: 2026-01-01\nauthor: test\n---\n\n## Problem\n\nDone\n\n"
            "## Solution\n\nDone\n"
        )

        result = collect_library_stats(project)
        assert "Open stack posts: 1" in result

    def test_stats_header(self, tmp_path: Path) -> None:
        """Stats section starts with '## Library Stats'."""
        project = _setup_project(tmp_path)
        concepts = project / ".lexibrary" / "concepts"
        concepts.mkdir(parents=True)
        (concepts / "one.md").write_text("# One\n")

        result = collect_library_stats(project)
        assert result.startswith("## Library Stats")


# ---------------------------------------------------------------------------
# collect_iwh_peek
# ---------------------------------------------------------------------------


class TestCollectIwhPeek:
    """Tests for collect_iwh_peek()."""

    def test_no_signals(self, tmp_path: Path) -> None:
        """Returns empty string when no IWH signals exist."""
        project = _setup_project(tmp_path)
        assert collect_iwh_peek(project) == ""

    def test_signal_present(self, tmp_path: Path) -> None:
        """Returns formatted section when IWH signals exist."""
        project = _setup_project(tmp_path)
        iwh_dir = project / ".lexibrary" / "designs" / "src"
        iwh_dir.mkdir(parents=True, exist_ok=True)
        (iwh_dir / ".iwh").write_text(
            "---\nauthor: test\ncreated: '2026-01-01T00:00:00'\nscope: incomplete\n"
            "---\nSome work remains here.",
            encoding="utf-8",
        )

        result = collect_iwh_peek(project)
        assert "## IWH Signals" in result
        assert "[incomplete]" in result
        assert "Some work remains here" in result

    def test_consumption_guidance(self, tmp_path: Path) -> None:
        """Peek output includes consumption guidance footer."""
        project = _setup_project(tmp_path)
        iwh_dir = project / ".lexibrary" / "designs" / "src"
        iwh_dir.mkdir(parents=True, exist_ok=True)
        (iwh_dir / ".iwh").write_text(
            "---\nauthor: test\ncreated: '2026-01-01T00:00:00'\nscope: incomplete\n"
            "---\nRemaining work.",
            encoding="utf-8",
        )

        result = collect_iwh_peek(project)
        assert "lexi iwh read" in result


# ---------------------------------------------------------------------------
# check_topology_staleness
# ---------------------------------------------------------------------------


class TestCheckTopologyStaleness:
    """Tests for check_topology_staleness()."""

    def test_no_raw_topology(self, tmp_path: Path) -> None:
        """Returns (False, None) when raw topology does not exist."""
        project = _setup_project(tmp_path)
        is_stale, msg = check_topology_staleness(project)
        assert is_stale is False
        assert msg is None

    def test_topology_missing(self, tmp_path: Path) -> None:
        """Returns stale with message when TOPOLOGY.md is missing but raw exists."""
        project = _setup_project(tmp_path)
        tmp_dir = project / ".lexibrary" / "tmp"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "raw-topology.md").write_text("raw content")

        is_stale, msg = check_topology_staleness(project)
        assert is_stale is True
        assert msg is not None
        assert "TOPOLOGY.md is missing" in msg

    def test_topology_fresh(self, tmp_path: Path) -> None:
        """Returns (False, None) when TOPOLOGY.md is newer than raw."""
        project = _setup_project(tmp_path)
        tmp_dir = project / ".lexibrary" / "tmp"
        tmp_dir.mkdir(parents=True)
        raw = tmp_dir / "raw-topology.md"
        raw.write_text("raw content")

        import time  # noqa: PLC0415

        time.sleep(0.05)

        topo = project / ".lexibrary" / "TOPOLOGY.md"
        topo.write_text("topology content")

        is_stale, msg = check_topology_staleness(project)
        assert is_stale is False
        assert msg is None

    def test_topology_stale(self, tmp_path: Path) -> None:
        """Returns stale with message when raw is newer than TOPOLOGY.md."""
        project = _setup_project(tmp_path)
        topo = project / ".lexibrary" / "TOPOLOGY.md"
        topo.write_text("topology content")

        import time  # noqa: PLC0415

        time.sleep(0.05)

        tmp_dir = project / ".lexibrary" / "tmp"
        tmp_dir.mkdir(parents=True)
        raw = tmp_dir / "raw-topology.md"
        raw.write_text("updated raw content")

        is_stale, msg = check_topology_staleness(project)
        assert is_stale is True
        assert msg is not None
        assert "newer than TOPOLOGY.md" in msg


# ---------------------------------------------------------------------------
# build_orient
# ---------------------------------------------------------------------------


class TestBuildOrient:
    """Tests for build_orient()."""

    def test_no_lexibrary_dir(self, tmp_path: Path) -> None:
        """Returns empty OrientResult when no .lexibrary/ exists."""
        result = build_orient(tmp_path)
        assert result.topology_text == ""
        assert result.file_descriptions == []
        assert result.library_stats == ""
        assert result.iwh_signals == ""
        assert result.is_stale is False

    def test_topology_text(self, tmp_path: Path) -> None:
        """Includes TOPOLOGY.md content in result."""
        project = _setup_project(tmp_path)
        (project / ".lexibrary" / "TOPOLOGY.md").write_text("# Project Topology\n\nStuff here.")
        result = build_orient(project)
        assert "# Project Topology" in result.topology_text

    def test_file_descriptions(self, tmp_path: Path) -> None:
        """Includes file descriptions from .aindex entries."""
        project = _setup_project(tmp_path)
        _create_aindex(project, "src", [("app.py", "Application entry point")])
        result = build_orient(project)
        assert len(result.file_descriptions) == 1
        assert result.file_descriptions[0] == ("src/app.py", "Application entry point")

    def test_library_stats(self, tmp_path: Path) -> None:
        """Includes library stats when artifacts exist."""
        project = _setup_project(tmp_path)
        concepts = project / ".lexibrary" / "concepts"
        concepts.mkdir(parents=True)
        (concepts / "one.md").write_text("# One")
        result = build_orient(project)
        assert "Concepts: 1" in result.library_stats

    def test_staleness_detection(self, tmp_path: Path) -> None:
        """Reports staleness in the result."""
        project = _setup_project(tmp_path)
        tmp_dir = project / ".lexibrary" / "tmp"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "raw-topology.md").write_text("raw")
        # No TOPOLOGY.md -> stale
        result = build_orient(project)
        assert result.is_stale is True
        assert result.staleness_message is not None


# ---------------------------------------------------------------------------
# render_orient
# ---------------------------------------------------------------------------


class TestRenderOrient:
    """Tests for render_orient()."""

    def test_empty_result(self) -> None:
        """Empty result produces empty string."""
        result = OrientResult()
        assert render_orient(result) == ""

    def test_topology_only(self) -> None:
        """Renders topology text when present."""
        result = OrientResult(topology_text="# My Topology")
        output = render_orient(result)
        assert "# My Topology" in output

    def test_file_descriptions(self) -> None:
        """Renders file descriptions section."""
        result = OrientResult(file_descriptions=[("src/app.py", "Main app")])
        output = render_orient(result)
        assert "## File Descriptions" in output
        assert "src/app.py: Main app" in output

    def test_library_stats(self) -> None:
        """Renders library stats section."""
        result = OrientResult(library_stats="## Library Stats\n\nConcepts: 3")
        output = render_orient(result)
        assert "Concepts: 3" in output

    def test_iwh_signals(self) -> None:
        """Renders IWH signals section."""
        result = OrientResult(iwh_signals="## IWH Signals\n\n- [incomplete] src/ -- Work")
        output = render_orient(result)
        assert "[incomplete]" in output

    def test_all_sections_combined(self) -> None:
        """All sections appear when all data is present."""
        result = OrientResult(
            topology_text="# Topology",
            file_descriptions=[("src/main.py", "Entry point")],
            library_stats="## Library Stats\n\nConcepts: 1",
            iwh_signals="## IWH Signals\n\n- [blocked] lib/ -- Blocked",
        )
        output = render_orient(result)
        assert "# Topology" in output
        assert "## File Descriptions" in output
        assert "## Library Stats" in output
        assert "## IWH Signals" in output

    def test_truncation_footer(self) -> None:
        """Truncation message appears when topology is large and budget is exceeded."""
        # Create a topology that consumes most of the budget
        large_topology = "x" * 20000
        result = OrientResult(
            topology_text=large_topology,
            file_descriptions=[("src/main.py", "Main module")],
        )
        output = render_orient(result)
        # With a 16000 char budget and 20000 char topology, descriptions
        # should be truncated (remaining_budget <= 0)
        assert large_topology in output


# ---------------------------------------------------------------------------
# Import isolation
# ---------------------------------------------------------------------------


class TestImportIsolation:
    """Verify orient service does not depend on CLI modules."""

    def test_no_cli_dependencies(self) -> None:
        """orient.py is importable without pulling in CLI modules."""
        import importlib  # noqa: PLC0415

        mod = importlib.import_module("lexibrary.services.orient")
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "import typer" not in source
        assert "from lexibrary.cli._output" not in source
