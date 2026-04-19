"""Tests for concept hard deletion (TTL expiry, reference protection, comment cleanup).

Tests for ``lexibrary.lifecycle.concept_deprecation``:
- TTL expiry checking for deprecated concepts
- Pre-deletion reference check (active artefacts still referencing the concept)
- Hard deletion of concept .md files and sibling .comments.yaml files
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from lexibrary.lifecycle.concept_deprecation import (
    ConceptDeletionResult,
    check_concept_ttl_expiry,
    deprecate_concept,
    find_concept_references,
    hard_delete_expired_concepts,
)
from lexibrary.wiki.parser import parse_concept_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_concept_id_counter = 0


def _next_concept_id() -> str:
    global _concept_id_counter
    _concept_id_counter += 1
    return f"CN-{_concept_id_counter:03d}"


def _create_concept_file(
    project_root: Path,
    slug: str,
    *,
    title: str = "Test Concept",
    status: str = "active",
    aliases: list[str] | None = None,
    superseded_by: str | None = None,
    deprecated_at: datetime | None = None,
    body: str = "Test concept body.\n",
) -> Path:
    """Create a concept .md file in .lexibrary/concepts/."""
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)

    concept_path = concepts_dir / f"{slug}.md"

    alias_str = ", ".join(aliases) if aliases else ""
    lines = [
        "---",
        f"title: {title}",
        f"id: {_next_concept_id()}",
        f"aliases: [{alias_str}]",
        "tags: []",
        f"status: {status}",
    ]
    if superseded_by is not None:
        lines.append(f"superseded_by: {superseded_by}")
    if deprecated_at is not None:
        lines.append(f"deprecated_at: '{deprecated_at.isoformat()}'")
    lines.append("---")
    lines.append("")
    lines.append(body)

    concept_path.write_text("\n".join(lines), encoding="utf-8")
    return concept_path


def _create_comment_file(concept_path: Path) -> Path:
    """Create a sibling .comments.yaml file for a concept."""
    comment_path = concept_path.with_suffix(".comments.yaml")
    comment_path.write_text(
        "comments:\n  - body: 'A test comment'\n    date: '2026-01-01T00:00:00+00:00'\n",
        encoding="utf-8",
    )
    return comment_path


def _create_design_file_with_wikilinks(
    project_root: Path,
    source_rel: str,
    wikilinks: list[str],
    *,
    status: str = "active",
) -> Path:
    """Create a minimal design file with wikilinks.

    Uses a simplified format that the design file parser can handle.
    """
    from lexibrary.artifacts.design_file import (
        DesignFile,
        DesignFileFrontmatter,
        StalenessMetadata,
    )
    from lexibrary.artifacts.design_file_serializer import serialize_design_file
    from lexibrary.utils.paths import mirror_path

    design_path = mirror_path(project_root, Path(source_rel))
    design_path.parent.mkdir(parents=True, exist_ok=True)

    data = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id="DS-001",
            updated_by="archivist",
            status=status,
        ),
        summary=f"Design for {source_rel}",
        interface_contract="def example(): ...",
        dependencies=[],
        dependents=[],
        wikilinks=wikilinks,
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash="abc123",
            interface_hash=None,
            design_hash="placeholder",
            generated=datetime(2026, 1, 1, tzinfo=UTC),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(data), encoding="utf-8")
    return design_path


# ---------------------------------------------------------------------------
# check_concept_ttl_expiry()
# ---------------------------------------------------------------------------


class TestCheckConceptTTLExpiry:
    """Tests for check_concept_ttl_expiry()."""

    def test_not_expired(self, tmp_path: Path) -> None:
        """10 commits ago with TTL of 50 -- not expired."""
        concept_path = _create_concept_file(
            tmp_path,
            "old-concept",
            title="Old Concept",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            return_value=10,
        ):
            result = check_concept_ttl_expiry(concept_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_expired(self, tmp_path: Path) -> None:
        """60 commits ago with TTL of 50 -- expired."""
        concept_path = _create_concept_file(
            tmp_path,
            "expired-concept",
            title="Expired Concept",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            return_value=60,
        ):
            result = check_concept_ttl_expiry(concept_path, tmp_path, ttl_commits=50)
        assert result is True

    def test_exactly_at_ttl_not_expired(self, tmp_path: Path) -> None:
        """Exactly at TTL boundary -- not expired (must exceed, not equal)."""
        concept_path = _create_concept_file(
            tmp_path,
            "boundary-concept",
            title="Boundary Concept",
            status="deprecated",
            deprecated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            return_value=50,
        ):
            result = check_concept_ttl_expiry(concept_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_active_concept_returns_false(self, tmp_path: Path) -> None:
        """Active concept -- not eligible for TTL expiry."""
        concept_path = _create_concept_file(
            tmp_path, "active-concept", title="Active", status="active"
        )
        result = check_concept_ttl_expiry(concept_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_deprecated_without_timestamp_returns_false(self, tmp_path: Path) -> None:
        """Deprecated but no deprecated_at -- cannot check TTL."""
        concept_path = _create_concept_file(
            tmp_path, "no-timestamp", title="No Timestamp", status="deprecated"
        )
        result = check_concept_ttl_expiry(concept_path, tmp_path, ttl_commits=50)
        assert result is False

    def test_unparseable_file_returns_false(self, tmp_path: Path) -> None:
        """Unparseable file returns False."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        concepts_dir.mkdir(parents=True)
        bad_file = concepts_dir / "bad.md"
        bad_file.write_text("not valid yaml frontmatter", encoding="utf-8")
        result = check_concept_ttl_expiry(bad_file, tmp_path, ttl_commits=50)
        assert result is False


