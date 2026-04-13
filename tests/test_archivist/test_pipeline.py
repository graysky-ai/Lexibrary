"""Tests for archivist pipeline."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import (
    FileResult,
    UpdateStats,
    _accumulate_stats,
    _has_meaningful_changes,
    _is_binary,
    _is_within_any_scope,
    _refresh_parent_aindex,
    discover_source_files,
    reindex_directories,
    update_file,
    update_files,
    update_project,
)
from lexibrary.archivist.service import (
    ArchivistService,
    DesignFileResult,
)
from lexibrary.artifacts.aindex import AIndexEntry, AIndexFile
from lexibrary.artifacts.aindex_serializer import serialize_aindex
from lexibrary.artifacts.design_file import StalenessMetadata
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.config.schema import LexibraryConfig, ScopeRoot, TokenBudgetConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _make_source_file(tmp_path: Path, rel: str, content: str = "print('hello')") -> Path:
    """Create a source file at the given relative path."""
    source = tmp_path / rel
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return source


def _make_design_file(
    tmp_path: Path,
    source_rel: str,
    *,
    source_hash: str = "src_hash_aaa",
    interface_hash: str | None = None,
    design_hash: str | None = None,
    body: str | None = None,
    include_footer: bool = True,
    description: str = "Test file.",
) -> Path:
    """Create a design file at the mirror path within tmp_path."""
    design_dir = tmp_path / ".lexibrary" / "designs" / Path(source_rel).parent
    design_dir.mkdir(parents=True, exist_ok=True)
    design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"

    if body is None:
        body = (
            "---\n"
            f"description: {description}\n"
            "id: DS-001\n"
            "updated_by: archivist\n"
            "---\n"
            "\n"
            f"# {source_rel}\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\ndef foo(): ...\n```\n"
            "\n"
            "## Dependencies\n"
            "\n"
            "(none)\n"
            "\n"
            "## Dependents\n"
            "\n"
            "(none)\n"
        )

    if include_footer:
        if design_hash is None:
            design_hash = _sha256(body.rstrip("\n"))

        footer_lines = [
            "<!-- lexibrary:meta",
            f"source: {source_rel}",
            f"source_hash: {source_hash}",
        ]
        if interface_hash is not None:
            footer_lines.append(f"interface_hash: {interface_hash}")
        footer_lines.append(f"design_hash: {design_hash}")
        footer_lines.append("generated: 2026-01-01T12:00:00")
        footer_lines.append("generator: lexibrary-v2")
        footer_lines.append("-->")

        text = body + "\n" + "\n".join(footer_lines) + "\n"
    else:
        text = body

    design_path.write_text(text, encoding="utf-8")
    return design_path


def _make_aindex(tmp_path: Path, dir_rel: str, entries: list[AIndexEntry]) -> Path:
    """Create a .aindex file for a directory."""
    from datetime import datetime

    aindex_dir = tmp_path / ".lexibrary" / "designs" / dir_rel
    aindex_dir.mkdir(parents=True, exist_ok=True)
    aindex_file_path = aindex_dir / ".aindex"

    aindex = AIndexFile(
        directory_path=dir_rel,
        billboard="Test directory.",
        entries=entries,
        metadata=StalenessMetadata(
            source=dir_rel,
            source_hash="dir_hash",
            generated=datetime(2026, 1, 1),
            generator="lexibrary-v2",
        ),
    )
    serialized = serialize_aindex(aindex)
    aindex_file_path.write_text(serialized, encoding="utf-8")
    return aindex_file_path


def _make_config(
    scope_root: str | None = None,
    scope_roots: list[str] | None = None,
    design_file_tokens: int = 400,
) -> LexibraryConfig:
    """Create a config with the given scope declaration and token budget.

    Accepts *either* a single-root ``scope_root`` string (for existing tests
    that predate the multi-root migration) *or* an explicit ``scope_roots``
    list. When both are omitted, the default root is ``"."``.
    """
    if scope_roots is not None:
        roots = [ScopeRoot(path=p) for p in scope_roots]
    elif scope_root is not None:
        roots = [ScopeRoot(path=scope_root)]
    else:
        roots = [ScopeRoot(path=".")]
    return LexibraryConfig(
        scope_roots=roots,
        token_budgets=TokenBudgetConfig(design_file_tokens=design_file_tokens),
    )


def _mock_archivist(
    summary: str = "Handles testing.",
    interface_contract: str = "def foo(): ...",
    error: bool = False,
) -> ArchivistService:
    """Create a mock ArchivistService that returns a canned design file output."""
    output = DesignFileOutput(
        summary=summary,
        interface_contract=interface_contract,
        dependencies=[],
        tests=None,
        complexity_warning=None,
        wikilinks=[],
        tags=[],
    )

    result = DesignFileResult(
        source_path="mock",
        design_file_output=None if error else output,
        error=error,
        error_message="LLM error" if error else None,
    )

    service = MagicMock(spec=ArchivistService)
    service.generate_design_file = AsyncMock(return_value=result)
    return service


# ---------------------------------------------------------------------------
# UpdateStats
# ---------------------------------------------------------------------------


class TestUpdateStats:
    """Verify UpdateStats dataclass defaults and accumulation."""

    def test_defaults_are_zero(self) -> None:
        stats = UpdateStats()
        assert stats.files_scanned == 0
        assert stats.files_unchanged == 0
        assert stats.files_agent_updated == 0
        assert stats.files_updated == 0
        assert stats.files_created == 0
        assert stats.files_failed == 0
        assert stats.aindex_refreshed == 0
        assert stats.token_budget_warnings == 0

    def test_topology_failed_defaults_false(self) -> None:
        stats = UpdateStats()
        assert stats.topology_failed is False

    def test_linkgraph_fields_default_values(self) -> None:
        stats = UpdateStats()
        assert stats.linkgraph_built is False
        assert stats.linkgraph_error is None

    def test_linkgraph_fields_are_mutable(self) -> None:
        stats = UpdateStats()
        stats.linkgraph_built = True
        stats.linkgraph_error = "SQLite error: disk full"
        assert stats.linkgraph_built is True
        assert stats.linkgraph_error == "SQLite error: disk full"

    def test_fields_are_mutable(self) -> None:
        stats = UpdateStats()
        stats.files_scanned = 5
        stats.files_created = 3
        stats.token_budget_warnings = 1
        assert stats.files_scanned == 5
        assert stats.files_created == 3
        assert stats.token_budget_warnings == 1


# ---------------------------------------------------------------------------
# _is_within_any_scope (multi-root scope gating)
# ---------------------------------------------------------------------------


class TestIsWithinAnyScope:
    """Multi-root scope gating: pass if path is under *any* declared root."""

    def test_inside_single_scope(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "foo.py"
        config = _make_config(scope_roots=["src"])
        assert _is_within_any_scope(source, tmp_path, config) is True

    def test_outside_single_scope(self, tmp_path: Path) -> None:
        source = tmp_path / "docs" / "readme.md"
        config = _make_config(scope_roots=["src"])
        assert _is_within_any_scope(source, tmp_path, config) is False

    def test_dot_scope_includes_everything(self, tmp_path: Path) -> None:
        source = tmp_path / "any" / "file.py"
        config = _make_config(scope_roots=["."])
        assert _is_within_any_scope(source, tmp_path, config) is True

    def test_two_roots_pass_under_first(self, tmp_path: Path) -> None:
        """In-scope pass under the first declared root."""
        source = tmp_path / "src" / "foo.py"
        config = _make_config(scope_roots=["src", "baml_src"])
        assert _is_within_any_scope(source, tmp_path, config) is True

    def test_two_roots_pass_under_second(self, tmp_path: Path) -> None:
        """In-scope pass under the second declared root."""
        source = tmp_path / "baml_src" / "foo.baml"
        config = _make_config(scope_roots=["src", "baml_src"])
        assert _is_within_any_scope(source, tmp_path, config) is True

    def test_two_roots_reject_neither(self, tmp_path: Path) -> None:
        """File under neither declared root is rejected."""
        source = tmp_path / "docs" / "foo.md"
        config = _make_config(scope_roots=["src", "baml_src"])
        assert _is_within_any_scope(source, tmp_path, config) is False


# ---------------------------------------------------------------------------
# _is_binary
# ---------------------------------------------------------------------------


class TestIsBinary:
    def test_binary_extension(self) -> None:
        assert _is_binary(Path("image.png"), {".png", ".jpg"}) is True

    def test_non_binary_extension(self) -> None:
        assert _is_binary(Path("code.py"), {".png", ".jpg"}) is False


# ---------------------------------------------------------------------------
# discover_source_files (multi-root)
# ---------------------------------------------------------------------------


class TestDiscoverSourceFilesMultiRoot:
    """Multi-root behaviour of ``discover_source_files``.

    With ``scope_dir=None`` the function walks every declared scope root.
    With an explicit ``scope_dir`` it stays single-path so targeted
    ``lexi design update <file>`` calls remain unchanged.
    """

    def test_scope_dir_none_walks_all_declared_roots(self, tmp_path: Path) -> None:
        """With ``scope_dir=None`` the walk returns the union across roots."""
        (tmp_path / "src").mkdir()
        (tmp_path / "baml_src").mkdir()
        file_a = _make_source_file(tmp_path, "src/a.py", "def a(): ...")
        file_b = _make_source_file(tmp_path, "baml_src/b.baml", "class B {}")
        # Deliberate out-of-scope file — must not surface in the result.
        _make_source_file(tmp_path, "docs/foo.md", "# docs")

        config = _make_config(scope_roots=["src", "baml_src"])

        discovered = discover_source_files(tmp_path, config, scope_dir=None)

        discovered_resolved = {p.resolve() for p in discovered}
        assert file_a.resolve() in discovered_resolved
        assert file_b.resolve() in discovered_resolved
        assert (tmp_path / "docs" / "foo.md").resolve() not in discovered_resolved

    def test_explicit_scope_dir_restricts_to_single_path(self, tmp_path: Path) -> None:
        """An explicit ``scope_dir`` still restricts the walk to that one path."""
        (tmp_path / "src").mkdir()
        (tmp_path / "baml_src").mkdir()
        file_a = _make_source_file(tmp_path, "src/a.py", "def a(): ...")
        file_b = _make_source_file(tmp_path, "baml_src/b.baml", "class B {}")

        config = _make_config(scope_roots=["src", "baml_src"])

        discovered = discover_source_files(tmp_path, config, scope_dir=tmp_path / "src")

        discovered_resolved = {p.resolve() for p in discovered}
        assert file_a.resolve() in discovered_resolved
        # baml_src file is excluded by the explicit scope_dir override.
        assert file_b.resolve() not in discovered_resolved

    def test_missing_root_is_skipped_silently_by_discovery(self, tmp_path: Path) -> None:
        """A declared-but-missing root does not crash discovery.

        Missing roots are filtered out by
        ``LexibraryConfig.resolved_scope_roots`` and surfaced upstream (e.g.
        by bootstrap) as ``warn()`` messages. Discovery itself just walks the
        resolved subset.
        """
        (tmp_path / "src").mkdir()
        file_a = _make_source_file(tmp_path, "src/a.py", "def a(): ...")

        config = _make_config(scope_roots=["src", "ghost"])

        discovered = discover_source_files(tmp_path, config, scope_dir=None)

        discovered_resolved = {p.resolve() for p in discovered}
        assert file_a.resolve() in discovered_resolved

    def test_single_root_unchanged(self, tmp_path: Path) -> None:
        """Single-root behaviour matches pre-multi-root semantics."""
        src_file = _make_source_file(tmp_path, "src/foo.py", "x = 1")
        _make_source_file(tmp_path, "elsewhere/other.py", "y = 2")

        config = _make_config(scope_roots=["src"])

        files = discover_source_files(tmp_path, config)
        resolved = {p.resolve() for p in files}

        assert src_file.resolve() in resolved
        assert (tmp_path / "elsewhere" / "other.py").resolve() not in resolved


# ---------------------------------------------------------------------------
# update_file — multi-root gating
# ---------------------------------------------------------------------------


class TestUpdateFileMultiRootGating:
    """``update_file`` accepts files under any declared root and rejects others."""

    @pytest.mark.asyncio()
    async def test_multi_root_first_root_proceeds(self, tmp_path: Path) -> None:
        """File under the first declared root passes the scope gate."""
        source = _make_source_file(tmp_path, "src/foo.py", "def bar(): pass")
        config = _make_config(scope_roots=["src", "baml_src"])
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        # Reaching anything past the gate is enough to confirm acceptance.
        # The skip_reason for an out-of-scope file would be "out of scope".
        assert result.skip_reason != "out of scope"

    @pytest.mark.asyncio()
    async def test_multi_root_second_root_proceeds(self, tmp_path: Path) -> None:
        """File under the second declared root passes the scope gate."""
        source = _make_source_file(tmp_path, "baml_src/foo.baml", "function Bar() {}")
        config = _make_config(scope_roots=["src", "baml_src"])
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.skip_reason != "out of scope"

    @pytest.mark.asyncio()
    async def test_multi_root_outside_all_roots_skipped(self, tmp_path: Path) -> None:
        """File under neither declared root is skipped with ``out of scope``."""
        source = _make_source_file(tmp_path, "docs/readme.md", "# README")
        config = _make_config(scope_roots=["src", "baml_src"])
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.UNCHANGED
        assert result.skip_reason == "out of scope"
        archivist.generate_design_file.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_file — NEW_FILE scenario
# ---------------------------------------------------------------------------


class TestUpdateFileNewFile:
    """New file with no existing design file gets LLM-generated design file."""

    @pytest.mark.asyncio()
    async def test_new_file_creates_design_file(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "src/foo.py", "def bar(): pass")
        config = _make_config()
        archivist = _mock_archivist(summary="Foo module for testing.")

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed

        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        assert design_path.exists()
        content = design_path.read_text()
        assert "Foo module for testing." in content

        # LLM was called
        archivist.generate_design_file.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_file — UNCHANGED scenario
# ---------------------------------------------------------------------------


class TestUpdateFileUnchanged:
    """File with matching content hash returns UNCHANGED without LLM call."""

    @pytest.mark.asyncio()
    async def test_unchanged_file_no_llm(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Compute actual content hash (SHA-256 of raw bytes)
        import hashlib as _hl

        actual_hash = _hl.sha256(source.read_bytes()).hexdigest()

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash=actual_hash,
        )

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.UNCHANGED
        archivist.generate_design_file.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_file — AGENT_UPDATED scenario
# ---------------------------------------------------------------------------


class TestUpdateFileAgentUpdated:
    """Agent-edited design file gets footer refresh only, no LLM call."""

    @pytest.mark.asyncio()
    async def test_agent_updated_refreshes_footer(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Create design file with a mismatched design_hash (simulating agent edit)
        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_hash",
            design_hash="agent_changed_this",
        )

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.AGENT_UPDATED
        archivist.generate_design_file.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_file — FOOTERLESS scenario
# ---------------------------------------------------------------------------


class TestUpdateFileFooterless:
    """Design file without footer is treated as AGENT_UPDATED (adds footer)."""

    @pytest.mark.asyncio()
    async def test_footerless_treated_as_agent_updated(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        _make_design_file(tmp_path, source_rel, include_footer=False)

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.AGENT_UPDATED
        archivist.generate_design_file.assert_not_awaited()

        # Verify footer was added
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        content = design_path.read_text()
        assert "lexibrary:meta" in content


# ---------------------------------------------------------------------------
# update_file — CONTENT_ONLY scenario
# ---------------------------------------------------------------------------


class TestUpdateFileContentOnly:
    """Content changed but interface unchanged triggers LLM call."""

    @pytest.mark.asyncio()
    async def test_content_only_calls_llm(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass\n# comment")

        # Create design file with old source hash but matching interface hash
        # We need to make the design_hash match the actual content hash of the design file
        body = (
            "---\n"
            "description: Test file.\n"
            "updated_by: archivist\n"
            "---\n"
            "\n"
            f"# {source_rel}\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\ndef foo(): ...\n```\n"
            "\n"
            "## Dependencies\n"
            "\n"
            "(none)\n"
            "\n"
            "## Dependents\n"
            "\n"
            "(none)\n"
        )

        # We need interface_hash to match what compute_hashes will return
        # For this test, we mock compute_hashes
        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("new_content_hash", "same_iface")

            _make_design_file(
                tmp_path,
                source_rel,
                source_hash="old_content_hash",
                interface_hash="same_iface",
                body=body,
            )

            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.CONTENT_ONLY,
            ):
                config = _make_config()
                archivist = _mock_archivist()

                result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.CONTENT_ONLY
        archivist.generate_design_file.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_file — CONTENT_CHANGED scenario (non-code)
# ---------------------------------------------------------------------------


class TestUpdateFileContentChanged:
    """Non-code file content change triggers LLM call."""

    @pytest.mark.asyncio()
    async def test_content_changed_non_code(self, tmp_path: Path) -> None:
        source_rel = "docs/readme.md"
        source = _make_source_file(tmp_path, source_rel, "# Updated readme")

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("new_hash", None)

            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.CONTENT_CHANGED,
            ):
                config = _make_config()
                archivist = _mock_archivist()

                result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.CONTENT_CHANGED
        archivist.generate_design_file.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_file — INTERFACE_CHANGED scenario
# ---------------------------------------------------------------------------


class TestUpdateFileInterfaceChanged:
    """Interface change triggers full LLM regeneration."""

    @pytest.mark.asyncio()
    async def test_interface_changed_calls_llm(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def new_func(): pass")

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("new_hash", "new_iface")

            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.INTERFACE_CHANGED,
            ):
                config = _make_config()
                archivist = _mock_archivist()

                result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.INTERFACE_CHANGED
        archivist.generate_design_file.assert_awaited_once()


# ---------------------------------------------------------------------------
# update_file — outside scope
# ---------------------------------------------------------------------------


class TestUpdateFileOutsideScope:
    """File outside every declared scope root is skipped."""

    @pytest.mark.asyncio()
    async def test_outside_scope_skipped(self, tmp_path: Path) -> None:
        source = _make_source_file(tmp_path, "docs/readme.md")
        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.UNCHANGED
        archivist.generate_design_file.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_two_roots_in_scope_under_first(self, tmp_path: Path) -> None:
        """File under the first declared root is processed."""
        source = _make_source_file(tmp_path, "src/foo.py", "def bar(): pass")
        config = _make_config(scope_roots=["src", "baml_src"])
        archivist = _mock_archivist(summary="Foo.")

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        archivist.generate_design_file.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_two_roots_in_scope_under_second(self, tmp_path: Path) -> None:
        """File under the second declared root is processed."""
        source = _make_source_file(tmp_path, "baml_src/bar.py", "def baz(): pass")
        config = _make_config(scope_roots=["src", "baml_src"])
        archivist = _mock_archivist(summary="Bar.")

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        archivist.generate_design_file.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_two_roots_reject_under_neither(self, tmp_path: Path) -> None:
        """File outside both declared roots is skipped, LLM not invoked."""
        source = _make_source_file(tmp_path, "docs/foo.md", "# docs")
        config = _make_config(scope_roots=["src", "baml_src"])
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.UNCHANGED
        assert result.skip_reason == "out of scope"
        archivist.generate_design_file.assert_not_awaited()


# ---------------------------------------------------------------------------
# update_file — .aindex refresh
# ---------------------------------------------------------------------------


class TestUpdateFileAIndexRefresh:
    """Parent .aindex is refreshed when design file is created/updated."""

    @pytest.mark.asyncio()
    async def test_aindex_refreshed_on_new_file(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Create parent .aindex with existing entries
        _make_aindex(
            tmp_path,
            "src",
            [
                AIndexEntry(name="existing.py", entry_type="file", description="Existing file"),
            ],
        )

        config = _make_config()
        archivist = _mock_archivist(summary="Foo module.")

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("hash1", "iface1")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.NEW_FILE,
            ):
                result = await update_file(source, tmp_path, config, archivist)

        assert result.aindex_refreshed is True

        # Check the .aindex was updated
        from lexibrary.artifacts.aindex_parser import parse_aindex

        aindex = parse_aindex(tmp_path / ".lexibrary" / "designs" / "src" / ".aindex")
        assert aindex is not None
        names = [e.name for e in aindex.entries]
        assert "foo.py" in names

        # Find the entry and check description
        for entry in aindex.entries:
            if entry.name == "foo.py":
                assert entry.description == "Foo module."
                break


# ---------------------------------------------------------------------------
# update_file — token budget warning
# ---------------------------------------------------------------------------


class TestUpdateFileTokenBudget:
    """Oversized design file logs warning but is still written."""

    @pytest.mark.asyncio()
    async def test_token_budget_warning(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Use a very low token budget
        config = _make_config(design_file_tokens=1)

        archivist = _mock_archivist(
            summary="A very detailed summary with lots of words.",
            interface_contract="def bar(): pass\ndef baz(): pass",
        )

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("hash1", "iface1")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.NEW_FILE,
            ):
                result = await update_file(source, tmp_path, config, archivist)

        assert result.token_budget_exceeded is True

        # File was still written
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        assert design_path.exists()


# ---------------------------------------------------------------------------
# update_file — LLM error
# ---------------------------------------------------------------------------


class TestUpdateFileLLMError:
    """LLM error marks the result as failed."""

    @pytest.mark.asyncio()
    async def test_llm_error_returns_failed(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        config = _make_config()
        archivist = _mock_archivist(error=True)

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("hash1", "iface1")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.NEW_FILE,
            ):
                result = await update_file(source, tmp_path, config, archivist)

        assert result.failed is True


# ---------------------------------------------------------------------------
# update_project — file discovery
# ---------------------------------------------------------------------------


class TestUpdateProjectDiscovery:
    """Project update discovers files within scope, skipping binary and .lexibrary."""

    @pytest.mark.asyncio()
    async def test_discovers_source_files(self, tmp_path: Path) -> None:
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        _make_source_file(tmp_path, "src/bar.py", "def bar(): pass")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        # Patch update_file to track calls without real processing
        calls: list[Path] = []

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            calls.append(source_path)
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file):
            stats = await update_project(tmp_path, config, archivist)

        assert stats.files_scanned == 2
        assert stats.files_unchanged == 2
        file_names = {p.name for p in calls}
        assert "foo.py" in file_names
        assert "bar.py" in file_names

    @pytest.mark.asyncio()
    async def test_skips_binary_files(self, tmp_path: Path) -> None:
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        # Create a binary file
        img = tmp_path / "src" / "logo.png"
        img.write_bytes(b"\x89PNG")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        calls: list[Path] = []

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            calls.append(source_path)
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file):
            await update_project(tmp_path, config, archivist)

        file_names = {p.name for p in calls}
        assert "logo.png" not in file_names

    @pytest.mark.asyncio()
    async def test_skips_lexibrary_contents(self, tmp_path: Path) -> None:
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        # Create a file inside .lexibrary
        lexi_file = tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"
        lexi_file.parent.mkdir(parents=True, exist_ok=True)
        lexi_file.write_text("design file", encoding="utf-8")

        config = _make_config()
        archivist = _mock_archivist()

        calls: list[Path] = []

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            calls.append(source_path)
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file):
            await update_project(tmp_path, config, archivist)

        file_names = {p.name for p in calls}
        assert "foo.py.md" not in file_names


# ---------------------------------------------------------------------------
# update_project — stats accumulation
# ---------------------------------------------------------------------------


class TestUpdateProjectStats:
    """Stats correctly reflect different change levels."""

    @pytest.mark.asyncio()
    async def test_stats_accumulate_correctly(self, tmp_path: Path) -> None:
        _make_source_file(tmp_path, "src/a.py", "# a")
        _make_source_file(tmp_path, "src/b.py", "# b")
        _make_source_file(tmp_path, "src/c.py", "# c")
        _make_source_file(tmp_path, "src/d.py", "# d")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        call_count = 0
        results = [
            FileResult(change=ChangeLevel.UNCHANGED),
            FileResult(change=ChangeLevel.NEW_FILE, aindex_refreshed=True),
            FileResult(change=ChangeLevel.AGENT_UPDATED),
            FileResult(
                change=ChangeLevel.CONTENT_ONLY,
                token_budget_exceeded=True,
                aindex_refreshed=True,
            ),
        ]

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            nonlocal call_count
            r = results[call_count]
            call_count += 1
            return r

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch("lexibrary.archivist.pipeline.reindex_directories", return_value=0),
        ):
            stats = await update_project(tmp_path, config, archivist)

        assert stats.files_scanned == 4
        assert stats.files_unchanged == 1
        assert stats.files_created == 1
        assert stats.files_agent_updated == 1
        assert stats.files_updated == 1
        assert stats.aindex_refreshed == 2
        assert stats.token_budget_warnings == 1
        assert stats.files_failed == 0


# ---------------------------------------------------------------------------
# update_project — progress callback
# ---------------------------------------------------------------------------


class TestUpdateProjectProgressCallback:
    """Progress callback is invoked for each processed file."""

    @pytest.mark.asyncio()
    async def test_progress_callback_called(self, tmp_path: Path) -> None:
        _make_source_file(tmp_path, "src/foo.py", "# foo")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        callback_calls: list[tuple[Path, ChangeLevel, str | None]] = []

        def callback(path: Path, change: ChangeLevel, skip_reason: str | None = None) -> None:
            callback_calls.append((path, change, skip_reason))

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file):
            await update_project(tmp_path, config, archivist, progress_callback=callback)

        assert len(callback_calls) == 1
        assert callback_calls[0][1] == ChangeLevel.UNCHANGED


# ---------------------------------------------------------------------------
# _refresh_parent_aindex
# ---------------------------------------------------------------------------


class TestRefreshParentAindex:
    """Verify .aindex child map updates."""

    def test_updates_existing_entry(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "foo.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.touch()

        _make_aindex(
            tmp_path,
            "src",
            [
                AIndexEntry(name="foo.py", entry_type="file", description="Old description"),
            ],
        )

        result = _refresh_parent_aindex(source, tmp_path, "New description")
        assert result is True

        from lexibrary.artifacts.aindex_parser import parse_aindex

        aindex = parse_aindex(tmp_path / ".lexibrary" / "designs" / "src" / ".aindex")
        assert aindex is not None
        assert aindex.entries[0].description == "New description"

    def test_adds_new_entry(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "new_file.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.touch()

        _make_aindex(
            tmp_path,
            "src",
            [
                AIndexEntry(name="existing.py", entry_type="file", description="Existing"),
            ],
        )

        result = _refresh_parent_aindex(source, tmp_path, "Brand new file")
        assert result is True

        from lexibrary.artifacts.aindex_parser import parse_aindex

        aindex = parse_aindex(tmp_path / ".lexibrary" / "designs" / "src" / ".aindex")
        assert aindex is not None
        names = [e.name for e in aindex.entries]
        assert "new_file.py" in names

    def test_no_aindex_returns_false(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "foo.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.touch()

        result = _refresh_parent_aindex(source, tmp_path, "Description")
        assert result is False

    def test_same_description_no_update(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "foo.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.touch()

        _make_aindex(
            tmp_path,
            "src",
            [
                AIndexEntry(name="foo.py", entry_type="file", description="Same description"),
            ],
        )

        result = _refresh_parent_aindex(source, tmp_path, "Same description")
        assert result is False


# ---------------------------------------------------------------------------
# update_file — available_artifacts forwarding
# ---------------------------------------------------------------------------


class TestUpdateFileAvailableArtifacts:
    """Verify available_artifacts is passed through to the DesignFileRequest."""

    @pytest.mark.asyncio()
    async def test_artifacts_passed_to_archivist(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        config = _make_config()
        archivist = _mock_archivist(summary="Foo module.")
        artifacts = ["Authentication", "Caching"]

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("hash1", "iface1")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.NEW_FILE,
            ):
                await update_file(
                    source,
                    tmp_path,
                    config,
                    archivist,
                    available_artifacts=artifacts,
                )

        # Verify the request passed to generate_design_file includes artifacts
        call_args = archivist.generate_design_file.call_args
        request = call_args[0][0]
        assert request.available_artifacts == artifacts

    @pytest.mark.asyncio()
    async def test_none_artifacts_by_default(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        config = _make_config()
        archivist = _mock_archivist(summary="Foo module.")

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("hash1", "iface1")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.NEW_FILE,
            ):
                await update_file(source, tmp_path, config, archivist)

        # Verify the request passed to generate_design_file has None artifacts
        call_args = archivist.generate_design_file.call_args
        request = call_args[0][0]
        assert request.available_artifacts is None


# ---------------------------------------------------------------------------
# update_file — force parameter
# ---------------------------------------------------------------------------


class TestUpdateFileForce:
    """Verify force parameter deletes existing design, triggers NEW_FILE, and preserves context."""

    @pytest.mark.asyncio()
    async def test_force_regenerates_unchanged_file(self, tmp_path: Path) -> None:
        """Force=True on an up-to-date file deletes the design so check_change sees NEW_FILE."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Compute actual hashes to make the file look "unchanged"
        actual_hash = _sha256(source.read_bytes().decode())
        design_path = _make_design_file(
            tmp_path,
            source_rel,
            source_hash=actual_hash,
        )
        assert design_path.exists()

        config = _make_config()
        archivist = _mock_archivist(summary="Regenerated design.")

        result = await update_file(source, tmp_path, config, archivist, force=True)

        # Force should have caused an LLM call via NEW_FILE path
        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed
        archivist.generate_design_file.assert_awaited_once()

        # Design file should exist again (written by the pipeline)
        assert design_path.exists()

    @pytest.mark.asyncio()
    async def test_force_preserves_existing_design_as_context(self, tmp_path: Path) -> None:
        """Force=True passes the old design content as existing_design to the LLM request."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Create a design file with recognisable content
        original_body = (
            "---\n"
            "description: Original design.\n"
            "id: DS-001\n"
            "updated_by: archivist\n"
            "---\n"
            "\n"
            "# Original content\n"
            "\n"
            "This is the original design file body.\n"
        )
        _make_design_file(tmp_path, source_rel, body=original_body)

        config = _make_config()
        archivist = _mock_archivist(summary="Updated design.")

        result = await update_file(source, tmp_path, config, archivist, force=True)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed

        # Verify the preserved content was passed as existing_design_file
        call_args = archivist.generate_design_file.call_args
        request = call_args[0][0]
        assert request.existing_design_file is not None
        assert "Original content" in request.existing_design_file

    @pytest.mark.asyncio()
    async def test_force_with_no_existing_file(self, tmp_path: Path) -> None:
        """Force=True with no existing design file works like a normal new file."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # No design file created
        config = _make_config()
        archivist = _mock_archivist(summary="New design.")

        result = await update_file(source, tmp_path, config, archivist, force=True)

        assert result.change == ChangeLevel.NEW_FILE
        assert not result.failed
        archivist.generate_design_file.assert_awaited_once()

        # Verify existing_design_file is None since there was no prior file
        call_args = archivist.generate_design_file.call_args
        request = call_args[0][0]
        assert request.existing_design_file is None


