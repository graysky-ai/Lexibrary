"""Unit tests for IWH cleanup -- TTL expiry and orphan detection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from lexibrary.iwh import IWHFile, serialize_iwh
from lexibrary.iwh.cleanup import CleanedSignal, CleanupResult, iwh_cleanup


def _write_iwh(
    designs_dir: Path,
    relative_dir: str,
    *,
    scope: str = "incomplete",
    body: str = "WIP",
    created: datetime | None = None,
) -> Path:
    """Write a valid .iwh file under the designs mirror tree.

    Args:
        designs_dir: The ``.lexibrary/designs/`` directory.
        relative_dir: Relative source directory path (e.g. ``"src/auth"``).
        scope: IWH scope value.
        body: IWH body text.
        created: Timestamp for the signal; defaults to now-UTC.

    Returns:
        Path to the written ``.iwh`` file.
    """
    if created is None:
        created = datetime.now(UTC)
    iwh = IWHFile(
        author="agent-test",
        created=created,
        scope=scope,
        body=body,
    )
    target = designs_dir / relative_dir
    target.mkdir(parents=True, exist_ok=True)
    iwh_path = target / ".iwh"
    iwh_path.write_text(serialize_iwh(iwh), encoding="utf-8")
    return iwh_path


class TestCleanupDataclasses:
    """Smoke tests for CleanedSignal and CleanupResult dataclasses."""

    def test_cleaned_signal_fields(self) -> None:
        sig = CleanedSignal(
            source_dir=Path("src/auth"),
            scope="incomplete",
            reason="expired",
        )
        assert sig.source_dir == Path("src/auth")
        assert sig.scope == "incomplete"
        assert sig.reason == "expired"

    def test_cleanup_result_defaults(self) -> None:
        result = CleanupResult()
        assert result.expired == []
        assert result.orphaned == []
        assert result.kept == 0

    def test_cleanup_result_aggregates(self) -> None:
        result = CleanupResult(
            expired=[
                CleanedSignal(source_dir=Path("a"), scope="incomplete", reason="expired"),
                CleanedSignal(source_dir=Path("b"), scope="blocked", reason="expired"),
            ],
            orphaned=[
                CleanedSignal(source_dir=Path("c"), scope="warning", reason="orphaned"),
            ],
            kept=3,
        )
        assert len(result.expired) == 2
        assert len(result.orphaned) == 1
        assert result.kept == 3


class TestIWHCleanupExpired:
    """Tests for TTL-based expiry in iwh_cleanup."""

    def test_expired_signal_deleted(self, tmp_path: Path) -> None:
        """Signal older than TTL is deleted and included in expired list."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        source = project / "src" / "auth"
        source.mkdir(parents=True)

        old_time = datetime.now(UTC) - timedelta(hours=80)
        iwh_path = _write_iwh(designs, "src/auth", created=old_time)

        result = iwh_cleanup(project, ttl_hours=72)

        assert not iwh_path.exists()
        assert len(result.expired) == 1
        assert result.expired[0].source_dir == Path("src/auth")
        assert result.expired[0].reason == "expired"
        assert result.kept == 0

    def test_within_ttl_kept(self, tmp_path: Path) -> None:
        """Signal within TTL with existing source directory is kept."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        source = project / "src" / "auth"
        source.mkdir(parents=True)

        recent_time = datetime.now(UTC) - timedelta(hours=24)
        iwh_path = _write_iwh(designs, "src/auth", created=recent_time)

        result = iwh_cleanup(project, ttl_hours=72)

        assert iwh_path.exists()
        assert len(result.expired) == 0
        assert len(result.orphaned) == 0
        assert result.kept == 1


class TestIWHCleanupOrphaned:
    """Tests for orphan detection in iwh_cleanup."""

    def test_orphaned_signal_deleted(self, tmp_path: Path) -> None:
        """Signal whose source directory is gone is deleted and marked orphaned."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        # Source directory does NOT exist -- no project/src/deleted_module/
        recent_time = datetime.now(UTC) - timedelta(hours=10)
        iwh_path = _write_iwh(designs, "src/deleted_module", created=recent_time, scope="blocked")

        result = iwh_cleanup(project, ttl_hours=72)

        assert not iwh_path.exists()
        assert len(result.orphaned) == 1
        assert result.orphaned[0].source_dir == Path("src/deleted_module")
        assert result.orphaned[0].scope == "blocked"
        assert result.orphaned[0].reason == "orphaned"
        assert result.kept == 0

    def test_orphaned_regardless_of_age(self, tmp_path: Path) -> None:
        """Orphaned signals are deleted even if they are within TTL."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        # Very recent, but source is gone
        just_now = datetime.now(UTC) - timedelta(minutes=5)
        iwh_path = _write_iwh(designs, "src/gone", created=just_now)

        result = iwh_cleanup(project, ttl_hours=72)

        assert not iwh_path.exists()
        assert len(result.orphaned) == 1
        assert result.kept == 0


class TestIWHCleanupEdgeCases:
    """Edge-case tests for iwh_cleanup."""

    def test_no_lexibrary_dir(self, tmp_path: Path) -> None:
        """No .lexibrary/ directory returns empty result."""
        result = iwh_cleanup(tmp_path, ttl_hours=72)

        assert result.expired == []
        assert result.orphaned == []
        assert result.kept == 0

    def test_no_designs_dir(self, tmp_path: Path) -> None:
        """No .lexibrary/designs/ directory returns empty result."""
        (tmp_path / ".lexibrary").mkdir()
        result = iwh_cleanup(tmp_path, ttl_hours=72)

        assert result.expired == []
        assert result.orphaned == []
        assert result.kept == 0

    def test_unparseable_file_treated_as_expired(self, tmp_path: Path) -> None:
        """Corrupt .iwh file is deleted and counted as expired."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        target = designs / "src" / "broken"
        target.mkdir(parents=True)
        # Also create the source directory so it's not orphaned
        (project / "src" / "broken").mkdir(parents=True)

        iwh_path = target / ".iwh"
        iwh_path.write_text("not valid frontmatter content", encoding="utf-8")

        result = iwh_cleanup(project, ttl_hours=72)

        assert not iwh_path.exists()
        assert len(result.expired) == 1
        assert result.expired[0].source_dir == Path("src/broken")
        assert result.expired[0].scope == "unknown"
        assert result.expired[0].reason == "expired"

    def test_timezone_naive_timestamp(self, tmp_path: Path) -> None:
        """Timezone-naive created timestamp is treated as UTC."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        source = project / "src" / "naive"
        source.mkdir(parents=True)

        # Write an IWH file with a timezone-naive timestamp (80 hours ago)
        naive_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=80)
        target = designs / "src" / "naive"
        target.mkdir(parents=True, exist_ok=True)
        # Manually write with naive timestamp in frontmatter
        content = (
            "---\n"
            f"author: agent-test\n"
            f"created: '{naive_time.strftime('%Y-%m-%dT%H:%M:%S')}'\n"
            f"scope: incomplete\n"
            "---\n"
            "Naive timestamp test\n"
        )
        iwh_path = target / ".iwh"
        iwh_path.write_text(content, encoding="utf-8")

        result = iwh_cleanup(project, ttl_hours=72)

        assert not iwh_path.exists()
        assert len(result.expired) == 1
        assert result.expired[0].source_dir == Path("src/naive")
        assert result.expired[0].reason == "expired"

    def test_timezone_naive_within_ttl(self, tmp_path: Path) -> None:
        """Timezone-naive timestamp within TTL is kept."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        source = project / "src" / "naive_ok"
        source.mkdir(parents=True)

        # Write an IWH file with a timezone-naive timestamp (10 hours ago)
        naive_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=10)
        target = designs / "src" / "naive_ok"
        target.mkdir(parents=True, exist_ok=True)
        content = (
            "---\n"
            f"author: agent-test\n"
            f"created: '{naive_time.strftime('%Y-%m-%dT%H:%M:%S')}'\n"
            f"scope: warning\n"
            "---\n"
            "Within TTL\n"
        )
        iwh_path = target / ".iwh"
        iwh_path.write_text(content, encoding="utf-8")

        result = iwh_cleanup(project, ttl_hours=72)

        assert iwh_path.exists()
        assert result.kept == 1
        assert len(result.expired) == 0


