"""Tests for update stat rendering functions."""

from __future__ import annotations

from pathlib import Path

from lexibrary.archivist.change_checker import ChangeLevel
from lexibrary.archivist.pipeline import UpdateStats
from lexibrary.services.update_render import (
    has_enrichment_queue,
    has_lifecycle_stats,
    render_dry_run_results,
    render_enrichment_queue,
    render_failed_files,
    render_lifecycle_stats,
    render_update_summary,
)

PROJECT_ROOT = Path("/fake/project")


# ---------------------------------------------------------------------------
# render_update_summary
# ---------------------------------------------------------------------------


class TestRenderUpdateSummary:
    """Tests for render_update_summary."""

    def test_all_zero_stats(self) -> None:
        stats = UpdateStats()
        result = render_update_summary(stats, PROJECT_ROOT)

        # Should have the header lines plus the stat lines
        assert ("info", "") in result
        assert ("info", "Update summary:") in result
        assert ("info", "  Files scanned:       0") in result
        assert ("info", "  Files unchanged:     0") in result
        assert ("info", "  Files created:       0") in result
        assert ("info", "  Files updated:       0") in result
        assert ("info", "  Files agent-updated: 0") in result

        # Should NOT have error or warn lines for zero stats
        assert not any(level == "error" for level, _ in result)
        assert not any(level == "warn" for level, _ in result)

    def test_mixed_counts(self) -> None:
        stats = UpdateStats(
            files_scanned=10,
            files_unchanged=5,
            files_created=2,
            files_updated=3,
            files_agent_updated=1,
            aindex_refreshed=4,
            token_budget_warnings=2,
        )
        result = render_update_summary(stats, PROJECT_ROOT)

        assert ("info", "  Files scanned:       10") in result
        assert ("info", "  Files unchanged:     5") in result
        assert ("info", "  Files created:       2") in result
        assert ("info", "  Files updated:       3") in result
        assert ("info", "  Files agent-updated: 1") in result
        assert ("info", "  .aindex refreshed:   4") in result
        assert ("warn", "  Token budget warnings: 2") in result

    def test_with_failures(self) -> None:
        stats = UpdateStats(
            files_scanned=5,
            files_failed=2,
            failed_files=[
                (str(PROJECT_ROOT / "src/foo.py"), "LLM error"),
                (str(PROJECT_ROOT / "src/bar.py"), "Timeout"),
            ],
        )
        result = render_update_summary(stats, PROJECT_ROOT)

        assert ("error", "  Files failed:       2") in result
        assert ("error", "    - src/foo.py: LLM error") in result
        assert ("error", "    - src/bar.py: Timeout") in result

    def test_failed_file_outside_project_root(self) -> None:
        stats = UpdateStats(
            files_failed=1,
            failed_files=[("/other/path/file.py", "some error")],
        )
        result = render_update_summary(stats, PROJECT_ROOT)

        # Path outside project root should be shown as-is
        assert ("error", "    - /other/path/file.py: some error") in result


# ---------------------------------------------------------------------------
# render_failed_files
# ---------------------------------------------------------------------------


class TestRenderFailedFiles:
    """Tests for render_failed_files."""

    def test_no_failures(self) -> None:
        stats = UpdateStats()
        assert render_failed_files(stats, PROJECT_ROOT) == ""

    def test_with_failures(self) -> None:
        stats = UpdateStats(
            files_failed=2,
            failed_files=[
                (str(PROJECT_ROOT / "src/foo.py"), "LLM error"),
                (str(PROJECT_ROOT / "src/bar.py"), "Timeout"),
            ],
        )
        result = render_failed_files(stats, PROJECT_ROOT)

        assert "src/foo.py: LLM error" in result
        assert "src/bar.py: Timeout" in result

    def test_outside_project_root(self) -> None:
        stats = UpdateStats(
            files_failed=1,
            failed_files=[("/other/path.py", "error")],
        )
        result = render_failed_files(stats, PROJECT_ROOT)
        assert "/other/path.py: error" in result


# ---------------------------------------------------------------------------
# has_lifecycle_stats / render_lifecycle_stats
# ---------------------------------------------------------------------------