# ---------------------------------------------------------------------------
# update_project — concept loading
# ---------------------------------------------------------------------------


class TestUpdateProjectConceptLoading:
    """Verify update_project loads concepts and passes them to update_file."""

    @pytest.mark.asyncio()
    async def test_loads_concepts_from_lexibrary(self, tmp_path: Path) -> None:
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        # Create concept files in .lexibrary/concepts/
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        concepts_dir.mkdir(parents=True, exist_ok=True)

        concept_md = concepts_dir / "Authentication.md"
        concept_md.write_text(
            "---\ntitle: Authentication\nid: CN-001\naliases: []\ntags: [security]\n"
            "status: active\n---\n\nAuth concept body.\n",
            encoding="utf-8",
        )

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        captured_artifacts: list[list[str] | None] = []

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            available_artifacts: list[str] | None = None,
            **kwargs: object,
        ) -> FileResult:
            captured_artifacts.append(available_artifacts)
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=fake_update_file,
        ):
            await update_project(tmp_path, config, archivist)

        assert len(captured_artifacts) == 1
        assert captured_artifacts[0] is not None
        assert "Authentication" in captured_artifacts[0]

    @pytest.mark.asyncio()
    async def test_no_concepts_dir_passes_none(self, tmp_path: Path) -> None:
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        captured_artifacts: list[list[str] | None] = []

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            available_artifacts: list[str] | None = None,
            **kwargs: object,
        ) -> FileResult:
            captured_artifacts.append(available_artifacts)
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=fake_update_file,
        ):
            await update_project(tmp_path, config, archivist)

        assert len(captured_artifacts) == 1
        # No concepts dir means empty list -> None
        assert captured_artifacts[0] is None


