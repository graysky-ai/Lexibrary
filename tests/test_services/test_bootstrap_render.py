"""Tests for bootstrap stat rendering functions."""

from __future__ import annotations

from lexibrary.indexer.orchestrator import IndexStats
from lexibrary.lifecycle.bootstrap import BootstrapStats
from lexibrary.services.bootstrap_render import (
    render_bootstrap_summary,
    render_index_summary,
)

# ---------------------------------------------------------------------------
# render_index_summary
# ---------------------------------------------------------------------------


class TestRenderIndexSummary:
    """Tests for render_index_summary."""

    def test_successful_indexing_no_errors(self) -> None:
        stats = IndexStats(directories_indexed=5, files_found=42, errors=0)
        result = render_index_summary(stats)

        assert len(result) == 1
        level, msg = result[0]
        assert level == "info"
        assert "Directories indexed: 5" in msg
        assert "Files found: 42" in msg

        # No error lines when errors == 0
        assert not any(level == "error" for level, _ in result)

    def test_indexing_with_errors(self) -> None:
        stats = IndexStats(directories_indexed=3, files_found=20, errors=7)
        result = render_index_summary(stats)

        assert len(result) == 2

        # First line: info with counts
        level, msg = result[0]
        assert level == "info"
        assert "Directories indexed: 3" in msg
        assert "Files found: 20" in msg

        # Second line: error with error count
        level, msg = result[1]
        assert level == "error"
        assert "Errors: 7" in msg

    def test_zero_stats(self) -> None:
        stats = IndexStats()
        result = render_index_summary(stats)

        assert len(result) == 1
        level, msg = result[0]
        assert level == "info"
        assert "Directories indexed: 0" in msg
        assert "Files found: 0" in msg


# ---------------------------------------------------------------------------
# render_bootstrap_summary
# ---------------------------------------------------------------------------


class TestRenderBootstrapSummary:
    """Tests for render_bootstrap_summary."""

    def test_successful_bootstrap_no_failures(self) -> None:
        stats = BootstrapStats(
            files_scanned=50,
            files_created=30,
            files_updated=10,
            files_skipped=10,
            files_failed=0,
        )
        result = render_bootstrap_summary(stats)

        assert ("info", "") in result
        assert ("info", "Bootstrap summary:") in result
        assert ("info", "  Files scanned:  50") in result
        assert ("info", "  Files created:  30") in result
        assert ("info", "  Files updated:  10") in result
        assert ("info", "  Files skipped:  10") in result

        # No error lines when no failures
        assert not any(level == "error" for level, _ in result)

    def test_bootstrap_with_failures_and_errors(self) -> None:
        stats = BootstrapStats(
            files_scanned=20,
            files_created=10,
            files_updated=5,
            files_skipped=2,
            files_failed=3,
            errors=["Failed to parse foo.py", "Timeout on bar.py"],
        )
        result = render_bootstrap_summary(stats)

        assert ("info", "Bootstrap summary:") in result
        assert ("info", "  Files scanned:  20") in result
        assert ("info", "  Files created:  10") in result
        assert ("info", "  Files updated:  5") in result
        assert ("info", "  Files skipped:  2") in result
        assert ("error", "  Files failed:  3") in result

        # Error section
        assert ("error", "Errors:") in result
        assert ("error", "  Failed to parse foo.py") in result
        assert ("error", "  Timeout on bar.py") in result

    def test_bootstrap_with_failures_no_error_messages(self) -> None:
        stats = BootstrapStats(
            files_scanned=10,
            files_created=5,
            files_updated=2,
            files_skipped=1,
            files_failed=2,
        )
        result = render_bootstrap_summary(stats)

        assert ("error", "  Files failed:  2") in result

        # No "Errors:" section when errors list is empty
        assert ("error", "Errors:") not in result

    def test_all_zero_stats(self) -> None:
        stats = BootstrapStats()
        result = render_bootstrap_summary(stats)

        assert ("info", "") in result
        assert ("info", "Bootstrap summary:") in result
        assert ("info", "  Files scanned:  0") in result
        assert ("info", "  Files created:  0") in result
        assert ("info", "  Files updated:  0") in result
        assert ("info", "  Files skipped:  0") in result

        # No error lines for zero stats
        assert not any(level == "error" for level, _ in result)
