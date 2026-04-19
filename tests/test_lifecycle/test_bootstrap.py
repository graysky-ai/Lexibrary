"""Tests for the bootstrap lifecycle module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, patch

import pytest
from baml_py import ClientRegistry

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.skeleton import (
    _extract_module_docstring,
)
from lexibrary.archivist.skeleton import (
    heuristic_description as _heuristic_description,
)
from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import parse_design_file, parse_design_file_frontmatter
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig, ScopeRoot
from lexibrary.lifecycle.bootstrap import (
    BootstrapStats,
    _discover_source_files,
    _generate_quick_design,
    bootstrap_full,
    bootstrap_quick,
)
from lexibrary.utils.paths import mirror_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path, scope_root: str = ".") -> Path:
    """Create a minimal project structure with .lexibrary and config.

    Note: tests construct ``LexibraryConfig()`` in-memory rather than loading
    from YAML, so the on-disk ``config.yaml`` is just here for presence
    detection. The body uses the modern multi-root ``scope_roots`` shape so
    a stray ``load_config`` call would still succeed.
    """
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text(f"scope_roots:\n  - path: {scope_root}\n")
    return tmp_path


def _make_source_file(
    project: Path,
    rel: str,
    content: str = "print('hello')\n",
) -> Path:
    """Create a source file at the given relative path."""
    source = project / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _make_design_file(
    project_root: Path,
    source_rel: str,
    *,
    source_hash: str = "abc123",
    updated_by: Literal[
        "archivist", "agent", "bootstrap-quick", "skeleton-fallback", "maintainer"
    ] = "archivist",
) -> Path:
    """Create a minimal design file on disk and return its path."""
    design_path = mirror_path(project_root, Path(source_rel))
    design_path.parent.mkdir(parents=True, exist_ok=True)

    data = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id="DS-001",
            updated_by=updated_by,
        ),
        summary=f"Design for {source_rel}",
        interface_contract="",
        dependencies=[],
        dependents=[],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            generated=datetime.now(UTC).replace(tzinfo=None),
            generator="lexibrary-v2",
        ),
    )
    serialized = serialize_design_file(data)
    design_path.write_text(serialized, encoding="utf-8")
    return design_path


# ---------------------------------------------------------------------------
# _extract_module_docstring tests
# ---------------------------------------------------------------------------


class TestExtractModuleDocstring:
    """Tests for the _extract_module_docstring helper."""

    def test_extracts_docstring(self, tmp_path: Path) -> None:
        """Extracts the module-level docstring from a Python file."""
        source = _make_source_file(
            tmp_path,
            "mod.py",
            '"""This is a module docstring."""\n\nx = 1\n',
        )
        result = _extract_module_docstring(source)
        assert result == "This is a module docstring."

    def test_returns_none_for_no_docstring(self, tmp_path: Path) -> None:
        """Returns None when no module docstring is present."""
        source = _make_source_file(tmp_path, "mod.py", "x = 1\n")
        result = _extract_module_docstring(source)
        assert result is None

    def test_returns_none_for_non_python(self, tmp_path: Path) -> None:
        """Returns None for non-Python files."""
        source = _make_source_file(tmp_path, "mod.js", "const x = 1;\n")
        result = _extract_module_docstring(source)
        assert result is None

    def test_returns_none_for_syntax_error(self, tmp_path: Path) -> None:
        """Returns None when the file has a syntax error."""
        source = _make_source_file(tmp_path, "bad.py", "def (\n")
        result = _extract_module_docstring(source)
        assert result is None


# ---------------------------------------------------------------------------
# _heuristic_description tests
# ---------------------------------------------------------------------------


class TestHeuristicDescription:
    """Tests for the _heuristic_description helper."""

    def test_uses_docstring_first_line(self, tmp_path: Path) -> None:
        """Uses the first line of the module docstring as description."""
        source = _make_source_file(
            tmp_path,
            "mod.py",
            '"""Handles authentication logic.\n\nMore details here.\n"""\n',
        )
        result = _heuristic_description(source)
        assert result == "Handles authentication logic."

    def test_fallback_to_filename(self, tmp_path: Path) -> None:
        """Falls back to filename-derived description without docstring."""
        source = _make_source_file(tmp_path, "auth_handler.py", "x = 1\n")
        result = _heuristic_description(source)
        assert result == "Design file for auth handler"

    def test_init_file(self, tmp_path: Path) -> None:
        """Generates appropriate description for __init__.py."""
        source = _make_source_file(tmp_path, "pkg/__init__.py", "")
        result = _heuristic_description(source)
        assert "Package initializer" in result
        assert "pkg" in result

    def test_main_file(self, tmp_path: Path) -> None:
        """Generates appropriate description for __main__.py."""
        source = _make_source_file(tmp_path, "pkg/__main__.py", "")
        result = _heuristic_description(source)
        assert "Entry point" in result
        assert "pkg" in result


# ---------------------------------------------------------------------------
# _discover_source_files tests
# ---------------------------------------------------------------------------


class TestDiscoverSourceFiles:
    """Tests for the _discover_source_files helper."""

    def test_discovers_python_files(self, tmp_path: Path) -> None:
        """Discovers Python files in scope directory."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py")
        _make_source_file(project, "src/b.py")

        config = LexibraryConfig()
        scope_dir = (project / ".").resolve()

        files = _discover_source_files(scope_dir, project, config)
        names = {f.name for f in files}
        assert "a.py" in names
        assert "b.py" in names

    def test_skips_binary_files(self, tmp_path: Path) -> None:
        """Skips files with binary extensions."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py")
        _make_source_file(project, "src/image.png", "binary data")

        config = LexibraryConfig()
        scope_dir = (project / ".").resolve()

        files = _discover_source_files(scope_dir, project, config)
        names = {f.name for f in files}
        assert "a.py" in names
        assert "image.png" not in names

    def test_skips_lexibrary_dir(self, tmp_path: Path) -> None:
        """Skips files inside .lexibrary/."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py")
        (project / ".lexibrary" / "test.py").write_text("x = 1\n")

        config = LexibraryConfig()
        scope_dir = (project / ".").resolve()

        files = _discover_source_files(scope_dir, project, config)
        paths_str = [str(f) for f in files]
        assert not any(".lexibrary" in p for p in paths_str)