# ---------------------------------------------------------------------------
# update_project — link graph integration
# ---------------------------------------------------------------------------


class TestUpdateProjectLinkGraph:
    """Verify that update_project() triggers a link graph full build."""

    @pytest.mark.asyncio()
    async def test_creates_index_db(self, tmp_path: Path) -> None:
        """update_project() creates index.db in .lexibrary/ after processing files."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        # Create .lexibrary directory (normally created by init)
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file):
            stats = await update_project(tmp_path, config, archivist)

        # Verify index.db was created
        index_db = tmp_path / ".lexibrary" / "index.db"
        assert index_db.exists(), "index.db should be created by update_project()"

        # Verify stats reflect successful build
        assert stats.linkgraph_built is True
        assert stats.linkgraph_error is None

    @pytest.mark.asyncio()
    async def test_accurate_stats_when_index_build_fails(self, tmp_path: Path) -> None:
        """update_project() returns accurate design file stats even when index build fails."""
        _make_source_file(tmp_path, "src/a.py", "# a")
        _make_source_file(tmp_path, "src/b.py", "# b")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        call_count = 0
        results = [
            FileResult(change=ChangeLevel.NEW_FILE, aindex_refreshed=True),
            FileResult(change=ChangeLevel.UNCHANGED),
        ]

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            nonlocal call_count
            r = results[call_count]
            call_count += 1
            return r

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch(
                "lexibrary.archivist.pipeline.build_index",
                side_effect=RuntimeError("SQLite corruption"),
            ),
            patch("lexibrary.archivist.pipeline.reindex_directories", return_value=0),
        ):
            stats = await update_project(tmp_path, config, archivist)

        # Design file stats should still be accurate
        assert stats.files_scanned == 2
        assert stats.files_created == 1
        assert stats.files_unchanged == 1
        assert stats.aindex_refreshed == 1

        # Link graph stats should reflect failure
        assert stats.linkgraph_built is False
        assert stats.linkgraph_error is not None
        assert "failed" in stats.linkgraph_error.lower()


# ---------------------------------------------------------------------------
# update_files — link graph incremental update integration
# ---------------------------------------------------------------------------


class TestUpdateFilesLinkGraph:
    """Verify that update_files() triggers incremental link graph updates."""

    @pytest.mark.asyncio()
    async def test_changed_files_trigger_incremental_update(self, tmp_path: Path) -> None:
        """update_files() with changed files triggers incremental index update."""
        source_a = _make_source_file(tmp_path, "src/a.py", "def a(): pass")
        source_b = _make_source_file(tmp_path, "src/b.py", "def b(): pass")

        # Create .lexibrary directory (normally created by init)
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
            patch(
                "lexibrary.archivist.pipeline.build_index",
            ) as mock_build,
        ):
            stats = await update_files(
                [source_a, source_b],
                tmp_path,
                config,
                archivist,
            )

        # build_index was called once with changed_paths including both files
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args
        changed_paths = call_kwargs[1]["changed_paths"]
        # Both processed files should be in the changed paths
        assert source_a in changed_paths
        assert source_b in changed_paths

        # Stats should reflect successful build
        assert stats.linkgraph_built is True
        assert stats.linkgraph_error is None

    @pytest.mark.asyncio()
    async def test_deleted_files_forwarded_to_incremental_update(self, tmp_path: Path) -> None:
        """update_files() with deleted files forwards deletions to incremental update."""
        # Create one existing file and one "deleted" path (does not exist on disk)
        source_existing = _make_source_file(tmp_path, "src/existing.py", "def e(): pass")
        source_deleted = tmp_path / "src" / "deleted.py"
        # deleted.py does NOT exist on disk -- simulates a file deletion

        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
            patch(
                "lexibrary.archivist.pipeline.build_index",
            ) as mock_build,
        ):
            stats = await update_files(
                [source_existing, source_deleted],
                tmp_path,
                config,
                archivist,
            )

        # build_index should have been called with both the processed path
        # and the deleted path
        mock_build.assert_called_once()
        changed_paths = mock_build.call_args[1]["changed_paths"]
        assert source_existing in changed_paths
        assert source_deleted in changed_paths

        assert stats.linkgraph_built is True
        assert stats.linkgraph_error is None

    @pytest.mark.asyncio()
    async def test_accurate_stats_when_incremental_update_fails(self, tmp_path: Path) -> None:
        """update_files() returns accurate design file stats when incremental update fails."""
        source_a = _make_source_file(tmp_path, "src/a.py", "# a")
        source_b = _make_source_file(tmp_path, "src/b.py", "# b")

        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        call_count = 0
        results = [
            FileResult(change=ChangeLevel.NEW_FILE, aindex_refreshed=True),
            FileResult(change=ChangeLevel.UNCHANGED),
        ]

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            nonlocal call_count
            r = results[call_count]
            call_count += 1
            return r

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
            patch(
                "lexibrary.archivist.pipeline.build_index",
                side_effect=RuntimeError("SQLite disk full"),
            ),
            patch("lexibrary.archivist.pipeline.reindex_directories", return_value=0),
        ):
            stats = await update_files(
                [source_a, source_b],
                tmp_path,
                config,
                archivist,
            )

        # Design file stats should be accurate despite index failure
        assert stats.files_scanned == 2
        assert stats.files_created == 1
        assert stats.files_unchanged == 1
        assert stats.aindex_refreshed == 1
        assert stats.files_failed == 0

        # Link graph stats should reflect the failure
        assert stats.linkgraph_built is False
        assert stats.linkgraph_error is not None
        assert "failed" in stats.linkgraph_error.lower()


# ---------------------------------------------------------------------------
# reindex_directories (task 7.5)
# ---------------------------------------------------------------------------


class TestReindexDirectories:
    """Tests for automated index regeneration after update_project() (task 7.5)."""

    def test_reindex_generates_aindex_files(self, tmp_path: Path) -> None:
        """reindex_directories() regenerates .aindex files for given directories."""
        # Set up project structure
        (tmp_path / ".lexibrary").mkdir(parents=True)
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "foo.py").write_text("def foo(): pass\n")
        (src_dir / "bar.py").write_text("def bar(): pass\n")

        config = _make_config(scope_root="src")

        count = reindex_directories([src_dir], tmp_path, config)

        # Should have re-indexed at least the src directory
        assert count >= 1
        aindex_file = tmp_path / ".lexibrary" / "designs" / "src" / ".aindex"
        assert aindex_file.exists()

    def test_reindex_includes_ancestors(self, tmp_path: Path) -> None:
        """reindex_directories() walks up to scope_root and re-indexes ancestors."""
        (tmp_path / ".lexibrary").mkdir(parents=True)
        # Create nested dirs: src/api/handlers/
        src_dir = tmp_path / "src"
        api_dir = src_dir / "api"
        handlers_dir = api_dir / "handlers"
        handlers_dir.mkdir(parents=True)
        (handlers_dir / "auth.py").write_text("def auth(): pass\n")
        (api_dir / "routes.py").write_text("def routes(): pass\n")
        (src_dir / "main.py").write_text("def main(): pass\n")

        config = _make_config(scope_root="src")

        count = reindex_directories([handlers_dir], tmp_path, config)

        # Should have re-indexed handlers/, api/, and src/ (3 directories)
        assert count == 3
        designs = tmp_path / ".lexibrary" / "designs"
        assert (designs / "src" / "api" / "handlers" / ".aindex").exists()
        assert (tmp_path / ".lexibrary" / "designs" / "src" / "api" / ".aindex").exists()
        assert (tmp_path / ".lexibrary" / "designs" / "src" / ".aindex").exists()

    def test_reindex_empty_list_returns_zero(self, tmp_path: Path) -> None:
        """reindex_directories() with empty list returns 0."""
        config = _make_config()
        count = reindex_directories([], tmp_path, config)
        assert count == 0

    def test_reindex_deduplicates_directories(self, tmp_path: Path) -> None:
        """Passing multiple files in the same directory re-indexes it once."""
        (tmp_path / ".lexibrary").mkdir(parents=True)
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("a = 1\n")
        (src_dir / "b.py").write_text("b = 2\n")

        config = _make_config(scope_root="src")

        # Both files are in src/, so src/ should only be indexed once
        count = reindex_directories([src_dir, src_dir], tmp_path, config)
        assert count == 1

    @pytest.mark.asyncio()
    async def test_update_project_triggers_reindex(self, tmp_path: Path) -> None:
        """update_project() calls reindex_directories when files are changed."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.NEW_FILE)

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch(
                "lexibrary.archivist.pipeline.reindex_directories",
                return_value=2,
            ) as mock_reindex,
        ):
            await update_project(tmp_path, config, archivist)

        mock_reindex.assert_called_once()
        # Verify the arguments
        call_args = mock_reindex.call_args
        dirs_arg = call_args[0][0]
        # Should contain the parent directory of the changed file
        assert any(d.name == "src" for d in dirs_arg)

    @pytest.mark.asyncio()
    async def test_update_files_triggers_reindex(self, tmp_path: Path) -> None:
        """update_files() calls reindex_directories when files are changed."""
        source = _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.NEW_FILE)

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch(
                "lexibrary.archivist.pipeline.reindex_directories",
                return_value=1,
            ) as mock_reindex,
            patch("lexibrary.archivist.pipeline.build_index"),
        ):
            await update_files([source], tmp_path, config, archivist)

        mock_reindex.assert_called_once()


