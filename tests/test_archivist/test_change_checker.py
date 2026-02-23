"""Tests for archivist change checker."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lexibrary.archivist.change_checker import (
    ChangeLevel,
    _compute_design_content_hash,
    _design_file_path,
    check_change,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _make_design_file(
    tmp_path: Path,
    source_rel: str,
    *,
    source_hash: str = "src_hash_aaa",
    interface_hash: str | None = None,
    design_hash: str | None = None,
    body: str | None = None,
    include_footer: bool = True,
) -> Path:
    """Create a design file at the mirror path within tmp_path.

    If ``body`` is not given, a minimal design file body is generated.
    If ``design_hash`` is None (and ``include_footer`` is True) the
    design_hash is computed from the body content.
    """
    design_dir = tmp_path / ".lexibrary" / Path(source_rel).parent
    design_dir.mkdir(parents=True, exist_ok=True)
    design_path = tmp_path / ".lexibrary" / f"{source_rel}.md"

    if body is None:
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


# ---------------------------------------------------------------------------
# ChangeLevel enum
# ---------------------------------------------------------------------------


class TestChangeLevelEnum:
    """Verify ChangeLevel has exactly six values."""

    def test_all_change_levels_defined(self) -> None:
        expected = {
            "UNCHANGED",
            "AGENT_UPDATED",
            "CONTENT_ONLY",
            "CONTENT_CHANGED",
            "INTERFACE_CHANGED",
            "NEW_FILE",
        }
        actual = {member.name for member in ChangeLevel}
        assert actual == expected


# ---------------------------------------------------------------------------
# _design_file_path
# ---------------------------------------------------------------------------


class TestDesignFilePath:
    def test_mirror_path(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "foo.py"
        result = _design_file_path(source, tmp_path)
        assert result == tmp_path / ".lexibrary" / "src" / "foo.py.md"


# ---------------------------------------------------------------------------
# check_change scenarios
# ---------------------------------------------------------------------------


class TestCheckChangeNewFile:
    """No existing design file -> NEW_FILE."""

    def test_new_file(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "foo.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hello')", encoding="utf-8")

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="abc123",
            interface_hash="iface123",
        )
        assert result == ChangeLevel.NEW_FILE


class TestCheckChangeFooterless:
    """Design file exists but no metadata footer -> AGENT_UPDATED."""

    def test_footerless(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hello')", encoding="utf-8")

        _make_design_file(
            tmp_path,
            source_rel,
            include_footer=False,
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="abc123",
            interface_hash="iface123",
        )
        assert result == ChangeLevel.AGENT_UPDATED


class TestCheckChangeUnchanged:
    """Source file unchanged -> UNCHANGED."""

    def test_unchanged(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hello')", encoding="utf-8")

        source_hash = "matching_hash"
        _make_design_file(
            tmp_path,
            source_rel,
            source_hash=source_hash,
            interface_hash="iface_old",
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash=source_hash,  # matches footer
            interface_hash="iface_new",
        )
        assert result == ChangeLevel.UNCHANGED


class TestCheckChangeAgentUpdated:
    """Source changed AND design file content hash differs from footer -> AGENT_UPDATED."""

    def test_agent_updated(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hello')", encoding="utf-8")

        # Create a design file with a known design_hash
        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_source_hash",
            interface_hash="iface_old",
            design_hash="original_design_hash",  # will differ from actual content hash
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="new_source_hash",  # source changed
            interface_hash="iface_new",
        )
        # design_hash in footer ("original_design_hash") differs from computed hash
        # -> agent edited the design file
        assert result == ChangeLevel.AGENT_UPDATED


class TestCheckChangeContentOnly:
    """Source changed, interface hash same -> CONTENT_ONLY."""

    def test_content_only(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hello')", encoding="utf-8")

        # Build body and compute its hash for the design_hash field
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

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_source_hash",
            interface_hash="same_iface_hash",
            body=body,
            # design_hash=None means it will be auto-computed from body
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="new_source_hash",  # source changed
            interface_hash="same_iface_hash",  # interface unchanged
        )
        assert result == ChangeLevel.CONTENT_ONLY


class TestCheckChangeInterfaceChanged:
    """Source changed, interface hash different -> INTERFACE_CHANGED."""

    def test_interface_changed(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hello')", encoding="utf-8")

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

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_source_hash",
            interface_hash="old_iface_hash",
            body=body,
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="new_source_hash",  # source changed
            interface_hash="new_iface_hash",  # interface changed
        )
        assert result == ChangeLevel.INTERFACE_CHANGED


class TestCheckChangeContentChanged:
    """Non-code file (interface_hash is None) with changed content -> CONTENT_CHANGED."""

    def test_content_changed_non_code(self, tmp_path: Path) -> None:
        source_rel = "docs/readme.md"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Hello", encoding="utf-8")

        body = (
            "---\n"
            "description: Project readme.\n"
            "updated_by: archivist\n"
            "---\n"
            "\n"
            f"# {source_rel}\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```text\nN/A\n```\n"
            "\n"
            "## Dependencies\n"
            "\n"
            "(none)\n"
            "\n"
            "## Dependents\n"
            "\n"
            "(none)\n"
        )

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_content_hash",
            interface_hash=None,  # non-code: no interface hash in footer
            body=body,
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="new_content_hash",  # content changed
            interface_hash=None,  # non-code file
        )
        assert result == ChangeLevel.CONTENT_CHANGED


# ---------------------------------------------------------------------------
# _compute_design_content_hash
# ---------------------------------------------------------------------------


class TestComputeDesignContentHash:
    """Design content hashing excludes footer."""

    def test_footer_excluded_from_hash(self, tmp_path: Path) -> None:
        source_rel = "src/foo.py"
        body = "---\ndescription: Test.\nupdated_by: archivist\n---\n\n# src/foo.py\n"

        # Create design file with footer
        design_path = _make_design_file(
            tmp_path,
            source_rel,
            body=body,
        )

        computed = _compute_design_content_hash(design_path)
        expected = _sha256(body.rstrip("\n"))
        assert computed == expected

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        result = _compute_design_content_hash(tmp_path / "nonexistent.md")
        assert result is None

    def test_footer_update_does_not_change_hash(self, tmp_path: Path) -> None:
        """Verify that updating only the footer does not change the design hash."""
        source_rel = "src/bar.py"
        body = "---\ndescription: Bar module.\nupdated_by: archivist\n---\n\n# src/bar.py\n"

        # Create with one set of footer hashes
        path1 = _make_design_file(
            tmp_path,
            source_rel,
            source_hash="hash_v1",
            body=body,
        )
        hash1 = _compute_design_content_hash(path1)

        # Overwrite with different footer hashes but same body
        path2 = _make_design_file(
            tmp_path,
            source_rel,
            source_hash="hash_v2",
            body=body,
        )
        hash2 = _compute_design_content_hash(path2)

        assert hash1 == hash2