# ---------------------------------------------------------------------------
# _generate_quick_design tests
# ---------------------------------------------------------------------------


class TestGenerateQuickDesign:
    """Tests for the _generate_quick_design function."""

    def test_creates_new_design_file(self, tmp_path: Path) -> None:
        """Creates a design file for a source file without one."""
        project = _setup_project(tmp_path)
        source = _make_source_file(
            project,
            "src/mod.py",
            '"""Module docstring."""\n\ndef hello():\n    pass\n',
        )

        result = _generate_quick_design(source, project)

        assert result.change == ChangeLevel.NEW_FILE
        design_path = mirror_path(project, source)
        assert design_path.exists()

        # Check frontmatter
        frontmatter = parse_design_file_frontmatter(design_path)
        assert frontmatter is not None
        assert frontmatter.updated_by == "bootstrap-quick"
        assert frontmatter.status == "active"

    def test_skips_unchanged_file(self, tmp_path: Path) -> None:
        """Skips files with up-to-date design files."""
        project = _setup_project(tmp_path)
        source = _make_source_file(project, "src/mod.py", "x = 1\n")

        # First generation
        result1 = _generate_quick_design(source, project)
        assert result1.change == ChangeLevel.NEW_FILE

        # Second generation should be unchanged
        result2 = _generate_quick_design(source, project)
        assert result2.change == ChangeLevel.UNCHANGED

    def test_preserves_agent_updated_files(self, tmp_path: Path) -> None:
        """Does not overwrite agent-updated design files."""
        project = _setup_project(tmp_path)
        source = _make_source_file(project, "src/mod.py", "x = 1\n")

        # Create a design file first
        _generate_quick_design(source, project)

        # Simulate agent editing the design file (modify body without
        # matching the footer hash -- we'll just rewrite the whole file)
        design_path = mirror_path(project, source)
        content = design_path.read_text(encoding="utf-8")
        modified = content.replace(
            "## Interface Contract",
            "## Interface Contract\n\nAgent notes here.",
        )
        design_path.write_text(modified, encoding="utf-8")

        # Modify source to trigger re-check
        source.write_text("x = 2\n", encoding="utf-8")

        result = _generate_quick_design(source, project)
        assert result.change == ChangeLevel.AGENT_UPDATED

    def test_extracts_dependencies(self, tmp_path: Path) -> None:
        """Extracts import dependencies via AST analysis."""
        project = _setup_project(tmp_path)
        # Create two files where one imports the other
        _make_source_file(
            project,
            "src/utils.py",
            "def helper():\n    pass\n",
        )
        source = _make_source_file(
            project,
            "src/main.py",
            "from src.utils import helper\n\ndef main():\n    helper()\n",
        )

        result = _generate_quick_design(source, project)
        assert result.change == ChangeLevel.NEW_FILE

        # Read the design file and check dependencies
        design_path = mirror_path(project, source)
        design = parse_design_file(design_path)
        assert design is not None
        # Should contain a dependency on utils.py
        assert any("utils" in d for d in design.dependencies)

    def test_uses_heuristic_description(self, tmp_path: Path) -> None:
        """Uses module docstring as description."""
        project = _setup_project(tmp_path)
        source = _make_source_file(
            project,
            "src/mod.py",
            '"""Handles user authentication."""\n\nx = 1\n',
        )

        _generate_quick_design(source, project)

        design_path = mirror_path(project, source)
        frontmatter = parse_design_file_frontmatter(design_path)
        assert frontmatter is not None
        assert frontmatter.description == "Handles user authentication."