# ---------------------------------------------------------------------------
# Skip-when-no-changes (task 7.6)
# ---------------------------------------------------------------------------


class TestSkipWhenNoChanges:
    """Tests for skip re-indexing when UpdateStats has zero changes (task 7.6)."""

    def test_has_meaningful_changes_all_zeros(self) -> None:
        """_has_meaningful_changes returns False when no files changed."""
        stats = UpdateStats(files_scanned=10, files_unchanged=10)
        assert _has_meaningful_changes(stats) is False

    def test_has_meaningful_changes_with_created(self) -> None:
        """_has_meaningful_changes returns True when files are created."""
        stats = UpdateStats(files_scanned=5, files_created=1)
        assert _has_meaningful_changes(stats) is True

    def test_has_meaningful_changes_with_updated(self) -> None:
        """_has_meaningful_changes returns True when files are updated."""
        stats = UpdateStats(files_scanned=5, files_updated=2)
        assert _has_meaningful_changes(stats) is True

    def test_has_meaningful_changes_with_failed(self) -> None:
        """_has_meaningful_changes returns True when files failed."""
        stats = UpdateStats(files_scanned=5, files_failed=1)
        assert _has_meaningful_changes(stats) is True

    def test_has_meaningful_changes_agent_updated_only(self) -> None:
        """_has_meaningful_changes returns False when only agent_updated changes exist."""
        stats = UpdateStats(files_scanned=5, files_unchanged=3, files_agent_updated=2)
        assert _has_meaningful_changes(stats) is False

    @pytest.mark.asyncio()
    async def test_update_project_skips_reindex_when_no_changes(self, tmp_path: Path) -> None:
        """update_project() does NOT re-index when all files are unchanged."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch(
                "lexibrary.archivist.pipeline.reindex_directories",
            ) as mock_reindex,
        ):
            await update_project(tmp_path, config, archivist)

        # reindex_directories should NOT have been called
        mock_reindex.assert_not_called()

    @pytest.mark.asyncio()
    async def test_update_files_skips_reindex_when_no_changes(self, tmp_path: Path) -> None:
        """update_files() does NOT re-index when all files are unchanged."""
        source = _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        (tmp_path / ".lexibrary").mkdir(parents=True, exist_ok=True)

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch(
                "lexibrary.archivist.pipeline.reindex_directories",
            ) as mock_reindex,
            patch("lexibrary.archivist.pipeline.build_index"),
        ):
            await update_files([source], tmp_path, config, archivist)

        # reindex_directories should NOT have been called
        mock_reindex.assert_not_called()

    @pytest.mark.asyncio()
    async def test_update_project_reindexes_when_files_created(self, tmp_path: Path) -> None:
        """update_project() DOES re-index when files are created."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.NEW_FILE)

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch(
                "lexibrary.archivist.pipeline.reindex_directories",
                return_value=1,
            ) as mock_reindex,
        ):
            await update_project(tmp_path, config, archivist)

        # reindex_directories SHOULD have been called
        mock_reindex.assert_called_once()


