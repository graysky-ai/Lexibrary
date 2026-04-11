"""Tests for the shared curator write contract helper.

Exercises :func:`lexibrary.curator.write_contract.write_design_file_as_curator`
in isolation to verify that it:

1. Stamps ``frontmatter.updated_by = "curator"`` regardless of the
   value the caller set beforehand.
2. Recomputes ``source_hash`` and ``interface_hash`` from the current
   on-disk source file and overwrites any stale values the caller
   provided on the in-memory DesignFile.
3. Delegates to :func:`serialize_design_file` (which computes the
   ``design_hash`` footer field) and writes via :func:`atomic_write`
   (so readers never observe a partially-written file).
4. Propagates errors from hash computation or atomic write.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
    parse_design_file_metadata,
)
from lexibrary.curator.write_contract import write_design_file_as_curator
from lexibrary.utils.hashing import hash_file


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with a .lexibrary/designs layout."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".lexibrary").mkdir()
    (project / ".lexibrary" / "designs").mkdir()
    return project


def _make_source(project: Path, rel_path: str, content: str) -> Path:
    """Create a source file under *project* and return its absolute path."""
    src = project / rel_path
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(content, encoding="utf-8")
    return src


def _make_design_file_obj(
    source_rel: str,
    *,
    stale_source_hash: str = "old_source_hash",
    stale_interface_hash: str | None = "old_interface_hash",
    updated_by: str = "archivist",
) -> DesignFile:
    """Build an in-memory DesignFile with deliberately stale metadata."""
    return DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description="Test design file",
            id=source_rel.replace("/", "-").replace(".", "-"),
            updated_by=updated_by,  # type: ignore[arg-type]
            status="active",
        ),
        summary="Test summary",
        interface_contract="def foo(): ...",
        dependencies=[],
        dependents=[],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=stale_source_hash,
            interface_hash=stale_interface_hash,
            generated=datetime.now(UTC),
            generator="curator-test",
        ),
    )


class TestWriteDesignFileAsCurator:
    """Unit tests for ``write_design_file_as_curator``."""

    def test_write_design_file_sets_updated_by_curator(self, tmp_path: Path) -> None:
        """Helper stamps ``updated_by="curator"`` regardless of input value."""
        project = _setup_project(tmp_path)
        _make_source(project, "src/foo.py", "def foo(): pass\n")
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        # Caller hands us a DesignFile with updated_by="archivist" --
        # the helper MUST overwrite it to "curator".
        df = _make_design_file_obj("src/foo.py", updated_by="archivist")

        write_design_file_as_curator(df, design_path, project)

        # The on-disk file reflects curator authorship.
        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.updated_by == "curator"

        # The in-memory object was also mutated so the caller sees
        # the final authorship without re-parsing.
        assert df.frontmatter.updated_by == "curator"

    def test_write_design_file_overrides_maintainer_updated_by(self, tmp_path: Path) -> None:
        """Caller-provided ``updated_by='maintainer'`` is still rewritten."""
        project = _setup_project(tmp_path)
        _make_source(project, "src/foo.py", "def foo(): pass\n")
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        df = _make_design_file_obj("src/foo.py", updated_by="maintainer")
        write_design_file_as_curator(df, design_path, project)

        fm = parse_design_file_frontmatter(design_path)
        assert fm is not None
        assert fm.updated_by == "curator"

    def test_write_design_file_recomputes_hashes(self, tmp_path: Path) -> None:
        """Helper replaces stale ``source_hash`` with the current hash."""
        project = _setup_project(tmp_path)
        source_content = "def foo(): pass\n"
        source = _make_source(project, "src/foo.py", source_content)
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        df = _make_design_file_obj(
            "src/foo.py",
            stale_source_hash="bogus_old_hash",
            stale_interface_hash="bogus_old_interface",
        )
        write_design_file_as_curator(df, design_path, project)

        # On-disk metadata shows fresh hashes.
        metadata = parse_design_file_metadata(design_path)
        assert metadata is not None
        expected_source_hash = hash_file(source)
        assert metadata.source_hash == expected_source_hash
        # interface_hash either becomes a new hash or None (if the
        # parser can't compute one); it MUST NOT remain the bogus
        # caller-provided value.
        assert metadata.interface_hash != "bogus_old_interface"

        # In-memory DesignFile was mutated with the same fresh values.
        assert df.metadata.source_hash == expected_source_hash
        assert df.metadata.interface_hash != "bogus_old_interface"

    def test_write_design_file_design_hash_populated_by_serializer(self, tmp_path: Path) -> None:
        """Helper lets the serializer compute ``design_hash`` for the footer."""
        project = _setup_project(tmp_path)
        _make_source(project, "src/foo.py", "def foo(): pass\n")
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        df = _make_design_file_obj("src/foo.py")
        write_design_file_as_curator(df, design_path, project)

        metadata = parse_design_file_metadata(design_path)
        assert metadata is not None
        assert metadata.design_hash is not None
        # SHA-256 hex digest is 64 characters.
        assert len(metadata.design_hash) == 64

    def test_write_design_file_atomic(self, tmp_path: Path) -> None:
        """Helper delegates to ``atomic_write`` rather than a direct write."""
        project = _setup_project(tmp_path)
        _make_source(project, "src/foo.py", "def foo(): pass\n")
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        df = _make_design_file_obj("src/foo.py")

        with patch("lexibrary.curator.write_contract.atomic_write") as mock_write:
            write_design_file_as_curator(df, design_path, project)

            mock_write.assert_called_once()
            call_args = mock_write.call_args
            # First positional arg is the target path.
            assert call_args[0][0] == design_path
            # Second positional arg is the serialized content string.
            assert isinstance(call_args[0][1], str)
            assert len(call_args[0][1]) > 0

    def test_write_design_file_serializes_before_writing(self, tmp_path: Path) -> None:
        """Helper delegates to ``serialize_design_file`` for content generation."""
        project = _setup_project(tmp_path)
        _make_source(project, "src/foo.py", "def foo(): pass\n")
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        df = _make_design_file_obj("src/foo.py")

        with patch("lexibrary.curator.write_contract.serialize_design_file") as mock_serialize:
            mock_serialize.return_value = "---\nid: test\n---\n# body\n"
            # Patch atomic_write too so we do not actually touch disk
            # and risk serializer output drift.
            with patch("lexibrary.curator.write_contract.atomic_write"):
                write_design_file_as_curator(df, design_path, project)

            mock_serialize.assert_called_once()
            # The DesignFile passed to serialize_design_file should
            # already have updated_by="curator" and fresh hashes.
            passed_df = mock_serialize.call_args[0][0]
            assert passed_df is df
            assert passed_df.frontmatter.updated_by == "curator"

    def test_write_design_file_roundtrip_parse(self, tmp_path: Path) -> None:
        """Round-trip: written file can be re-parsed into a DesignFile."""
        project = _setup_project(tmp_path)
        _make_source(project, "src/foo.py", "def foo(): pass\n")
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        df = _make_design_file_obj("src/foo.py")
        df.interface_contract = "def foo() -> None: ..."
        # NOTE: the line-oriented design file parser derives ``summary``
        # from ``frontmatter.description``, so we round-trip the
        # description field to verify the parse path.
        df.frontmatter.description = "Roundtrip description"

        write_design_file_as_curator(df, design_path, project)

        parsed = parse_design_file(design_path)
        assert parsed is not None
        assert parsed.frontmatter.updated_by == "curator"
        assert parsed.frontmatter.description == "Roundtrip description"
        assert parsed.summary == "Roundtrip description"
        assert "def foo() -> None" in parsed.interface_contract

    def test_write_design_file_missing_source_raises(self, tmp_path: Path) -> None:
        """If the source file does not exist, hash computation raises."""
        project = _setup_project(tmp_path)
        # NOTE: deliberately do NOT create src/foo.py.
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        df = _make_design_file_obj("src/foo.py")

        # ``compute_hashes`` calls ``hash_file`` which raises
        # ``FileNotFoundError`` (an ``OSError`` subclass) when the
        # source is missing.  The helper must not swallow this.
        with pytest.raises(OSError):
            write_design_file_as_curator(df, design_path, project)

    def test_write_design_file_resolves_source_from_project_root(self, tmp_path: Path) -> None:
        """source_path (relative) is joined with project_root for hashing."""
        project = _setup_project(tmp_path)
        # Create source at a nested path to prove relative join works.
        _make_source(
            project,
            "src/lexibrary/foo.py",
            "def foo(): pass\n",
        )
        design_path = project / ".lexibrary" / "designs" / "src" / "lexibrary" / "foo.py.md"

        df = _make_design_file_obj("src/lexibrary/foo.py")
        write_design_file_as_curator(df, design_path, project)

        metadata = parse_design_file_metadata(design_path)
        assert metadata is not None
        assert metadata.source_hash == hash_file(project / "src" / "lexibrary" / "foo.py")

    def test_write_design_file_atomic_no_partial_file_on_error(self, tmp_path: Path) -> None:
        """If atomic_write raises, no stray temp file is left behind."""
        project = _setup_project(tmp_path)
        _make_source(project, "src/foo.py", "def foo(): pass\n")
        design_path = project / ".lexibrary" / "designs" / "src" / "foo.py.md"

        df = _make_design_file_obj("src/foo.py")

        with (
            patch(
                "lexibrary.curator.write_contract.atomic_write",
                side_effect=OSError("disk full"),
            ),
            pytest.raises(OSError, match="disk full"),
        ):
            write_design_file_as_curator(df, design_path, project)

        # Target file was never created.
        assert not design_path.exists()