# ---------------------------------------------------------------------------
# bootstrap_quick tests
# ---------------------------------------------------------------------------


class TestBootstrapQuick:
    """Tests for the bootstrap_quick function."""

    def test_generates_skeletons_for_all_source_files(self, tmp_path: Path) -> None:
        """Quick bootstrap generates skeleton design files for all source files."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "src/b.py", "b = 2\n")
        _make_source_file(project, "src/c.py", "c = 3\n")

        config = LexibraryConfig()
        stats = bootstrap_quick(project, config)

        assert stats.files_scanned == 3
        assert stats.files_created == 3
        assert stats.files_skipped == 0

        # Verify design files exist
        for name in ("a.py", "b.py", "c.py"):
            design_path = mirror_path(project, project / "src" / name)
            assert design_path.exists(), f"Missing design file for {name}"

    def test_skips_existing_up_to_date_files(self, tmp_path: Path) -> None:
        """Quick bootstrap skips files with existing up-to-date design files."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "src/b.py", "b = 2\n")

        config = LexibraryConfig()

        # First run creates all files
        stats1 = bootstrap_quick(project, config)
        assert stats1.files_created == 2

        # Second run should skip all (idempotent)
        stats2 = bootstrap_quick(project, config)
        assert stats2.files_created == 0
        assert stats2.files_skipped == 2

    def test_idempotent_second_run(self, tmp_path: Path) -> None:
        """Running bootstrap twice with no changes reports 0 created, 0 updated."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")

        config = LexibraryConfig()

        stats1 = bootstrap_quick(project, config)
        assert stats1.files_created == 1

        stats2 = bootstrap_quick(project, config)
        assert stats2.files_created == 0
        assert stats2.files_updated == 0

    def test_respects_scope_override(self, tmp_path: Path) -> None:
        """Quick bootstrap with scope override only processes files in that scope."""
        project = _setup_project(tmp_path, scope_root=".")
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "lib/b.py", "b = 2\n")

        config = LexibraryConfig()

        stats = bootstrap_quick(project, config, scope_override="src")

        # Only src/a.py should be processed
        assert stats.files_scanned == 1
        assert stats.files_created == 1

        # Design file for src/a.py should exist
        assert mirror_path(project, project / "src" / "a.py").exists()
        # Design file for lib/b.py should NOT exist
        assert not mirror_path(project, project / "lib" / "b.py").exists()

    def test_marks_files_as_bootstrap_quick(self, tmp_path: Path) -> None:
        """Generated design files have updated_by: bootstrap-quick."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/mod.py", "x = 1\n")

        config = LexibraryConfig()
        bootstrap_quick(project, config)

        design_path = mirror_path(project, project / "src" / "mod.py")
        frontmatter = parse_design_file_frontmatter(design_path)
        assert frontmatter is not None
        assert frontmatter.updated_by == "bootstrap-quick"

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        """Progress callback is called for each file."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "src/b.py", "b = 2\n")

        config = LexibraryConfig()
        callbacks: list[tuple[Path, str]] = []

        def callback(path: Path, status: str) -> None:
            callbacks.append((path, status))

        bootstrap_quick(project, config, progress_callback=callback)

        assert len(callbacks) == 2
        statuses = {s for _, s in callbacks}
        assert "created" in statuses

    def test_handles_errors_gracefully(self, tmp_path: Path) -> None:
        """Bootstrap continues after individual file failures."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "src/b.py", "b = 2\n")

        config = LexibraryConfig()

        # Mock _generate_quick_design to fail on first file, succeed on second
        with patch("lexibrary.lifecycle.bootstrap._generate_quick_design") as mock_gen:
            from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415

            mock_gen.side_effect = [
                RuntimeError("mock failure"),
                FileResult(change=ChangeLevel.NEW_FILE),
            ]
            stats = bootstrap_quick(project, config)

        assert stats.files_failed == 1
        assert stats.files_created == 1
        assert len(stats.errors) == 1