# ---------------------------------------------------------------------------
# update_file — IWH awareness
# ---------------------------------------------------------------------------


class TestIWHAwareness:
    """Tests for archivist IWH signal awareness (TG4)."""

    @pytest.mark.asyncio()
    async def test_blocked_signal_skips_file(self, tmp_path: Path) -> None:
        """File in directory with blocked IWH signal returns UNCHANGED."""
        from lexibrary.iwh import write_iwh

        source = _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        config = _make_config()
        archivist = _mock_archivist()

        # Write a blocked IWH signal at the mirror path for src/
        mirror_dir = tmp_path / ".lexibrary" / "designs" / "src"
        mirror_dir.mkdir(parents=True, exist_ok=True)
        write_iwh(mirror_dir, author="agent", scope="blocked", body="do not touch")

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.UNCHANGED
        archivist.generate_design_file.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_incomplete_signal_proceeds(self, tmp_path: Path) -> None:
        """File in directory with incomplete IWH signal is still processed."""
        from lexibrary.iwh import write_iwh

        source = _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        config = _make_config()
        archivist = _mock_archivist(summary="Processed despite incomplete.")

        # Write an incomplete IWH signal
        mirror_dir = tmp_path / ".lexibrary" / "designs" / "src"
        mirror_dir.mkdir(parents=True, exist_ok=True)
        write_iwh(mirror_dir, author="agent", scope="incomplete", body="wip")

        result = await update_file(source, tmp_path, config, archivist)

        # Should proceed — NOT return UNCHANGED
        assert result.change != ChangeLevel.UNCHANGED
        archivist.generate_design_file.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_no_signal_proceeds_normally(self, tmp_path: Path) -> None:
        """File with no IWH signal is processed normally."""
        source = _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        config = _make_config()
        archivist = _mock_archivist(summary="Normal processing.")

        result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.NEW_FILE
        archivist.generate_design_file.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_iwh_disabled_ignores_signals(self, tmp_path: Path) -> None:
        """When config.iwh.enabled=False, blocked signals are ignored."""
        from lexibrary.config.schema import IWHConfig
        from lexibrary.iwh import write_iwh

        source = _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")
        config = _make_config()
        config.iwh = IWHConfig(enabled=False)
        archivist = _mock_archivist(summary="Processed despite blocked signal.")

        # Write a blocked IWH signal
        mirror_dir = tmp_path / ".lexibrary" / "designs" / "src"
        mirror_dir.mkdir(parents=True, exist_ok=True)
        write_iwh(mirror_dir, author="agent", scope="blocked", body="blocked")

        result = await update_file(source, tmp_path, config, archivist)

        # Should NOT be skipped — IWH is disabled
        assert result.change != ChangeLevel.UNCHANGED
        archivist.generate_design_file.assert_awaited_once()


# ---------------------------------------------------------------------------
# dry_run_project / dry_run_files (task 2.10)
# ---------------------------------------------------------------------------


class TestDryRunProject:
    """Tests for dry_run_project() — detection-only preview, no LLM or writes."""

    @pytest.mark.asyncio()
    async def test_detects_changed_files(self, tmp_path: Path) -> None:
        """dry_run_project() returns files that would change."""
        from lexibrary.archivist.pipeline import dry_run_project

        _make_source_file(tmp_path, "src/foo.py", "def bar(): pass")
        _make_source_file(tmp_path, "src/unchanged.py", "x = 1")

        # Create design file for unchanged.py with correct hash
        unchanged_hash = _sha256("x = 1")
        _make_design_file(tmp_path, "src/unchanged.py", source_hash=unchanged_hash)

        config = _make_config(scope_root="src")
        results = await dry_run_project(tmp_path, config)

        # foo.py is NEW_FILE (no design file), unchanged.py is UNCHANGED
        assert len(results) >= 1
        result_paths = {p.name for p, _ in results}
        assert "foo.py" in result_paths
        assert "unchanged.py" not in result_paths

    @pytest.mark.asyncio()
    async def test_empty_for_clean_project(self, tmp_path: Path) -> None:
        """dry_run_project() returns empty list when all files are unchanged."""
        from lexibrary.archivist.pipeline import dry_run_project

        source = _make_source_file(tmp_path, "src/foo.py", "x = 1")

        # Create design file with correct hash
        import hashlib as _hl

        actual_hash = _hl.sha256(source.read_bytes()).hexdigest()
        _make_design_file(tmp_path, "src/foo.py", source_hash=actual_hash)

        config = _make_config(scope_root="src")
        results = await dry_run_project(tmp_path, config)

        assert len(results) == 0

    @pytest.mark.asyncio()
    async def test_no_side_effects(self, tmp_path: Path) -> None:
        """dry_run_project() does not create or modify any files."""
        from lexibrary.archivist.pipeline import dry_run_project

        _make_source_file(tmp_path, "src/foo.py", "def bar(): pass")

        config = _make_config(scope_root="src")

        # Record state before dry run
        lexibrary_dir = tmp_path / ".lexibrary"
        files_before = set(lexibrary_dir.rglob("*")) if lexibrary_dir.exists() else set()

        await dry_run_project(tmp_path, config)

        # Verify no new files created in .lexibrary
        files_after = set(lexibrary_dir.rglob("*")) if lexibrary_dir.exists() else set()
        assert files_after == files_before

    @pytest.mark.asyncio()
    async def test_skips_binary_files(self, tmp_path: Path) -> None:
        """dry_run_project() skips binary files."""
        from lexibrary.archivist.pipeline import dry_run_project

        _make_source_file(tmp_path, "src/foo.py", "x = 1")
        img = tmp_path / "src" / "logo.png"
        img.write_bytes(b"\x89PNG")

        config = _make_config(scope_root="src")
        results = await dry_run_project(tmp_path, config)

        result_paths = {p.name for p, _ in results}
        assert "logo.png" not in result_paths


