"""Tests for the playbook soft-deprecate helper.

Covers :func:`lexibrary.lifecycle.playbook_deprecation.deprecate_playbook`:

- active → deprecated sets the four frontmatter fields (``status``,
  ``deprecated_at``, ``deprecated_reason``, ``superseded_by``) and appends
  the visible ``> **Deprecated:`` body note.
- already-deprecated input is a silent no-op (no re-stamp, no duplicate
  body note, mtime preserved).
- ``superseded_by`` is preserved when provided and omitted when not.
- parse failure / missing file returns ``None`` with no side effects.
- happy-path write is atomic — no ``.tmp`` stragglers remain in the
  playbooks directory.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lexibrary.lifecycle.playbook_deprecation import deprecate_playbook
from lexibrary.playbooks.parser import parse_playbook_file

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


_playbook_id_counter = 0


def _next_playbook_id() -> str:
    global _playbook_id_counter
    _playbook_id_counter += 1
    return f"PB-{_playbook_id_counter:03d}"


def _create_playbook_file(
    project_root: Path,
    slug: str,
    *,
    title: str = "Test Playbook",
    status: str = "active",
    deprecated_at: str | None = None,
    deprecated_reason: str | None = None,
    superseded_by: str | None = None,
    body: str = "## Overview\n\nA test playbook.\n\n## Steps\n\n1. [ ] Do the thing\n",
) -> Path:
    """Create a playbook ``.md`` file in ``.lexibrary/playbooks/``."""
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "---",
        f"title: '{title}'",
        f"id: {_next_playbook_id()}",
        "trigger_files: []",
        "tags: []",
        f"status: {status}",
        "source: user",
    ]
    if deprecated_at is not None:
        lines.append(f"deprecated_at: '{deprecated_at}'")
    if deprecated_reason is not None:
        lines.append(f"deprecated_reason: {deprecated_reason}")
    if superseded_by is not None:
        lines.append(f"superseded_by: {superseded_by}")
    lines.append("---")
    lines.append("")
    lines.append(body)

    playbook_path = playbooks_dir / f"{slug}.md"
    playbook_path.write_text("\n".join(lines), encoding="utf-8")
    return playbook_path


# ---------------------------------------------------------------------------
# deprecate_playbook() — happy-path transitions
# ---------------------------------------------------------------------------


class TestDeprecatePlaybookHappyPath:
    """Active / draft → deprecated transitions."""

    def test_active_to_deprecated_sets_four_fields_and_body_note(self, tmp_path: Path) -> None:
        """Status, deprecated_at, deprecated_reason, superseded_by all set;
        body-note appended.
        """
        playbook_path = _create_playbook_file(
            tmp_path, "version-bump", title="Version Bump", status="active"
        )

        before = datetime.now(UTC).replace(microsecond=0)
        deprecate_playbook(
            playbook_path,
            reason="past_last_verified",
            superseded_by="new-bump",
        )
        after = datetime.now(UTC).replace(microsecond=0)

        updated = parse_playbook_file(playbook_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "past_last_verified"
        assert updated.frontmatter.superseded_by == "new-bump"
        assert updated.frontmatter.deprecated_at is not None
        assert before <= updated.frontmatter.deprecated_at <= after
        assert updated.frontmatter.deprecated_at.microsecond == 0

        # Body-note append is required for playbooks (SHARED_BLOCK_D step 4).
        assert "> **Deprecated:** past_last_verified" in updated.body

    def test_draft_to_deprecated(self, tmp_path: Path) -> None:
        """Draft playbooks are also soft-deprecate eligible."""
        playbook_path = _create_playbook_file(
            tmp_path, "draft-bump", title="Draft Bump", status="draft"
        )

        deprecate_playbook(playbook_path, reason="abandoned")

        updated = parse_playbook_file(playbook_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "abandoned"
        assert updated.frontmatter.deprecated_at is not None
        assert "> **Deprecated:** abandoned" in updated.body

    def test_superseded_by_omitted_when_not_provided(self, tmp_path: Path) -> None:
        """Without ``superseded_by`` kwarg the field stays ``None``."""
        playbook_path = _create_playbook_file(tmp_path, "solo", title="Solo", status="active")

        deprecate_playbook(playbook_path, reason="obsolete")

        updated = parse_playbook_file(playbook_path)
        assert updated is not None
        assert updated.frontmatter.superseded_by is None

    def test_superseded_by_preserved_when_provided(self, tmp_path: Path) -> None:
        """``superseded_by`` kwarg round-trips through the serializer."""
        playbook_path = _create_playbook_file(
            tmp_path, "old-proc", title="Old Procedure", status="active"
        )

        deprecate_playbook(
            playbook_path,
            reason="replaced",
            superseded_by="new-proc",
        )

        updated = parse_playbook_file(playbook_path)
        assert updated is not None
        assert updated.frontmatter.superseded_by == "new-proc"


# ---------------------------------------------------------------------------
# deprecate_playbook() — idempotency
# ---------------------------------------------------------------------------


class TestDeprecatePlaybookIdempotent:
    """Already-deprecated inputs are silent no-ops."""

    def test_already_deprecated_is_noop_timestamp_preserved(self, tmp_path: Path) -> None:
        """Idempotent: already-deprecated input leaves ``deprecated_at`` and
        ``deprecated_reason`` untouched.
        """
        original_iso = "2025-06-01T12:34:56+00:00"
        playbook_path = _create_playbook_file(
            tmp_path,
            "old-pb",
            title="Old PB",
            status="deprecated",
            deprecated_at=original_iso,
            deprecated_reason="original_reason",
        )

        mtime_before = playbook_path.stat().st_mtime_ns
        body_before = playbook_path.read_text(encoding="utf-8")

        deprecate_playbook(
            playbook_path,
            reason="new_reason_should_be_ignored",
            superseded_by="should_not_set",
        )

        # Fields unchanged
        updated = parse_playbook_file(playbook_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "original_reason"
        assert updated.frontmatter.deprecated_at is not None
        assert updated.frontmatter.deprecated_at.isoformat() == original_iso
        assert updated.frontmatter.superseded_by is None

        # No-op: file not rewritten (mtime unchanged).
        mtime_after = playbook_path.stat().st_mtime_ns
        assert mtime_after == mtime_before

        # And the body is byte-for-byte identical — no duplicate
        # ``> **Deprecated:`` note appended.
        body_after = playbook_path.read_text(encoding="utf-8")
        assert body_after == body_before

    def test_already_deprecated_body_note_not_re_appended(self, tmp_path: Path) -> None:
        """When the original body already contains a deprecation note,
        re-deprecating must not duplicate it.
        """
        playbook_path = _create_playbook_file(
            tmp_path,
            "already",
            title="Already",
            status="deprecated",
            deprecated_at="2025-06-01T00:00:00+00:00",
            body="Some overview.\n\n> **Deprecated:** prior_reason\n",
        )

        deprecate_playbook(playbook_path, reason="different_reason")

        text = playbook_path.read_text(encoding="utf-8")
        # Exactly one occurrence of the deprecation blockquote line.
        assert text.count("> **Deprecated:**") == 1
        # And the original reason is preserved.
        assert "prior_reason" in text
        assert "different_reason" not in text


# ---------------------------------------------------------------------------
# deprecate_playbook() — parse-failure / missing-file
# ---------------------------------------------------------------------------


class TestDeprecatePlaybookParseFailure:
    """Parse failure and missing-file paths return ``None`` silently."""

    def test_unparseable_returns_none(self, tmp_path: Path) -> None:
        """Parse failure -> helper returns ``None``, file untouched."""
        playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
        playbooks_dir.mkdir(parents=True)
        bad_path = playbooks_dir / "bad.md"
        bad_path.write_text("not valid yaml frontmatter", encoding="utf-8")

        original = bad_path.read_text(encoding="utf-8")
        result = deprecate_playbook(bad_path, reason="anything")
        assert result is None
        assert bad_path.read_text(encoding="utf-8") == original

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        """Nonexistent playbook path -> ``None``, no side effects."""
        playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
        playbooks_dir.mkdir(parents=True)
        missing = playbooks_dir / "not-there.md"
        assert not missing.exists()

        result = deprecate_playbook(missing, reason="anything")
        assert result is None
        assert not missing.exists()


# ---------------------------------------------------------------------------
# deprecate_playbook() — atomic write
# ---------------------------------------------------------------------------


class TestDeprecatePlaybookAtomicWrite:
    """Happy-path writes are atomic — no temp stragglers."""

    def test_atomic_write_leaves_no_temp_files(self, tmp_path: Path) -> None:
        """Target directory contains exactly the target file after write."""
        playbook_path = _create_playbook_file(
            tmp_path, "atomic-pb", title="Atomic PB", status="active"
        )
        playbooks_dir = playbook_path.parent

        deprecate_playbook(playbook_path, reason="atomic_test")

        entries = sorted(p.name for p in playbooks_dir.iterdir())
        assert entries == ["atomic-pb.md"]

        updated = parse_playbook_file(playbook_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "atomic_test"


# ---------------------------------------------------------------------------
# deprecate_playbook() — preserves other frontmatter
# ---------------------------------------------------------------------------


class TestDeprecatePlaybookPreservesOtherFields:
    """Non-deprecation frontmatter fields survive the mutation."""

    def test_preserves_other_frontmatter_fields(self, tmp_path: Path) -> None:
        playbooks_dir = tmp_path / ".lexibrary" / "playbooks"
        playbooks_dir.mkdir(parents=True, exist_ok=True)
        playbook_path = playbooks_dir / "rich.md"
        playbook_path.write_text(
            "\n".join(
                [
                    "---",
                    "title: 'Rich Playbook'",
                    "id: PB-099",
                    "trigger_files: [pyproject.toml, setup.cfg]",
                    "tags: [release, versioning]",
                    "status: active",
                    "source: user",
                    "estimated_minutes: 15",
                    "last_verified: '2026-03-01'",
                    "aliases: [rich-alias]",
                    "---",
                    "",
                    "Original body content.\n",
                ]
            ),
            encoding="utf-8",
        )

        deprecate_playbook(playbook_path, reason="preservation_check")

        updated = parse_playbook_file(playbook_path)
        assert updated is not None
        assert updated.frontmatter.status == "deprecated"
        assert updated.frontmatter.deprecated_reason == "preservation_check"
        # Unrelated fields preserved:
        assert updated.frontmatter.title == "Rich Playbook"
        assert updated.frontmatter.id == "PB-099"
        assert updated.frontmatter.trigger_files == ["pyproject.toml", "setup.cfg"]
        assert updated.frontmatter.tags == ["release", "versioning"]
        assert updated.frontmatter.estimated_minutes == 15
        assert updated.frontmatter.aliases == ["rich-alias"]
        # Body preserved (plus the deprecation note)
        assert "Original body content." in updated.body
        assert "> **Deprecated:** preservation_check" in updated.body
