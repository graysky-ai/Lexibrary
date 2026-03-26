"""Tests for pipeline safety extensions (G4).

Covers conflict marker detection, design hash re-check, atomic write
usage, the batch update_files() function, deleted file skipping, and
the guarantee that update_files() does NOT regenerate TOPOLOGY.md.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import (
    FileResult,
    update_file,
    update_files,
)
from lexibrary.archivist.service import (
    ArchivistService,
    DesignFileResult,
)
from lexibrary.baml_client.types import DesignFileOutput
from lexibrary.config.schema import LexibraryConfig, TokenBudgetConfig

# ---------------------------------------------------------------------------
# Helpers (shared with test_pipeline.py patterns)
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


def _make_config(scope_root: str = ".", design_file_tokens: int = 400) -> LexibraryConfig:
    """Create a config with given scope_root and token budget."""
    return LexibraryConfig(
        scope_root=scope_root,
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
# Conflict marker detection
# ---------------------------------------------------------------------------


class TestConflictMarkerSkip:
    """update_file() returns failed=True when source has conflict markers."""

    @pytest.mark.asyncio()
    async def test_conflict_markers_skip_llm(self, tmp_path: Path) -> None:
        """Source file with conflict markers is skipped with failed=True."""
        conflicted_content = (
            "def foo():\n<<<<<<< HEAD\n    return 1\n=======\n    return 2\n>>>>>>> branch\n"
        )
        source_rel = "src/conflict.py"
        source = _make_source_file(tmp_path, source_rel, conflicted_content)

        config = _make_config()
        archivist = _mock_archivist()

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("new_hash", "new_iface")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.CONTENT_CHANGED,
            ):
                result = await update_file(source, tmp_path, config, archivist)

        assert result.failed is True
        # LLM should NOT have been called
        archivist.generate_design_file.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_clean_file_proceeds_normally(self, tmp_path: Path) -> None:
        """Source file without conflict markers proceeds to LLM generation."""
        source_rel = "src/clean.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        config = _make_config()
        archivist = _mock_archivist(summary="Clean module.")

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("hash1", "iface1")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.NEW_FILE,
            ):
                result = await update_file(source, tmp_path, config, archivist)

        assert result.failed is False
        archivist.generate_design_file.assert_awaited_once()


# ---------------------------------------------------------------------------
# Design hash re-check (TOCTOU protection)
# ---------------------------------------------------------------------------


class TestDesignHashRecheck:
    """Verify LLM output is discarded when design file is edited during generation."""

    @pytest.mark.asyncio()
    async def test_discard_on_design_hash_mismatch(self, tmp_path: Path) -> None:
        """LLM output is discarded if design_hash changed during generation."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass\n# v2")

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
        original_design_hash = _sha256(body.rstrip("\n"))

        design_path = _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_hash",
            design_hash=original_design_hash,
            body=body,
        )

        config = _make_config()
        archivist = _mock_archivist()

        # Simulate an agent editing the design file during LLM generation
        original_generate = archivist.generate_design_file

        async def edit_during_generation(request: object) -> DesignFileResult:
            # Agent edits the design file while LLM is running
            edited_body = body + "\n\nAgent added this line.\n"
            # Rewrite the design file with different content
            footer_lines = [
                "<!-- lexibrary:meta",
                f"source: {source_rel}",
                "source_hash: old_hash",
                f"design_hash: {original_design_hash}",
                "generated: 2026-01-01T12:00:00",
                "generator: lexibrary-v2",
                "-->",
            ]
            new_text = edited_body + "\n" + "\n".join(footer_lines) + "\n"
            design_path.write_text(new_text, encoding="utf-8")

            return await original_generate(request)

        archivist.generate_design_file = AsyncMock(side_effect=edit_during_generation)

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("new_content_hash", "new_iface")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.CONTENT_CHANGED,
            ):
                result = await update_file(source, tmp_path, config, archivist)

        # LLM output should have been discarded — return AGENT_UPDATED
        assert result.change == ChangeLevel.AGENT_UPDATED
        assert result.aindex_refreshed is False

    @pytest.mark.asyncio()
    async def test_no_discard_when_hash_unchanged(self, tmp_path: Path) -> None:
        """LLM output is written normally if design_hash is unchanged."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass\n# v2")

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
        design_hash = _sha256(body.rstrip("\n"))

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_hash",
            design_hash=design_hash,
            body=body,
        )

        config = _make_config()
        archivist = _mock_archivist(summary="Updated module.")

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("new_content_hash", "new_iface")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.CONTENT_CHANGED,
            ):
                result = await update_file(source, tmp_path, config, archivist)

        # LLM output should be written normally
        assert result.failed is False
        assert result.change == ChangeLevel.CONTENT_CHANGED
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        content = design_path.read_text()
        assert "Updated module." in content

    @pytest.mark.asyncio()
    async def test_new_file_skips_recheck(self, tmp_path: Path) -> None:
        """New files (no prior design file) skip the re-check entirely."""
        source_rel = "src/brand_new.py"
        source = _make_source_file(tmp_path, source_rel, "def fresh(): pass")

        config = _make_config()
        archivist = _mock_archivist(summary="Brand new module.")

        result = await update_file(source, tmp_path, config, archivist)

        # Should write normally — no re-check for new files
        assert result.failed is False
        assert result.change == ChangeLevel.NEW_FILE
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"
        assert design_path.exists()

    @pytest.mark.asyncio()
    async def test_no_design_hash_skips_recheck(self, tmp_path: Path) -> None:
        """If pre-existing design file has no design_hash, re-check is skipped."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass\n# v2")

        # Create a design file with no design_hash in its footer
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

        design_dir = tmp_path / ".lexibrary" / "designs" / Path(source_rel).parent
        design_dir.mkdir(parents=True, exist_ok=True)
        design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"

        # Footer without design_hash
        footer = (
            "<!-- lexibrary:meta\n"
            f"source: {source_rel}\n"
            "source_hash: old_hash\n"
            "generated: 2026-01-01T12:00:00\n"
            "generator: lexibrary-v2\n"
            "-->"
        )
        design_path.write_text(body + "\n" + footer + "\n", encoding="utf-8")

        config = _make_config()
        archivist = _mock_archivist(summary="Updated module.")

        with patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes:
            mock_hashes.return_value = ("new_hash", "new_iface")
            with patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.CONTENT_CHANGED,
            ):
                result = await update_file(source, tmp_path, config, archivist)

        # Should write normally — no design_hash means skip re-check
        assert result.failed is False
        assert result.change == ChangeLevel.CONTENT_CHANGED