# ---------------------------------------------------------------------------
# bootstrap_full tests
# ---------------------------------------------------------------------------


class TestBootstrapFull:
    """Tests for the bootstrap_full function."""

    @pytest.mark.asyncio
    async def test_calls_archivist_update_file(self, tmp_path: Path) -> None:
        """Full bootstrap delegates to update_file with an ArchivistService."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/mod.py", "x = 1\n")

        config = LexibraryConfig()

        with patch(
            "lexibrary.lifecycle.bootstrap.update_file",
            new_callable=AsyncMock,
        ) as mock_update:
            from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415

            mock_update.return_value = FileResult(change=ChangeLevel.NEW_FILE)

            stats = await bootstrap_full(project, config, client_registry=ClientRegistry())

        assert stats.files_scanned == 1
        assert stats.files_created == 1
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_mode_handles_failures(self, tmp_path: Path) -> None:
        """Full bootstrap handles update_file failures gracefully."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "src/b.py", "b = 2\n")

        config = LexibraryConfig()

        with patch(
            "lexibrary.lifecycle.bootstrap.update_file",
            new_callable=AsyncMock,
        ) as mock_update:
            from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415

            mock_update.side_effect = [
                RuntimeError("LLM error"),
                FileResult(change=ChangeLevel.NEW_FILE),
            ]

            stats = await bootstrap_full(project, config, client_registry=ClientRegistry())

        assert stats.files_failed == 1
        assert stats.files_created == 1

    @pytest.mark.asyncio
    async def test_full_mode_progress_callback(self, tmp_path: Path) -> None:
        """Full bootstrap calls progress callback for each file."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/mod.py", "x = 1\n")

        config = LexibraryConfig()
        callbacks: list[tuple[Path, str]] = []

        def callback(path: Path, status: str) -> None:
            callbacks.append((path, status))

        with patch(
            "lexibrary.lifecycle.bootstrap.update_file",
            new_callable=AsyncMock,
        ) as mock_update:
            from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415

            mock_update.return_value = FileResult(change=ChangeLevel.NEW_FILE)

            await bootstrap_full(
                project, config, progress_callback=callback, client_registry=ClientRegistry()
            )

        assert len(callbacks) == 1
        assert callbacks[0][1] == "created"

    @pytest.mark.asyncio
    async def test_full_mode_skips_unchanged(self, tmp_path: Path) -> None:
        """Full bootstrap counts unchanged files as skipped."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/mod.py", "x = 1\n")

        config = LexibraryConfig()

        with patch(
            "lexibrary.lifecycle.bootstrap.update_file",
            new_callable=AsyncMock,
        ) as mock_update:
            from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415

            mock_update.return_value = FileResult(change=ChangeLevel.UNCHANGED)

            stats = await bootstrap_full(project, config, client_registry=ClientRegistry())

        assert stats.files_skipped == 1
        assert stats.files_created == 0

    @pytest.mark.asyncio
    async def test_full_mode_respects_scope_override(self, tmp_path: Path) -> None:
        """Full bootstrap with scope override only processes files in that scope."""
        project = _setup_project(tmp_path, scope_root=".")
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "lib/b.py", "b = 2\n")

        config = LexibraryConfig()

        with patch(
            "lexibrary.lifecycle.bootstrap.update_file",
            new_callable=AsyncMock,
        ) as mock_update:
            from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415

            mock_update.return_value = FileResult(change=ChangeLevel.NEW_FILE)

            stats = await bootstrap_full(
                project, config, scope_override="src", client_registry=ClientRegistry()
            )

        # Only src/a.py should be processed
        assert stats.files_scanned == 1