class TestIWHCleanupMixed:
    """Tests combining multiple signal states in a single cleanup run."""

    def test_mixed_signals(self, tmp_path: Path) -> None:
        """Cleanup correctly categorises a mix of expired, orphaned, and kept signals."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"

        # 1. Valid, within TTL, source exists -> kept
        (project / "src" / "good").mkdir(parents=True)
        recent = datetime.now(UTC) - timedelta(hours=10)
        kept_path = _write_iwh(designs, "src/good", created=recent)

        # 2. Expired (old), source exists -> expired
        (project / "src" / "old").mkdir(parents=True)
        old = datetime.now(UTC) - timedelta(hours=100)
        expired_path = _write_iwh(designs, "src/old", created=old, scope="blocked")

        # 3. Within TTL but source missing -> orphaned
        orphan_time = datetime.now(UTC) - timedelta(hours=5)
        orphan_path = _write_iwh(designs, "src/gone", created=orphan_time, scope="warning")

        result = iwh_cleanup(project, ttl_hours=72)

        assert kept_path.exists()
        assert not expired_path.exists()
        assert not orphan_path.exists()

        assert result.kept == 1
        assert len(result.expired) == 1
        assert len(result.orphaned) == 1
        assert result.expired[0].source_dir == Path("src/old")
        assert result.orphaned[0].source_dir == Path("src/gone")


class TestIWHCleanupRemoveAll:
    """Tests for the remove_all parameter in iwh_cleanup."""

    def test_remove_all_removes_within_ttl(self, tmp_path: Path) -> None:
        """remove_all=True removes signals that are within TTL."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        source = project / "src" / "auth"
        source.mkdir(parents=True)

        # Signal is only 1 hour old -- well within a 72-hour TTL
        recent_time = datetime.now(UTC) - timedelta(hours=1)
        iwh_path = _write_iwh(designs, "src/auth", created=recent_time)

        result = iwh_cleanup(project, ttl_hours=72, remove_all=True)

        assert not iwh_path.exists()
        assert len(result.expired) == 1
        assert result.expired[0].source_dir == Path("src/auth")
        assert result.expired[0].reason == "expired"
        assert result.kept == 0

    def test_remove_all_with_no_signals(self, tmp_path: Path) -> None:
        """remove_all=True with no signals returns empty result."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        designs.mkdir(parents=True)

        result = iwh_cleanup(project, ttl_hours=72, remove_all=True)

        assert result.expired == []
        assert result.orphaned == []
        assert result.kept == 0

    def test_remove_all_still_detects_orphans(self, tmp_path: Path) -> None:
        """remove_all=True still classifies orphaned signals as orphaned."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        # Source directory does NOT exist
        recent_time = datetime.now(UTC) - timedelta(hours=1)
        iwh_path = _write_iwh(designs, "src/missing", created=recent_time, scope="blocked")

        result = iwh_cleanup(project, ttl_hours=72, remove_all=True)

        assert not iwh_path.exists()
        assert len(result.orphaned) == 1
        assert result.orphaned[0].source_dir == Path("src/missing")
        assert result.orphaned[0].reason == "orphaned"
        assert len(result.expired) == 0

    def test_remove_all_multiple_signals(self, tmp_path: Path) -> None:
        """remove_all=True removes all signals, categorising orphans correctly."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"

        # Signal 1: within TTL, source exists -> expired (remove_all)
        (project / "src" / "a").mkdir(parents=True)
        recent = datetime.now(UTC) - timedelta(hours=5)
        path_a = _write_iwh(designs, "src/a", created=recent)

        # Signal 2: within TTL, source missing -> orphaned
        path_b = _write_iwh(designs, "src/b", created=recent, scope="warning")

        result = iwh_cleanup(project, ttl_hours=72, remove_all=True)

        assert not path_a.exists()
        assert not path_b.exists()
        assert len(result.expired) == 1
        assert len(result.orphaned) == 1
        assert result.kept == 0

    def test_default_preserves_ttl_behavior(self, tmp_path: Path) -> None:
        """Default remove_all=False preserves existing TTL behavior."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        source = project / "src" / "kept"
        source.mkdir(parents=True)

        recent_time = datetime.now(UTC) - timedelta(hours=10)
        iwh_path = _write_iwh(designs, "src/kept", created=recent_time)

        result = iwh_cleanup(project, ttl_hours=72)

        assert iwh_path.exists()
        assert result.kept == 1
        assert len(result.expired) == 0

    def test_custom_ttl_hours(self, tmp_path: Path) -> None:
        """Custom ttl_hours value correctly controls expiry threshold."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        source = project / "src" / "custom"
        source.mkdir(parents=True)

        # Signal is 5 hours old
        five_hours_ago = datetime.now(UTC) - timedelta(hours=5)
        iwh_path = _write_iwh(designs, "src/custom", created=five_hours_ago)

        # With ttl_hours=4, the signal should be expired
        result = iwh_cleanup(project, ttl_hours=4)
        assert not iwh_path.exists()
        assert len(result.expired) == 1

    def test_custom_ttl_hours_keeps_young(self, tmp_path: Path) -> None:
        """Custom ttl_hours keeps signals younger than the threshold."""
        project = tmp_path / "project"
        designs = project / ".lexibrary" / "designs"
        source = project / "src" / "young"
        source.mkdir(parents=True)

        # Signal is 2 hours old
        two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
        iwh_path = _write_iwh(designs, "src/young", created=two_hours_ago)

        # With ttl_hours=4, the signal should be kept
        result = iwh_cleanup(project, ttl_hours=4)
        assert iwh_path.exists()
        assert result.kept == 1


class TestCleanupImports:
    """Verify that cleanup symbols are importable from the package."""

    def test_imports_from_package(self) -> None:
        """All cleanup exports are available from lexibrary.iwh."""
        from lexibrary.iwh import CleanedSignal, CleanupResult, iwh_cleanup

        assert CleanedSignal is not None
        assert CleanupResult is not None
        assert callable(iwh_cleanup)