class TestLifecycleStats:
    """Tests for lifecycle stat helpers."""

    def test_has_lifecycle_false_when_all_zero(self) -> None:
        stats = UpdateStats()
        assert has_lifecycle_stats(stats) is False

    def test_has_lifecycle_true_single_field(self) -> None:
        assert has_lifecycle_stats(UpdateStats(designs_deprecated=1)) is True
        assert has_lifecycle_stats(UpdateStats(designs_unlinked=1)) is True
        assert has_lifecycle_stats(UpdateStats(designs_deleted_ttl=1)) is True
        assert has_lifecycle_stats(UpdateStats(concepts_deleted_ttl=1)) is True
        assert has_lifecycle_stats(UpdateStats(concepts_skipped_referenced=1)) is True
        assert has_lifecycle_stats(UpdateStats(conventions_deleted_ttl=1)) is True
        assert has_lifecycle_stats(UpdateStats(renames_detected=1)) is True
        assert has_lifecycle_stats(UpdateStats(renames_migrated=1)) is True

    def test_render_lifecycle_with_activity(self) -> None:
        stats = UpdateStats(
            renames_detected=3,
            renames_migrated=2,
            designs_deprecated=1,
            designs_unlinked=4,
            designs_deleted_ttl=2,
            concepts_deleted_ttl=1,
            concepts_skipped_referenced=5,
            conventions_deleted_ttl=3,
        )
        result = render_lifecycle_stats(stats)

        assert ("info", "Lifecycle:") in result
        assert ("info", "  Renames detected:    3") in result
        assert ("info", "  Renames migrated:    2") in result
        assert ("info", "  Designs deprecated:  1") in result
        assert ("info", "  Designs unlinked:    4") in result
        assert ("warn", "  Designs TTL-deleted: 2") in result
        assert ("warn", "  Concepts TTL-deleted: 1") in result
        assert ("info", "  Concepts skipped (referenced): 5") in result
        assert ("warn", "  Conventions TTL-deleted: 3") in result

    def test_render_lifecycle_omits_zero_fields(self) -> None:
        stats = UpdateStats(designs_deprecated=1)
        result = render_lifecycle_stats(stats)

        # Only header and the one non-zero field
        assert ("info", "  Designs deprecated:  1") in result
        assert not any("Renames" in msg for _, msg in result)
        assert not any("unlinked" in msg for _, msg in result)


# ---------------------------------------------------------------------------
# has_enrichment_queue / render_enrichment_queue
# ---------------------------------------------------------------------------


class TestEnrichmentQueue:
    """Tests for enrichment queue helpers."""

    def test_has_queue_false_when_all_zero(self) -> None:
        stats = UpdateStats()
        assert has_enrichment_queue(stats) is False

    def test_has_queue_true(self) -> None:
        assert has_enrichment_queue(UpdateStats(queue_processed=1)) is True
        assert has_enrichment_queue(UpdateStats(queue_failed=1)) is True
        assert has_enrichment_queue(UpdateStats(queue_remaining=1)) is True

    def test_render_queue_with_items(self) -> None:
        stats = UpdateStats(
            queue_processed=5,
            queue_failed=1,
            queue_remaining=3,
        )
        result = render_enrichment_queue(stats)

        assert ("info", "Enrichment queue:") in result
        assert ("info", "  Enriched:            5") in result
        assert ("error", "  Failed:             1") in result
        assert ("info", "  Remaining:           3") in result

    def test_render_queue_omits_zero_fields(self) -> None:
        stats = UpdateStats(queue_processed=2)
        result = render_enrichment_queue(stats)

        assert ("info", "  Enriched:            2") in result
        assert not any("Failed" in msg for _, msg in result)
        assert not any("Remaining" in msg for _, msg in result)


# ---------------------------------------------------------------------------
# render_dry_run_results
# ---------------------------------------------------------------------------


class TestRenderDryRunResults:
    """Tests for render_dry_run_results."""

    def test_mixed_results(self) -> None:
        results: list[tuple[Path, ChangeLevel]] = [
            (PROJECT_ROOT / "src/a.py", ChangeLevel.NEW_FILE),
            (PROJECT_ROOT / "src/b.py", ChangeLevel.CONTENT_CHANGED),
            (PROJECT_ROOT / "src/c.py", ChangeLevel.NEW_FILE),
        ]
        output = render_dry_run_results(results, PROJECT_ROOT)

        assert "NEW_FILE" in output
        assert "CONTENT_CHANGED" in output
        assert "src/a.py" in output
        assert "src/b.py" in output
        assert "src/c.py" in output
        assert "Summary: 3 files" in output
        assert "1 content_changed" in output
        assert "2 new_file" in output

    def test_single_file(self) -> None:
        results: list[tuple[Path, ChangeLevel]] = [
            (PROJECT_ROOT / "src/x.py", ChangeLevel.UNCHANGED),
        ]
        output = render_dry_run_results(results, PROJECT_ROOT)

        assert "1 file" in output
        # Singular "file" not "files"
        assert "1 files" not in output