# ---------------------------------------------------------------------------
# BootstrapStats tests
# ---------------------------------------------------------------------------


class TestBootstrapStats:
    """Tests for the BootstrapStats dataclass."""

    def test_default_values(self) -> None:
        """BootstrapStats has sensible defaults."""
        stats = BootstrapStats()
        assert stats.files_scanned == 0
        assert stats.files_created == 0
        assert stats.files_updated == 0
        assert stats.files_skipped == 0
        assert stats.files_failed == 0
        assert stats.errors == []


# ---------------------------------------------------------------------------
# Multi-root bootstrap tests (task 7.5 — two-root gating + missing-root warn)
# ---------------------------------------------------------------------------


class TestBootstrapQuickMultiRoot:
    """Two-root gating + missing-root warn for ``bootstrap_quick``.

    Pins the multi-root contract:

    * When ``scope_override`` is ``None``, discovery walks every declared root
      and unions the results. A file under either root is in-scope; a file
      outside every declared root is silently excluded from discovery.
    * When ``scope_override`` points at a directory outside every declared
      root, ``bootstrap_quick`` raises :class:`ValueError` with Block A's
      wording (``outside all configured scope_roots: [...]``).
    * A declared root that does not exist on disk surfaces one
      :func:`warn` call per missing root **from the bootstrap layer** before
      discovery starts. The model-side existence filter is silent — no warn
      output comes from :meth:`LexibraryConfig.resolved_scope_roots`.
    """

    def test_in_scope_under_either_root_is_discovered(self, tmp_path: Path) -> None:
        """Two-root gating: files under either declared root are processed."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "baml_src/main.py", "b = 2\n")
        # A file outside every declared root must NOT be discovered.
        _make_source_file(project, "docs/ignore_me.py", "c = 3\n")

        config = LexibraryConfig(scope_roots=[ScopeRoot(path="src"), ScopeRoot(path="baml_src")])
        stats = bootstrap_quick(project, config)

        # Both in-scope files processed; the docs/ file is outside every root.
        assert stats.files_scanned == 2
        assert stats.files_created == 2
        assert mirror_path(project, project / "src" / "a.py").exists()
        assert mirror_path(project, project / "baml_src" / "main.py").exists()
        assert not mirror_path(project, project / "docs" / "ignore_me.py").exists()

    def test_scope_override_outside_all_roots_raises_block_a(self, tmp_path: Path) -> None:
        """``scope_override`` pointing outside every declared root raises Block A.

        The error text must be Block A: ``"<override> is outside all configured
        scope_roots: [<declared paths>]"``. The declared list uses
        ``[r.path for r in config.scope_roots]`` (string repr of the list).
        """
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "baml_src/main.py", "b = 2\n")
        # The override directory must exist so we're testing the scope gate,
        # not a ``FileNotFoundError`` from the path resolver.
        (project / "docs").mkdir()

        config = LexibraryConfig(scope_roots=[ScopeRoot(path="src"), ScopeRoot(path="baml_src")])

        with pytest.raises(ValueError) as excinfo:
            bootstrap_quick(project, config, scope_override="docs")

        message = str(excinfo.value)
        assert "docs" in message
        assert "outside all configured scope_roots" in message
        # Block A lists declared roots via ``[r.path for r in config.scope_roots]``
        assert "'src'" in message
        assert "'baml_src'" in message

    def test_missing_root_emits_single_warn_from_bootstrap_layer(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A missing-on-disk root emits one warn from bootstrap, not from the model.

        Two declared roots, one absent: bootstrap surfaces a single warn with
        canonical wording ``"scope_root '<path>' does not exist on disk;
        skipping"`` before discovery starts. The remaining root is still walked.
        """
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        # ``baml_src/`` does not exist on disk.

        config = LexibraryConfig(scope_roots=[ScopeRoot(path="src"), ScopeRoot(path="baml_src")])
        stats = bootstrap_quick(project, config)

        captured = capsys.readouterr()
        # Warn should be printed to stderr, once, naming the missing root.
        assert "Warning:" in captured.err
        assert "scope_root 'baml_src'" in captured.err
        assert "does not exist on disk; skipping" in captured.err
        assert captured.err.count("does not exist on disk; skipping") == 1

        # The existing root is still walked — discovery must not be aborted by
        # the missing root.
        assert stats.files_scanned == 1
        assert stats.files_created == 1

    def test_model_side_has_no_warn_output(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``LexibraryConfig.resolved_scope_roots`` itself emits no warn.

        The warn-on-missing policy lives in the bootstrap layer (per design:
        the model stays decoupled from ``_output.py``). Pinning this keeps any
        future refactor that moves warns into the model honest.
        """
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")

        config = LexibraryConfig(scope_roots=[ScopeRoot(path="src"), ScopeRoot(path="ghost")])

        resolved = config.resolved_scope_roots(project)
        captured = capsys.readouterr()

        assert captured.out == ""
        assert captured.err == ""
        assert len(resolved.resolved) == 1
        assert len(resolved.missing) == 1
        assert resolved.missing[0].path == "ghost"


class TestBootstrapFullMultiRoot:
    """Two-root gating + missing-root warn for ``bootstrap_full``.

    Mirrors :class:`TestBootstrapQuickMultiRoot` but exercises the async
    ``bootstrap_full`` path. ``update_file`` is mocked so we do not touch the
    LLM; we assert on the call count and arguments to prove each in-scope
    file was routed through the archivist.
    """

    @pytest.mark.asyncio
    async def test_in_scope_under_either_root_is_discovered(
        self,
        tmp_path: Path,
    ) -> None:
        """Two-root gating: full bootstrap processes files under either root."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "baml_src/main.py", "b = 2\n")
        # Outside every declared root — must not be processed.
        _make_source_file(project, "docs/ignore_me.py", "c = 3\n")

        config = LexibraryConfig(scope_roots=[ScopeRoot(path="src"), ScopeRoot(path="baml_src")])

        with patch(
            "lexibrary.lifecycle.bootstrap.update_file",
            new_callable=AsyncMock,
        ) as mock_update:
            from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415

            mock_update.return_value = FileResult(change=ChangeLevel.NEW_FILE)

            stats = await bootstrap_full(
                project,
                config,
                client_registry=ClientRegistry(),
            )

        assert stats.files_scanned == 2
        assert stats.files_created == 2
        # Two in-scope files → two archivist calls.
        assert mock_update.call_count == 2
        called_paths = {call.args[0].name for call in mock_update.call_args_list}
        assert called_paths == {"a.py", "main.py"}

    @pytest.mark.asyncio
    async def test_scope_override_outside_all_roots_raises_block_a(
        self,
        tmp_path: Path,
    ) -> None:
        """``scope_override`` outside every declared root raises Block A."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        _make_source_file(project, "baml_src/main.py", "b = 2\n")
        (project / "docs").mkdir()

        config = LexibraryConfig(scope_roots=[ScopeRoot(path="src"), ScopeRoot(path="baml_src")])

        with pytest.raises(ValueError) as excinfo:
            await bootstrap_full(
                project,
                config,
                scope_override="docs",
                client_registry=ClientRegistry(),
            )

        message = str(excinfo.value)
        assert "docs" in message
        assert "outside all configured scope_roots" in message
        assert "'src'" in message
        assert "'baml_src'" in message

    @pytest.mark.asyncio
    async def test_missing_root_emits_single_warn_from_bootstrap_layer(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Missing-on-disk root surfaces a single warn from the bootstrap layer."""
        project = _setup_project(tmp_path)
        _make_source_file(project, "src/a.py", "a = 1\n")
        # ``baml_src/`` does not exist on disk.

        config = LexibraryConfig(scope_roots=[ScopeRoot(path="src"), ScopeRoot(path="baml_src")])

        with patch(
            "lexibrary.lifecycle.bootstrap.update_file",
            new_callable=AsyncMock,
        ) as mock_update:
            from lexibrary.archivist.pipeline import FileResult  # noqa: PLC0415

            mock_update.return_value = FileResult(change=ChangeLevel.NEW_FILE)

            stats = await bootstrap_full(
                project,
                config,
                client_registry=ClientRegistry(),
            )

        captured = capsys.readouterr()
        assert "Warning:" in captured.err
        assert "scope_root 'baml_src'" in captured.err
        assert "does not exist on disk; skipping" in captured.err
        assert captured.err.count("does not exist on disk; skipping") == 1

        # Discovery continues against the remaining root.
        assert stats.files_scanned == 1
        assert mock_update.call_count == 1