class TestDryRunFiles:
    """Tests for dry_run_files() — detection-only preview for specific files."""

    @pytest.mark.asyncio()
    async def test_checks_specific_files(self, tmp_path: Path) -> None:
        """dry_run_files() only checks the given file paths."""
        from lexibrary.archivist.pipeline import dry_run_files

        source_a = _make_source_file(tmp_path, "src/a.py", "a = 1")
        source_b = _make_source_file(tmp_path, "src/b.py", "b = 2")

        config = _make_config()
        results = await dry_run_files([source_a, source_b], tmp_path, config)

        # Both are new files (no design files exist)
        assert len(results) == 2
        result_paths = {p.name for p, _ in results}
        assert "a.py" in result_paths
        assert "b.py" in result_paths

    @pytest.mark.asyncio()
    async def test_skips_deleted_files(self, tmp_path: Path) -> None:
        """dry_run_files() skips files that don't exist."""
        from lexibrary.archivist.pipeline import dry_run_files

        source_a = _make_source_file(tmp_path, "src/a.py", "a = 1")
        deleted = tmp_path / "src" / "deleted.py"

        config = _make_config()
        results = await dry_run_files([source_a, deleted], tmp_path, config)

        assert len(results) == 1
        assert results[0][0].name == "a.py"

    @pytest.mark.asyncio()
    async def test_returns_change_levels(self, tmp_path: Path) -> None:
        """dry_run_files() returns correct ChangeLevel values."""
        from lexibrary.archivist.pipeline import dry_run_files

        source = _make_source_file(tmp_path, "src/new.py", "def new(): pass")

        config = _make_config()
        results = await dry_run_files([source], tmp_path, config)

        assert len(results) == 1
        _path, change = results[0]
        assert change == ChangeLevel.NEW_FILE


# ---------------------------------------------------------------------------
# UpdateStats — new lifecycle fields
# ---------------------------------------------------------------------------


class TestUpdateStatsLifecycleFields:
    """Verify new deprecation, rename, and queue fields on UpdateStats."""

    def test_deprecation_fields_default_to_zero(self) -> None:
        stats = UpdateStats()
        assert stats.designs_deprecated == 0
        assert stats.designs_unlinked == 0
        assert stats.designs_deleted_ttl == 0

    def test_rename_fields_default_to_zero(self) -> None:
        stats = UpdateStats()
        assert stats.renames_detected == 0
        assert stats.renames_migrated == 0

    def test_queue_fields_default_to_zero(self) -> None:
        stats = UpdateStats()
        assert stats.queue_processed == 0
        assert stats.queue_failed == 0
        assert stats.queue_remaining == 0

    def test_lifecycle_fields_are_mutable(self) -> None:
        stats = UpdateStats()
        stats.designs_deprecated = 3
        stats.designs_unlinked = 1
        stats.designs_deleted_ttl = 2
        stats.renames_detected = 4
        stats.renames_migrated = 4
        stats.queue_processed = 5
        stats.queue_failed = 1
        stats.queue_remaining = 2
        assert stats.designs_deprecated == 3
        assert stats.designs_unlinked == 1
        assert stats.designs_deleted_ttl == 2
        assert stats.renames_detected == 4
        assert stats.renames_migrated == 4
        assert stats.queue_processed == 5
        assert stats.queue_failed == 1
        assert stats.queue_remaining == 2


# ---------------------------------------------------------------------------
# _run_deprecation_pass — deprecation post-pass integration
# ---------------------------------------------------------------------------


class TestRunDeprecationPass:
    """Integration tests for the deprecation lifecycle post-pass."""

    def test_deprecates_orphaned_committed(self, tmp_path: Path) -> None:
        """Orphaned designs with committed deletions are deprecated."""
        from lexibrary.archivist.pipeline import _run_deprecation_pass

        # Create a design file for a source that does not exist
        _make_design_file(tmp_path, "src/deleted.py")
        config = _make_config()
        stats = UpdateStats()

        with (
            patch(
                "lexibrary.archivist.pipeline.detect_renames",
                return_value=[],
            ),
            patch(
                "lexibrary.archivist.pipeline.hard_delete_expired",
                return_value=[],
            ),
            # Simulate committed deletion (file not tracked by git)
            patch(
                "lexibrary.lifecycle.deprecation._is_committed_deletion",
                return_value=True,
            ),
        ):
            _run_deprecation_pass(tmp_path, config, stats)

        assert stats.designs_deprecated == 1
        assert stats.designs_unlinked == 0

    def test_marks_unlinked_uncommitted(self, tmp_path: Path) -> None:
        """Orphaned designs with uncommitted deletions are marked unlinked."""
        from lexibrary.archivist.pipeline import _run_deprecation_pass

        _make_design_file(tmp_path, "src/removed.py")
        config = _make_config()
        stats = UpdateStats()

        with (
            patch(
                "lexibrary.archivist.pipeline.detect_renames",
                return_value=[],
            ),
            patch(
                "lexibrary.archivist.pipeline.hard_delete_expired",
                return_value=[],
            ),
            patch(
                "lexibrary.lifecycle.deprecation._is_committed_deletion",
                return_value=False,
            ),
        ):
            _run_deprecation_pass(tmp_path, config, stats)

        assert stats.designs_unlinked == 1
        assert stats.designs_deprecated == 0

    def test_ttl_expiry_stats(self, tmp_path: Path) -> None:
        """TTL-expired deletions are counted in stats."""
        from lexibrary.archivist.pipeline import _run_deprecation_pass

        config = _make_config()
        stats = UpdateStats()

        fake_deleted = [
            tmp_path / ".lexibrary" / "designs" / "old1.py.md",
            tmp_path / ".lexibrary" / "designs" / "old2.py.md",
        ]

        with (
            patch(
                "lexibrary.archivist.pipeline.detect_renames",
                return_value=[],
            ),
            patch(
                "lexibrary.archivist.pipeline.detect_orphaned_designs",
                return_value=[],
            ),
            patch(
                "lexibrary.archivist.pipeline.hard_delete_expired",
                return_value=fake_deleted,
            ),
        ):
            _run_deprecation_pass(tmp_path, config, stats)

        assert stats.designs_deleted_ttl == 2

    def test_rename_detection_and_migration(self, tmp_path: Path) -> None:
        """Detected renames are counted and migration is attempted."""
        from lexibrary.archivist.pipeline import _run_deprecation_pass
        from lexibrary.lifecycle.deprecation import RenameMapping

        config = _make_config()
        stats = UpdateStats()

        # Create a design file at the old location
        _make_design_file(tmp_path, "src/old_name.py")
        # Create the new source file
        _make_source_file(tmp_path, "src/new_name.py", "def foo(): pass")

        fake_renames = [
            RenameMapping(old_path=Path("src/old_name.py"), new_path=Path("src/new_name.py")),
        ]

        with (
            patch(
                "lexibrary.archivist.pipeline.detect_renames",
                return_value=fake_renames,
            ),
            patch(
                "lexibrary.archivist.pipeline.detect_orphaned_designs",
                return_value=[],
            ),
            patch(
                "lexibrary.archivist.pipeline.hard_delete_expired",
                return_value=[],
            ),
        ):
            _run_deprecation_pass(tmp_path, config, stats)

        assert stats.renames_detected == 1
        assert stats.renames_migrated == 1

        # Old design file should be gone
        old_design = tmp_path / ".lexibrary" / "designs" / "src" / "old_name.py.md"
        assert not old_design.exists()

        # New design file should exist
        new_design = tmp_path / ".lexibrary" / "designs" / "src" / "new_name.py.md"
        assert new_design.exists()

    def test_rename_no_design_file(self, tmp_path: Path) -> None:
        """Rename with no existing design file does not fail, just skips migration."""
        from lexibrary.archivist.pipeline import _run_deprecation_pass
        from lexibrary.lifecycle.deprecation import RenameMapping

        config = _make_config()
        stats = UpdateStats()

        fake_renames = [
            RenameMapping(old_path=Path("src/gone.py"), new_path=Path("src/new.py")),
        ]

        with (
            patch(
                "lexibrary.archivist.pipeline.detect_renames",
                return_value=fake_renames,
            ),
            patch(
                "lexibrary.archivist.pipeline.detect_orphaned_designs",
                return_value=[],
            ),
            patch(
                "lexibrary.archivist.pipeline.hard_delete_expired",
                return_value=[],
            ),
        ):
            _run_deprecation_pass(tmp_path, config, stats)

        assert stats.renames_detected == 1
        assert stats.renames_migrated == 0

    def test_errors_in_deprecation_do_not_propagate(self, tmp_path: Path) -> None:
        """Errors in deprecation detection are caught and reported, not propagated."""
        from lexibrary.archivist.pipeline import _run_deprecation_pass

        config = _make_config()
        stats = UpdateStats()

        with (
            patch(
                "lexibrary.archivist.pipeline.detect_renames",
                side_effect=RuntimeError("git error"),
            ),
            patch(
                "lexibrary.archivist.pipeline.detect_orphaned_designs",
                side_effect=RuntimeError("scan error"),
            ),
            patch(
                "lexibrary.archivist.pipeline.hard_delete_expired",
                side_effect=RuntimeError("ttl error"),
            ),
        ):
            # Should not raise
            _run_deprecation_pass(tmp_path, config, stats)

        assert stats.error_summary.has_errors()


# ---------------------------------------------------------------------------
# _process_enrichment_queue — queue processing integration
# ---------------------------------------------------------------------------