# ---------------------------------------------------------------------------
# Atomic write usage
# ---------------------------------------------------------------------------


class TestAtomicWriteUsage:
    """Verify that pipeline uses atomic_write instead of Path.write_text."""

    @pytest.mark.asyncio()
    async def test_design_file_written_atomically(self, tmp_path: Path) -> None:
        """Design file writes go through atomic_write()."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        config = _make_config()
        archivist = _mock_archivist(summary="Foo module.")

        with (
            patch("lexibrary.archivist.pipeline.atomic_write") as mock_atomic,
            patch("lexibrary.archivist.pipeline.compute_hashes") as mock_hashes,
            patch(
                "lexibrary.archivist.pipeline.check_change",
                return_value=ChangeLevel.NEW_FILE,
            ),
        ):
            mock_hashes.return_value = ("hash1", "iface1")
            await update_file(source, tmp_path, config, archivist)

        # atomic_write should have been called (at least once for the design file)
        assert mock_atomic.call_count >= 1
        # The call should write to the design file path
        call_args = mock_atomic.call_args_list[-1]
        target_path = call_args[0][0]
        assert str(target_path).endswith(".md")

    @pytest.mark.asyncio()
    async def test_footer_refresh_uses_atomic_write(self, tmp_path: Path) -> None:
        """AGENT_UPDATED footer refresh uses atomic_write()."""
        source_rel = "src/foo.py"
        source = _make_source_file(tmp_path, source_rel, "def bar(): pass")

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_hash",
            design_hash="agent_changed_this",
        )

        config = _make_config()
        archivist = _mock_archivist()

        with patch("lexibrary.archivist.pipeline.atomic_write") as mock_atomic:
            result = await update_file(source, tmp_path, config, archivist)

        assert result.change == ChangeLevel.AGENT_UPDATED
        # atomic_write should have been called for the footer refresh
        assert mock_atomic.call_count >= 1


# ---------------------------------------------------------------------------
# Batch update_files()
# ---------------------------------------------------------------------------


class TestUpdateFiles:
    """Verify update_files() batch function behavior."""

    @pytest.mark.asyncio()
    async def test_processes_listed_files(self, tmp_path: Path) -> None:
        """update_files() processes each listed file through update_file()."""
        source_a = _make_source_file(tmp_path, "src/a.py", "def a(): pass")
        source_b = _make_source_file(tmp_path, "src/b.py", "def b(): pass")

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
            return FileResult(change=ChangeLevel.NEW_FILE)

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=fake_update_file,
        ):
            stats = await update_files([source_a, source_b], tmp_path, config, archivist)

        assert stats.files_scanned == 2
        assert stats.files_created == 2
        assert {p.name for p in calls} == {"a.py", "b.py"}

    @pytest.mark.asyncio()
    async def test_skips_deleted_files(self, tmp_path: Path) -> None:
        """update_files() silently skips non-existent (deleted) files."""
        existing = _make_source_file(tmp_path, "src/exists.py", "def e(): pass")
        deleted = tmp_path / "src" / "deleted.py"  # does not exist

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

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=fake_update_file,
        ):
            stats = await update_files([existing, deleted], tmp_path, config, archivist)

        # Only the existing file should be scanned
        assert stats.files_scanned == 1
        assert len(calls) == 1
        assert calls[0].name == "exists.py"

    @pytest.mark.asyncio()
    async def test_skips_binary_files(self, tmp_path: Path) -> None:
        """update_files() skips binary-extension files."""
        source = _make_source_file(tmp_path, "src/code.py", "def c(): pass")
        binary = tmp_path / "src" / "image.png"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"\x89PNG")

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

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=fake_update_file,
        ):
            stats = await update_files([source, binary], tmp_path, config, archivist)

        assert stats.files_scanned == 1
        file_names = {p.name for p in calls}
        assert "image.png" not in file_names
        assert "code.py" in file_names

    @pytest.mark.asyncio()
    async def test_skips_lexibrary_contents(self, tmp_path: Path) -> None:
        """update_files() skips files inside .lexibrary/ directory."""
        source = _make_source_file(tmp_path, "src/code.py", "def c(): pass")
        lexi_file = tmp_path / ".lexibrary" / "designs" / "src" / "code.py.md"
        lexi_file.parent.mkdir(parents=True, exist_ok=True)
        lexi_file.write_text("design file content", encoding="utf-8")

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

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=fake_update_file,
        ):
            stats = await update_files([source, lexi_file], tmp_path, config, archivist)

        assert stats.files_scanned == 1
        file_names = {p.name for p in calls}
        assert "code.py.md" not in file_names
        assert "code.py" in file_names

    @pytest.mark.asyncio()
    async def test_no_topology_regeneration(self, tmp_path: Path) -> None:
        """update_files() does NOT generate TOPOLOGY.md."""
        source = _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        config = _make_config()
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
            patch("lexibrary.archivist.pipeline.generate_raw_topology") as mock_topology,
        ):
            await update_files([source], tmp_path, config, archivist)

        mock_topology.assert_not_called()

    @pytest.mark.asyncio()
    async def test_error_handling_per_file(self, tmp_path: Path) -> None:
        """Errors on individual files increment files_failed without stopping."""
        source_a = _make_source_file(tmp_path, "src/a.py", "def a(): pass")
        source_b = _make_source_file(tmp_path, "src/b.py", "def b(): pass")

        config = _make_config()
        archivist = _mock_archivist()

        call_count = 0

        async def flaky_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Simulated failure")
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=flaky_update_file,
        ):
            stats = await update_files([source_a, source_b], tmp_path, config, archivist)

        assert stats.files_scanned == 2
        assert stats.files_failed == 1
        assert stats.files_unchanged == 1

    @pytest.mark.asyncio()
    async def test_progress_callback_invoked(self, tmp_path: Path) -> None:
        """update_files() invokes the progress callback for each processed file."""
        source = _make_source_file(tmp_path, "src/foo.py", "def foo(): pass")

        config = _make_config()
        archivist = _mock_archivist()

        callback_calls: list[tuple[Path, ChangeLevel]] = []

        def callback(path: Path, change: ChangeLevel) -> None:
            callback_calls.append((path, change))

        async def fake_update_file(
            source_path: Path,
            project_root: Path,
            cfg: LexibraryConfig,
            svc: ArchivistService,
            **kwargs: object,
        ) -> FileResult:
            return FileResult(change=ChangeLevel.UNCHANGED)

        with patch(
            "lexibrary.archivist.pipeline.update_file",
            side_effect=fake_update_file,
        ):
            await update_files([source], tmp_path, config, archivist, progress_callback=callback)

        assert len(callback_calls) == 1
        assert callback_calls[0][1] == ChangeLevel.UNCHANGED
