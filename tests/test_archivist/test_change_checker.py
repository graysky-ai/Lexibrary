"""Tests for archivist change checker."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lexibrary.archivist.change_checker import (
    ChangeLevel,
    _compute_design_content_hash,
    check_change,
)
from lexibrary.utils.paths import mirror_path

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
    design_dir = tmp_path / ".lexibrary" / "designs" / Path(source_rel).parent
    design_dir.mkdir(parents=True, exist_ok=True)
    design_path = tmp_path / ".lexibrary" / "designs" / f"{source_rel}.md"

    if body is None:
        body = (
            "---\n"
            "description: Test file.\n"
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


# ---------------------------------------------------------------------------
# ChangeLevel enum
# ---------------------------------------------------------------------------


class TestChangeLevelEnum:
    """Verify ChangeLevel has exactly seven values."""

    def test_all_change_levels_defined(self) -> None:
        expected = {
            "UNCHANGED",
            "AGENT_UPDATED",
            "CONTENT_ONLY",
            "CONTENT_CHANGED",
            "INTERFACE_CHANGED",
            "NEW_FILE",
            "SKELETON_ONLY",
        }
        actual = {member.name for member in ChangeLevel}
        assert actual == expected


# ---------------------------------------------------------------------------
# mirror_path (was _design_file_path, now delegated to utils.paths)
# ---------------------------------------------------------------------------


class TestDesignFilePath:
    def test_mirror_path(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "foo.py"
        result = mirror_path(tmp_path, source)
        assert result == tmp_path / ".lexibrary" / "designs" / "src" / "foo.py.md"


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
        body = "---\ndescription: Test.\nid: DS-001\nupdated_by: archivist\n---\n\n# src/foo.py\n"

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
        body = (
            "---\ndescription: Bar module.\nid: DS-002\n"
            "updated_by: archivist\n---\n\n# src/bar.py\n"
        )

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


# ---------------------------------------------------------------------------
# SKELETON_ONLY detection
# ---------------------------------------------------------------------------


class TestCheckChangeSkeletonOnly:
    """Skeleton-fallback design files with matching source hash -> SKELETON_ONLY."""

    def test_skeleton_with_matching_hash(self, tmp_path: Path) -> None:
        """A skeleton-fallback file whose source hash matches returns SKELETON_ONLY."""
        source_rel = "src/big_module.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# large file", encoding="utf-8")

        source_hash = "matching_hash"

        body = (
            "---\n"
            "description: Design file for big module\n"
            "id: DS-001\n"
            "updated_by: skeleton-fallback\n"
            "---\n"
            "\n"
            f"# {source_rel}\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\nclass BigModule: ...\n```\n"
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
            source_hash=source_hash,
            interface_hash="iface_hash",
            body=body,
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash=source_hash,  # matches -> would be UNCHANGED normally
            interface_hash="iface_hash",
        )
        assert result == ChangeLevel.SKELETON_ONLY

    def test_skeleton_with_changed_hash(self, tmp_path: Path) -> None:
        """A skeleton-fallback file whose source hash changed falls through to normal detection."""
        source_rel = "src/big_module.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# large file v2", encoding="utf-8")

        body = (
            "---\n"
            "description: Design file for big module\n"
            "id: DS-002\n"
            "updated_by: skeleton-fallback\n"
            "---\n"
            "\n"
            f"# {source_rel}\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\nclass BigModule: ...\n```\n"
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
            source_hash="old_hash",
            interface_hash="old_iface",
            body=body,
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="new_hash",  # source changed -> normal detection
            interface_hash="new_iface",  # interface also changed
        )
        # Source changed + interface changed -> INTERFACE_CHANGED (normal flow)
        assert result == ChangeLevel.INTERFACE_CHANGED

    def test_non_skeleton_file_unaffected(self, tmp_path: Path) -> None:
        """A normal archivist file with matching hash still returns UNCHANGED."""
        source_rel = "src/normal.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# normal file", encoding="utf-8")

        source_hash = "matching_hash"

        body = (
            "---\n"
            "description: Normal module.\n"
            "id: DS-003\n"
            "updated_by: archivist\n"
            "---\n"
            "\n"
            f"# {source_rel}\n"
            "\n"
            "## Interface Contract\n"
            "\n"
            "```python\ndef normal(): ...\n```\n"
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
            source_hash=source_hash,
            interface_hash="iface_hash",
            body=body,
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash=source_hash,  # matches
            interface_hash="iface_hash",
        )
        assert result == ChangeLevel.UNCHANGED


# ---------------------------------------------------------------------------
# Curator / archivist parity — lexictl update treats curator-stamped files
# identically to archivist-stamped files because change detection is hash
# based, not updated_by based.  These tests lock in that invariant so any
# future change_checker change that special-cases updated_by will fail loudly.
# ---------------------------------------------------------------------------


def _parity_body(source_rel: str, updated_by: str) -> str:
    """Minimal design-file body matching _make_design_file's default shape."""
    return (
        "---\n"
        "description: Test file.\n"
        "id: DS-001\n"
        f"updated_by: {updated_by}\n"
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


class TestCuratorArchivistParity:
    """check_change must classify curator-stamped files exactly like archivist-stamped files.

    Curator uses the shared write_contract helper which recomputes
    source_hash / interface_hash / design_hash on write, so a curator-written
    file is just as hash-fresh as an archivist-written file.  The hash-based
    classifier should therefore not distinguish between them.
    """

    def test_unchanged_parity(self, tmp_path: Path) -> None:
        source_rel = "src/parity_unchanged.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hi')", encoding="utf-8")

        source_hash = "matching_hash"
        body = _parity_body(source_rel, "curator")
        _make_design_file(
            tmp_path,
            source_rel,
            source_hash=source_hash,
            interface_hash="iface_old",
            body=body,
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash=source_hash,
            interface_hash="iface_new",
        )
        assert result == ChangeLevel.UNCHANGED

    def test_content_only_parity(self, tmp_path: Path) -> None:
        source_rel = "src/parity_content.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hi')", encoding="utf-8")

        body = _parity_body(source_rel, "curator")
        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_source_hash",
            interface_hash="same_iface_hash",
            body=body,
            # design_hash=None -> auto-computed from body, mirroring write_contract
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="new_source_hash",
            interface_hash="same_iface_hash",
        )
        assert result == ChangeLevel.CONTENT_ONLY

    def test_interface_changed_parity(self, tmp_path: Path) -> None:
        source_rel = "src/parity_interface.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hi')", encoding="utf-8")

        body = _parity_body(source_rel, "curator")
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
            content_hash="new_source_hash",
            interface_hash="new_iface_hash",
        )
        assert result == ChangeLevel.INTERFACE_CHANGED

    def test_agent_updated_still_detected_when_body_drifts(self, tmp_path: Path) -> None:
        """If a curator-stamped body is later mutated out-of-band, the
        design_hash divergence must still trip AGENT_UPDATED — curator is
        hash-fresh only at the moment of the write contract, not forever.
        """
        source_rel = "src/parity_drift.py"
        source = tmp_path / source_rel
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("print('hi')", encoding="utf-8")

        _make_design_file(
            tmp_path,
            source_rel,
            source_hash="old_source_hash",
            interface_hash="iface_old",
            design_hash="stale_design_hash_placeholder",  # forced mismatch
        )

        result = check_change(
            source_path=source,
            project_root=tmp_path,
            content_hash="new_source_hash",
            interface_hash="iface_new",
        )
        assert result == ChangeLevel.AGENT_UPDATED