class TestProcessEnrichmentQueue:
    """Integration tests for enrichment queue processing in the pipeline."""

    @pytest.mark.asyncio()
    async def test_processes_queued_files(self, tmp_path: Path) -> None:
        """Queued files are processed through the pipeline and cleared."""
        from lexibrary.archivist.pipeline import _process_enrichment_queue
        from lexibrary.lifecycle.queue import queue_for_enrichment

        source = _make_source_file(tmp_path, "src/queued.py", "def queued(): pass")
        queue_for_enrichment(tmp_path, source)

        config = _make_config()
        archivist = _mock_archivist(summary="Enriched queued file.")
        stats = UpdateStats()

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            return_value=FileResult(change=ChangeLevel.CONTENT_CHANGED),
        ):
            await _process_enrichment_queue(tmp_path, config, archivist, stats)

        assert stats.queue_processed == 1
        assert stats.queue_failed == 0
        assert stats.queue_remaining == 0

    @pytest.mark.asyncio()
    async def test_empty_queue_is_noop(self, tmp_path: Path) -> None:
        """Empty queue results in no processing."""
        from lexibrary.archivist.pipeline import _process_enrichment_queue

        config = _make_config()
        archivist = _mock_archivist()
        stats = UpdateStats()

        await _process_enrichment_queue(tmp_path, config, archivist, stats)

        assert stats.queue_processed == 0
        assert stats.queue_failed == 0
        assert stats.queue_remaining == 0

    @pytest.mark.asyncio()
    async def test_failed_enrichment_counted(self, tmp_path: Path) -> None:
        """Failed enrichment is counted separately from successful."""
        from lexibrary.archivist.pipeline import _process_enrichment_queue
        from lexibrary.lifecycle.queue import queue_for_enrichment

        source = _make_source_file(tmp_path, "src/fail.py", "def fail(): pass")
        queue_for_enrichment(tmp_path, source)

        config = _make_config()
        archivist = _mock_archivist()
        stats = UpdateStats()

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            return_value=FileResult(change=ChangeLevel.CONTENT_CHANGED, failed=True),
        ):
            await _process_enrichment_queue(tmp_path, config, archivist, stats)

        assert stats.queue_failed == 1
        assert stats.queue_processed == 0

    @pytest.mark.asyncio()
    async def test_missing_source_cleared_from_queue(self, tmp_path: Path) -> None:
        """Queue entries for deleted source files are cleared without error."""
        from lexibrary.archivist.pipeline import _process_enrichment_queue
        from lexibrary.lifecycle.queue import queue_for_enrichment, read_queue

        # Queue a file that does not exist on disk
        missing = tmp_path / "src" / "gone.py"
        queue_for_enrichment(tmp_path, missing)

        config = _make_config()
        archivist = _mock_archivist()
        stats = UpdateStats()

        await _process_enrichment_queue(tmp_path, config, archivist, stats)

        # Should be cleared from the queue since the source is missing
        remaining = read_queue(tmp_path)
        assert len(remaining) == 0
        assert stats.queue_remaining == 0

    @pytest.mark.asyncio()
    async def test_exception_in_update_file_counted_as_failed(self, tmp_path: Path) -> None:
        """Exceptions during enrichment are caught and counted as failures."""
        from lexibrary.archivist.pipeline import _process_enrichment_queue
        from lexibrary.lifecycle.queue import queue_for_enrichment

        source = _make_source_file(tmp_path, "src/boom.py", "raise Exception")
        queue_for_enrichment(tmp_path, source)

        config = _make_config()
        archivist = _mock_archivist()
        stats = UpdateStats()

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=RuntimeError("LLM timeout"),
        ):
            await _process_enrichment_queue(tmp_path, config, archivist, stats)

        assert stats.queue_failed == 1
        assert stats.queue_processed == 0
        assert stats.error_summary.has_errors()


# ---------------------------------------------------------------------------
# update_project — full pipeline integration with deprecation and queue
# ---------------------------------------------------------------------------