# ---------------------------------------------------------------------------
# find_concept_references()
# ---------------------------------------------------------------------------


class TestFindConceptReferences:
    """Tests for find_concept_references()."""

    def test_no_references(self, tmp_path: Path) -> None:
        """No artefacts reference the concept -- empty list."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        refs = find_concept_references("Orphaned Concept", [], tmp_path, lexibrary_dir)
        assert refs == []

    def test_design_file_references_by_title(self, tmp_path: Path) -> None:
        """Design file wikilink matches concept title."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        _create_design_file_with_wikilinks(tmp_path, "src/module.py", ["My Concept"])

        refs = find_concept_references("My Concept", [], tmp_path, lexibrary_dir)
        assert len(refs) == 1
        assert "src/module.py.md" in refs[0]

    def test_design_file_references_by_alias(self, tmp_path: Path) -> None:
        """Design file wikilink matches concept alias."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        _create_design_file_with_wikilinks(tmp_path, "src/module.py", ["my_alias"])

        refs = find_concept_references("My Concept", ["my_alias"], tmp_path, lexibrary_dir)
        assert len(refs) == 1

    def test_deprecated_design_excluded(self, tmp_path: Path) -> None:
        """Deprecated design files are excluded from reference check."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        _create_design_file_with_wikilinks(
            tmp_path, "src/old.py", ["My Concept"], status="deprecated"
        )

        refs = find_concept_references("My Concept", [], tmp_path, lexibrary_dir)
        assert refs == []

    def test_active_concept_references_in_body(self, tmp_path: Path) -> None:
        """Another active concept's body contains a wikilink to the target."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        _create_concept_file(
            tmp_path,
            "referencing-concept",
            title="Referencing Concept",
            status="active",
            body="This references [[Target Concept]] in the body.\n",
        )

        refs = find_concept_references("Target Concept", [], tmp_path, lexibrary_dir)
        assert len(refs) == 1
        assert "referencing-concept.md" in refs[0]

    def test_deprecated_concept_excluded_from_references(self, tmp_path: Path) -> None:
        """Deprecated concepts are excluded from reference checking."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        _create_concept_file(
            tmp_path,
            "deprecated-referrer",
            title="Deprecated Referrer",
            status="deprecated",
            body="References [[Target Concept]] but is deprecated.\n",
        )

        refs = find_concept_references("Target Concept", [], tmp_path, lexibrary_dir)
        assert refs == []

    def test_self_reference_excluded(self, tmp_path: Path) -> None:
        """A concept does not count as referencing itself."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        _create_concept_file(
            tmp_path,
            "self-ref",
            title="Self Ref",
            status="active",
            body="References [[Self Ref]] in own body.\n",
        )

        refs = find_concept_references("Self Ref", [], tmp_path, lexibrary_dir)
        assert refs == []


# ---------------------------------------------------------------------------
# hard_delete_expired_concepts()
# ---------------------------------------------------------------------------


class TestHardDeleteExpiredConcepts:
    """Tests for hard_delete_expired_concepts()."""

    def test_deletes_expired_concept(self, tmp_path: Path) -> None:
        """Expired deprecated concept is deleted."""
        concept_path = _create_concept_file(
            tmp_path,
            "expired",
            title="Expired",
            status="deprecated",
            deprecated_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            return_value=100,
        ):
            result = hard_delete_expired_concepts(tmp_path, lexibrary_dir, ttl_commits=50)

        assert concept_path in result.deleted
        assert not concept_path.exists()

    def test_preserves_non_expired_concept(self, tmp_path: Path) -> None:
        """Non-expired deprecated concept is preserved."""
        concept_path = _create_concept_file(
            tmp_path,
            "recent",
            title="Recent",
            status="deprecated",
            deprecated_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            return_value=10,
        ):
            result = hard_delete_expired_concepts(tmp_path, lexibrary_dir, ttl_commits=50)

        assert result.deleted == []
        assert concept_path.exists()

    def test_preserves_active_concept(self, tmp_path: Path) -> None:
        """Active concepts are never deleted."""
        concept_path = _create_concept_file(tmp_path, "active", title="Active", status="active")
        lexibrary_dir = tmp_path / ".lexibrary"

        result = hard_delete_expired_concepts(tmp_path, lexibrary_dir, ttl_commits=50)

        assert result.deleted == []
        assert concept_path.exists()

    def test_deletes_sibling_comment_file(self, tmp_path: Path) -> None:
        """Sibling .comments.yaml is deleted along with the concept."""
        concept_path = _create_concept_file(
            tmp_path,
            "with-comments",
            title="With Comments",
            status="deprecated",
            deprecated_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        comment_path = _create_comment_file(concept_path)
        lexibrary_dir = tmp_path / ".lexibrary"

        assert comment_path.exists()

        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            return_value=100,
        ):
            result = hard_delete_expired_concepts(tmp_path, lexibrary_dir, ttl_commits=50)

        assert concept_path in result.deleted
        assert not concept_path.exists()
        assert comment_path in result.comments_deleted
        assert not comment_path.exists()

    def test_skips_referenced_concept(self, tmp_path: Path) -> None:
        """Expired concept with active references is not deleted."""
        concept_path = _create_concept_file(
            tmp_path,
            "referenced",
            title="Referenced Concept",
            status="deprecated",
            deprecated_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        # Create a design file that references this concept
        _create_design_file_with_wikilinks(tmp_path, "src/module.py", ["Referenced Concept"])

        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            return_value=100,
        ):
            result = hard_delete_expired_concepts(tmp_path, lexibrary_dir, ttl_commits=50)

        assert result.deleted == []
        assert len(result.skipped_referenced) == 1
        assert result.skipped_referenced[0][0] == concept_path
        assert concept_path.exists()

    def test_empty_when_no_concepts_dir(self, tmp_path: Path) -> None:
        """Returns empty result when concepts/ directory doesn't exist."""
        lexibrary_dir = tmp_path / ".lexibrary"
        lexibrary_dir.mkdir(parents=True, exist_ok=True)

        result = hard_delete_expired_concepts(tmp_path, lexibrary_dir, ttl_commits=50)

        assert result.deleted == []
        assert result.skipped_referenced == []
        assert result.comments_deleted == []

    def test_mixed_expired_and_non_expired(self, tmp_path: Path) -> None:
        """Mix of expired and non-expired deprecated concepts."""
        expired_path = _create_concept_file(
            tmp_path,
            "old-concept",
            title="Old Concept",
            status="deprecated",
            deprecated_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        recent_path = _create_concept_file(
            tmp_path,
            "recent-concept",
            title="Recent Concept",
            status="deprecated",
            deprecated_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        def mock_count(root: Path, since_iso: str) -> int:
            if "2025" in since_iso:
                return 100  # old -- expired
            return 5  # recent -- not expired

        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            side_effect=mock_count,
        ):
            result = hard_delete_expired_concepts(tmp_path, lexibrary_dir, ttl_commits=50)

        assert expired_path in result.deleted
        assert not expired_path.exists()
        assert recent_path.exists()

    def test_comment_file_absent_still_succeeds(self, tmp_path: Path) -> None:
        """Deletion succeeds even when no .comments.yaml exists."""
        concept_path = _create_concept_file(
            tmp_path,
            "no-comments",
            title="No Comments",
            status="deprecated",
            deprecated_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
        lexibrary_dir = tmp_path / ".lexibrary"

        # No comment file created
        comment_path = concept_path.with_suffix(".comments.yaml")
        assert not comment_path.exists()

        with patch(
            "lexibrary.lifecycle.concept_deprecation._count_commits_since",
            return_value=100,
        ):
            result = hard_delete_expired_concepts(tmp_path, lexibrary_dir, ttl_commits=50)

        assert concept_path in result.deleted
        assert not concept_path.exists()
        assert result.comments_deleted == []


# ---------------------------------------------------------------------------
# ConceptDeletionResult dataclass
# ---------------------------------------------------------------------------


class TestConceptDeletionResult:
    """Tests for ConceptDeletionResult dataclass."""

    def test_empty_result(self) -> None:
        result = ConceptDeletionResult(deleted=[], skipped_referenced=[], comments_deleted=[])
        assert result.deleted == []
        assert result.skipped_referenced == []
        assert result.comments_deleted == []

    def test_populated_result(self) -> None:
        result = ConceptDeletionResult(
            deleted=[Path("/concepts/a.md")],
            skipped_referenced=[(Path("/concepts/b.md"), ["design.md"])],
            comments_deleted=[Path("/concepts/a.comments.yaml")],
        )
        assert len(result.deleted) == 1
        assert len(result.skipped_referenced) == 1
        assert len(result.comments_deleted) == 1


# ---------------------------------------------------------------------------
# deprecate_concept()
# ---------------------------------------------------------------------------


class TestDeprecateConcept:
    """Tests for the soft-deprecate helper ``deprecate_concept``."""

    def test_active_to_deprecated_sets_four_fields(self, tmp_path: Path) -> None:
        """Active concept -> deprecated: status, deprecated_at, deprecated_reason,
        superseded_by."""
        concept_path = _create_concept_file(
            tmp_path,
            "to-deprecate",
            title="To Deprecate",
            status="active",
        )

        deprecate_concept(
            concept_path,
            reason="no_inbound_links",
            superseded_by="Scope Root",
        )

        reloaded = parse_concept_file(concept_path)
        assert reloaded is not None
        assert reloaded.frontmatter.status == "deprecated"
        assert reloaded.frontmatter.deprecated_at is not None
        # microsecond-zero invariant per spec
        assert reloaded.frontmatter.deprecated_at.microsecond == 0
        assert reloaded.frontmatter.deprecated_reason == "no_inbound_links"
        assert reloaded.frontmatter.superseded_by == "Scope Root"

    def test_active_to_deprecated_without_supersession(self, tmp_path: Path) -> None:
        """reason only -- superseded_by stays None."""
        concept_path = _create_concept_file(
            tmp_path,
            "plain-deprecate",
            title="Plain Deprecate",
            status="active",
        )

        deprecate_concept(concept_path, reason="merged")

        reloaded = parse_concept_file(concept_path)
        assert reloaded is not None
        assert reloaded.frontmatter.status == "deprecated"
        assert reloaded.frontmatter.deprecated_reason == "merged"
        assert reloaded.frontmatter.superseded_by is None

    def test_already_deprecated_is_noop(self, tmp_path: Path) -> None:
        """Already deprecated -> no-op; deprecated_at unchanged, no raise."""
        original_stamp = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        concept_path = _create_concept_file(
            tmp_path,
            "already-dep",
            title="Already Deprecated",
            status="deprecated",
            deprecated_at=original_stamp,
        )

        # Should not raise ValueError -- idempotent no-op semantics.
        deprecate_concept(
            concept_path,
            reason="different_reason",
            superseded_by="Some Other Concept",
        )

        reloaded = parse_concept_file(concept_path)
        assert reloaded is not None
        assert reloaded.frontmatter.status == "deprecated"
        # deprecated_at MUST be unchanged (preserves downstream TTL math).
        assert reloaded.frontmatter.deprecated_at == original_stamp
        # deprecated_reason MUST be unchanged from its pre-call value (None in
        # this fixture -- the concept was deprecated but never had a reason
        # recorded).
        assert reloaded.frontmatter.deprecated_reason is None
        # superseded_by MUST be unchanged.
        assert reloaded.frontmatter.superseded_by is None

    def test_unparseable_returns_none(self, tmp_path: Path) -> None:
        """Unparseable file -> returns None without raising."""
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        concepts_dir.mkdir(parents=True)
        bad_file = concepts_dir / "bad.md"
        # A file that is not valid frontmatter at all.
        bad_file.write_text("not valid yaml frontmatter", encoding="utf-8")
        original_contents = bad_file.read_text(encoding="utf-8")

        # Should return silently -- no raise.
        deprecate_concept(bad_file, reason="whatever")

        # Unparseable file is left untouched.
        assert bad_file.read_text(encoding="utf-8") == original_contents

    def test_atomic_write_leaves_no_temp_file(self, tmp_path: Path) -> None:
        """Successful write leaves the concept at the target path and no temp
        files lingering in the concepts dir."""
        concept_path = _create_concept_file(
            tmp_path,
            "atomic-test",
            title="Atomic Test",
            status="active",
        )

        deprecate_concept(concept_path, reason="test_reason")

        # Target file exists and is the only .md in the dir.
        concepts_dir = concept_path.parent
        md_files = sorted(concepts_dir.glob("*.md"))
        assert md_files == [concept_path]
        # No stray temp files from the atomic write.
        tmp_files = list(concepts_dir.glob("*.tmp"))
        assert tmp_files == []

    def test_atomic_write_preserves_original_on_serializer_failure(self, tmp_path: Path) -> None:
        """If serializer raises mid-write, the original file is untouched.

        Simulates atomicity: ``atomic_write`` writes to a temp file then
        ``os.replace``\\ s into the target.  If the serializer call itself
        raises (before any write), the original must remain intact.
        """
        import contextlib  # noqa: PLC0415
        import unittest.mock as _mock  # noqa: PLC0415

        concept_path = _create_concept_file(
            tmp_path,
            "atomic-fail",
            title="Atomic Fail",
            status="active",
        )
        original_contents = concept_path.read_text(encoding="utf-8")

        with (
            _mock.patch(
                "lexibrary.lifecycle.concept_deprecation.serialize_concept_file",
                side_effect=RuntimeError("boom"),
            ),
            contextlib.suppress(RuntimeError),
        ):
            deprecate_concept(concept_path, reason="test")

        # Original file content is byte-for-byte unchanged.
        assert concept_path.read_text(encoding="utf-8") == original_contents