class TestUpdateProjectDeprecationIntegration:
    """Verify update_project() calls deprecation post-pass and queue processing."""

    @pytest.mark.asyncio()
    async def test_deprecation_pass_called(self, tmp_path: Path) -> None:
        """update_project() invokes the deprecation post-pass."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
            patch(
                "lexibrary.archivist.pipeline._run_deprecation_pass",
            ) as mock_deprecation,
            patch(
                "lexibrary.archivist.pipeline._process_enrichment_queue",
            ),
            patch("lexibrary.archivist.pipeline.build_index"),
        ):
            stats = await update_project(tmp_path, config, archivist)

        # Deprecation pass should have been called with project_root, config, stats
        mock_deprecation.assert_called_once()
        call_args = mock_deprecation.call_args
        assert call_args[0][0] == tmp_path  # project_root
        assert call_args[0][1] is config  # config
        assert call_args[0][2] is stats  # stats

    @pytest.mark.asyncio()
    async def test_queue_processing_called(self, tmp_path: Path) -> None:
        """update_project() invokes enrichment queue processing."""
        _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
            patch(
                "lexibrary.archivist.pipeline._run_deprecation_pass",
            ),
            patch(
                "lexibrary.archivist.pipeline._process_enrichment_queue",
            ) as mock_queue,
            patch("lexibrary.archivist.pipeline.build_index"),
        ):
            stats = await update_project(tmp_path, config, archivist)

        # Queue processing should have been called
        mock_queue.assert_called_once()
        call_args = mock_queue.call_args
        assert call_args[0][0] == tmp_path  # project_root
        assert call_args[0][1] is config  # config
        assert call_args[0][2] is archivist  # archivist
        assert call_args[0][3] is stats  # stats

    @pytest.mark.asyncio()
    async def test_deprecation_before_linkgraph(self, tmp_path: Path) -> None:
        """Deprecation pass runs before link graph build."""
        _make_source_file(tmp_path, "src/foo.py", "x = 1")

        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        call_order: list[str] = []

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        def track_deprecation(*args: object, **kwargs: object) -> None:
            call_order.append("deprecation")

        async def track_queue(*args: object, **kwargs: object) -> None:
            call_order.append("queue")

        def track_linkgraph(*args: object, **kwargs: object) -> None:
            call_order.append("linkgraph")

        with (
            patch(
                "lexibrary.archivist.pipeline.update_file",
                side_effect=fake_update_file,
            ),
            patch(
                "lexibrary.archivist.pipeline._run_deprecation_pass",
                side_effect=track_deprecation,
            ),
            patch(
                "lexibrary.archivist.pipeline._process_enrichment_queue",
                side_effect=track_queue,
            ),
            patch(
                "lexibrary.archivist.pipeline.build_index",
                side_effect=track_linkgraph,
            ),
        ):
            await update_project(tmp_path, config, archivist)

        # Verify ordering: deprecation -> queue -> linkgraph
        assert call_order == ["deprecation", "queue", "linkgraph"]

    def test_deprecation_pass_handles_internal_errors(self, tmp_path: Path) -> None:
        """_run_deprecation_pass catches errors internally and records them in stats."""
        from lexibrary.archivist.pipeline import _run_deprecation_pass

        config = _make_config(scope_root="src")
        stats = UpdateStats()

        with (
            patch(
                "lexibrary.archivist.pipeline.detect_renames",
                side_effect=RuntimeError("git error"),
            ),
            patch(
                "lexibrary.archivist.pipeline.detect_orphaned_designs",
                side_effect=RuntimeError("scan error"),
            ),
            patch(
                "lexibrary.archivist.pipeline.hard_delete_expired",
                side_effect=RuntimeError("ttl error"),
            ),
        ):
            # Should not raise -- errors are caught internally
            _run_deprecation_pass(tmp_path, config, stats)

        # Errors were caught and recorded in the error summary
        assert stats.error_summary.has_errors()


# ---------------------------------------------------------------------------
# should_skip_llm — size gate tests
# ---------------------------------------------------------------------------


class TestShouldSkipLlm:
    """Tests for the two-tier size gate that prevents wasted LLM calls."""

    def test_small_file_passes(self) -> None:
        """Files under SIZE_GATE_BYTES are never gated, regardless of tokens."""
        from lexibrary.archivist.pipeline import SIZE_GATE_BYTES, should_skip_llm

        # Content is small — well under the byte threshold
        content = "x = 1\n"
        assert len(content.encode()) < SIZE_GATE_BYTES
        assert should_skip_llm(content, len(content.encode()), archivist_max_tokens=5000) is False

    def test_small_file_skips_tokenizer(self) -> None:
        """Files under SIZE_GATE_BYTES must not invoke tiktoken at all."""
        from lexibrary.archivist.pipeline import SIZE_GATE_BYTES, should_skip_llm

        content = "x = 1\n"
        file_size = len(content.encode())
        assert file_size < SIZE_GATE_BYTES

        with patch("lexibrary.archivist.pipeline._get_tiktoken") as mock_tok:
            result = should_skip_llm(content, file_size, archivist_max_tokens=5000)
            assert result is False
            mock_tok.assert_not_called()

    def test_medium_file_passes(self) -> None:
        """A file above SIZE_GATE_BYTES but under the token threshold passes."""
        from lexibrary.archivist.pipeline import (
            SIZE_GATE_BYTES,
            should_skip_llm,
        )

        # Create content that is above the byte gate but well under the
        # token limit.  At archivist_max_tokens=5000, the threshold is
        # 5000 * 5 = 25 000 tokens.  A line like "x = 1\n" is ~4 tokens,
        # so 1000 lines = ~4000 tokens — well under.
        line = "x = 1\n"
        content = line * 3000  # ~18 KB, ~12 000 tokens
        file_size = len(content.encode())
        assert file_size > SIZE_GATE_BYTES

        archivist_max = 5000
        assert should_skip_llm(content, file_size, archivist_max) is False

    def test_large_file_triggers_gate(self) -> None:
        """A file whose tokens exceed archivist_max_tokens * GATE_MULTIPLIER is gated."""
        from lexibrary.archivist.pipeline import (
            SIZE_GATE_BYTES,
            should_skip_llm,
        )

        # Use a very low archivist_max_tokens so we can trigger the gate
        # with a modest amount of content.  threshold = 10 * 5 = 50 tokens.
        archivist_max = 10
        # Create content with enough tokens to exceed the threshold.
        # Each "word " is roughly 1 token; 200 words >> 50 tokens.
        content = "word " * 5000  # ~25 KB, ~5000 tokens >> 50
        file_size = len(content.encode())
        assert file_size > SIZE_GATE_BYTES

        assert should_skip_llm(content, file_size, archivist_max) is True

    def test_uses_offline_tiktoken_not_api(self) -> None:
        """The size gate must use the offline TiktokenCounter, not an API counter."""
        from lexibrary.archivist.pipeline import SIZE_GATE_BYTES, should_skip_llm

        # Build content large enough to pass the byte gate
        content = "word " * 5000
        file_size = len(content.encode())
        assert file_size > SIZE_GATE_BYTES

        # Patch _get_tiktoken to verify it returns a TiktokenCounter
        from lexibrary.tokenizer.tiktoken_counter import TiktokenCounter

        mock_counter = MagicMock(spec=TiktokenCounter)
        mock_counter.count.return_value = 100  # under any reasonable threshold

        with patch("lexibrary.archivist.pipeline._get_tiktoken", return_value=mock_counter):
            should_skip_llm(content, file_size, archivist_max_tokens=5000)
            mock_counter.count.assert_called_once_with(content)

    def test_gate_constants_match_design(self) -> None:
        """Verify the gate constants match the documented design values."""
        from lexibrary.archivist.pipeline import GATE_MULTIPLIER, SIZE_GATE_BYTES

        assert SIZE_GATE_BYTES == 12_288  # 12 KB
        assert GATE_MULTIPLIER == 5


# ---------------------------------------------------------------------------
# Pipeline Integration — size gate skeleton, unlimited bypass,
# SKELETON_ONLY skip/re-enrich, truncation fallback
# ---------------------------------------------------------------------------


class TestPipelineIntegrationSizeGate:
    """Size gate writes skeleton fallback when file is too large."""

    @pytest.mark.asyncio()
    async def test_size_gate_writes_skeleton(self, tmp_path: Path) -> None:
        """When should_skip_llm returns True, a skeleton fallback is written."""
        source = _make_source_file(tmp_path, "src/big.py", "x = 1\n" * 5000)
        config = _make_config()
        archivist = _mock_archivist()

        with patch("lexibrary.archivist.pipeline.should_skip_llm", return_value=True):
            result = await update_file(source, tmp_path, config, archivist)

        assert result.skeleton is True
        assert not result.failed

        # LLM was NOT called
        archivist.generate_design_file.assert_not_awaited()

        # Design file exists with skeleton-fallback marker
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "big.py.md"
        assert design_path.exists()
        content = design_path.read_text()
        assert "skeleton-fallback" in content

    @pytest.mark.asyncio()
    async def test_unlimited_bypasses_size_gate(self, tmp_path: Path) -> None:
        """When unlimited=True, the size gate is skipped and LLM is called."""
        source = _make_source_file(tmp_path, "src/big.py", "def foo(): pass")
        config = _make_config()
        archivist = _mock_archivist(summary="Big module.")

        # should_skip_llm should NOT be called when unlimited=True
        with patch(
            "lexibrary.archivist.pipeline.should_skip_llm",
            side_effect=AssertionError("should_skip_llm should not be called"),
        ):
            result = await update_file(source, tmp_path, config, archivist, unlimited=True)

        assert not result.failed
        assert not result.skeleton
        archivist.generate_design_file.assert_awaited_once()


class TestPipelineIntegrationSkeletonOnly:
    """SKELETON_ONLY change level handling."""

    @pytest.mark.asyncio()
    async def test_skeleton_only_skipped_in_normal_mode(self, tmp_path: Path) -> None:
        """SKELETON_ONLY files are treated as UNCHANGED in normal mode."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Create a skeleton-fallback design file with matching source hash
        _make_design_file(
            tmp_path,
            source_rel,
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
            description="Design file for foo",
            body=(
                "---\n"
                "description: Design file for foo\n"
                "id: DS-001\n"
                "updated_by: skeleton-fallback\n"
                "---\n"
                "\n"
                f"# {source_rel}\n"
                "\n"
                "## Interface Contract\n"
                "\n"
                "```python\ndef bar(): ...\n```\n"
                "\n"
                "## Dependencies\n"
                "\n"
                "(none)\n"
                "\n"
                "## Dependents\n"
                "\n"
                "(none)\n"
            ),
        )

        config = _make_config()
        archivist = _mock_archivist()

        result = await update_file(source, tmp_path, config, archivist)

        # Treated as UNCHANGED -- no LLM call
        assert result.change == ChangeLevel.UNCHANGED
        archivist.generate_design_file.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_skeleton_only_re_enriched_with_unlimited(self, tmp_path: Path) -> None:
        """SKELETON_ONLY files proceed to LLM when unlimited=True."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        # Create a skeleton-fallback design file with matching source hash
        _make_design_file(
            tmp_path,
            source_rel,
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
            description="Design file for foo",
            body=(
                "---\n"
                "description: Design file for foo\n"
                "id: DS-001\n"
                "updated_by: skeleton-fallback\n"
                "---\n"
                "\n"
                f"# {source_rel}\n"
                "\n"
                "## Interface Contract\n"
                "\n"
                "```python\ndef bar(): ...\n```\n"
                "\n"
                "## Dependencies\n"
                "\n"
                "(none)\n"
                "\n"
                "## Dependents\n"
                "\n"
                "(none)\n"
            ),
        )

        config = _make_config()
        archivist = _mock_archivist(summary="Enriched foo module.")

        # unlimited bypasses size gate too, so mock it out
        with patch("lexibrary.archivist.pipeline.should_skip_llm", return_value=False):
            result = await update_file(source, tmp_path, config, archivist, unlimited=True)

        # LLM was called to re-enrich the skeleton
        archivist.generate_design_file.assert_awaited_once()
        assert not result.failed


class TestPipelineIntegrationTruncation:
    """ArchivistTruncationError triggers skeleton fallback."""

    @pytest.mark.asyncio()
    async def test_truncation_writes_skeleton_fallback(self, tmp_path: Path) -> None:
        """When LLM truncates, a skeleton fallback is written instead of failing."""
        from lexibrary.exceptions import ArchivistTruncationError

        source = _make_source_file(tmp_path, "src/trunc.py", "def hello(): pass")
        config = _make_config()
        archivist = _mock_archivist()

        # Make archivist raise truncation error
        archivist.generate_design_file = AsyncMock(
            side_effect=ArchivistTruncationError("Output truncated: stop_reason=length"),
        )

        result = await update_file(source, tmp_path, config, archivist)

        assert result.skeleton is True
        assert not result.failed

        # Design file exists with skeleton-fallback marker
        design_path = tmp_path / ".lexibrary" / "designs" / "src" / "trunc.py.md"
        assert design_path.exists()
        content = design_path.read_text()
        assert "skeleton-fallback" in content


class TestPipelineIntegrationSkeletonStats:
    """files_skeletons counter is tracked in stats."""

    @pytest.mark.asyncio()
    async def test_skeleton_counter_tracked(self, tmp_path: Path) -> None:
        """Skeleton fallbacks increment files_skeletons in UpdateStats."""
        stats = UpdateStats()
        skeleton_result = FileResult(change=ChangeLevel.NEW_FILE, skeleton=True)
        _accumulate_stats(stats, skeleton_result)

        assert stats.files_skeletons == 1
        assert stats.files_created == 1  # still counts as created

    @pytest.mark.asyncio()
    async def test_non_skeleton_does_not_increment(self, tmp_path: Path) -> None:
        """Normal file results do not increment files_skeletons."""
        stats = UpdateStats()
        normal_result = FileResult(change=ChangeLevel.NEW_FILE)
        _accumulate_stats(stats, normal_result)

        assert stats.files_skeletons == 0
        assert stats.files_created == 1


# ---------------------------------------------------------------------------
# Pipeline topology integration — 2-step raw topology generation
# ---------------------------------------------------------------------------


class TestPipelineTopologyIntegration:
    """Pipeline calls generate_raw_topology and logs skill hint."""

    @pytest.mark.asyncio()
    async def test_update_project_calls_generate_raw_topology(self, tmp_path: Path) -> None:
        """update_project invokes generate_raw_topology after processing."""
        _make_source_file(tmp_path, "src/a.py", "# a")
        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        mock_generate = MagicMock(return_value=tmp_path / ".lexibrary" / "tmp" / "raw-topology.md")

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch("lexibrary.archivist.pipeline.reindex_directories", return_value=0),
            patch("lexibrary.archivist.pipeline.generate_raw_topology", mock_generate),
        ):
            await update_project(tmp_path, config, archivist)

        mock_generate.assert_called_once_with(tmp_path)

    @pytest.mark.asyncio()
    async def test_update_project_logs_topology_hint(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """update_project logs raw topology path and skill hint."""
        import logging  # noqa: PLC0415

        _make_source_file(tmp_path, "src/a.py", "# a")
        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch("lexibrary.archivist.pipeline.reindex_directories", return_value=0),
            patch(
                "lexibrary.archivist.pipeline.generate_raw_topology",
                return_value=tmp_path / ".lexibrary" / "tmp" / "raw-topology.md",
            ),
            caplog.at_level(logging.INFO, logger="lexibrary.archivist.pipeline"),
        ):
            await update_project(tmp_path, config, archivist)

        assert any(
            "Raw topology written to .lexibrary/tmp/raw-topology.md" in r.message
            for r in caplog.records
        )
        assert any(
            "Run /topology-builder to generate TOPOLOGY.md" in r.message for r in caplog.records
        )

    @pytest.mark.asyncio()
    async def test_topology_failure_sets_flag(self, tmp_path: Path) -> None:
        """topology_failed flag is set when generate_raw_topology raises."""
        _make_source_file(tmp_path, "src/a.py", "# a")
        config = _make_config(scope_root="src")
        archivist = _mock_archivist()

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with (
            patch("lexibrary.archivist.pipeline.update_file", side_effect=fake_update_file),
            patch("lexibrary.archivist.pipeline.reindex_directories", return_value=0),
            patch(
                "lexibrary.archivist.pipeline.generate_raw_topology",
                side_effect=OSError("disk full"),
            ),
        ):
            stats = await update_project(tmp_path, config, archivist)

        assert stats.topology_failed is True
