"""Tests for structured error collection (ErrorRecord, ErrorSummary, format_error_summary)."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from lexibrary.errors import ErrorRecord, ErrorSummary, format_error_summary


class TestErrorRecord:
    def test_fields(self) -> None:
        rec = ErrorRecord(
            timestamp="2026-01-01T00:00:00+00:00",
            phase="crawl",
            path="src/foo.py",
            error_type="ValueError",
            message="bad value",
            traceback=None,
        )
        assert rec.phase == "crawl"
        assert rec.path == "src/foo.py"
        assert rec.error_type == "ValueError"
        assert rec.message == "bad value"
        assert rec.traceback is None


class TestErrorSummary:
    def test_empty_summary(self) -> None:
        summary = ErrorSummary()
        assert summary.count == 0
        assert not summary.has_errors()
        assert summary.by_phase() == {}

    def test_add_records_error(self) -> None:
        summary = ErrorSummary()
        summary.add("crawl", ValueError("bad"))
        assert summary.count == 1
        assert summary.has_errors()
        rec = summary.records[0]
        assert rec.phase == "crawl"
        assert rec.error_type == "ValueError"
        assert rec.message == "bad"
        assert rec.path is None

    def test_add_with_path(self) -> None:
        summary = ErrorSummary()
        summary.add("indexer", RuntimeError("fail"), path="src/bar.py")
        assert summary.records[0].path == "src/bar.py"

    def test_by_phase_groups_correctly(self) -> None:
        summary = ErrorSummary()
        summary.add("crawl", ValueError("a"))
        summary.add("indexer", RuntimeError("b"))
        summary.add("crawl", TypeError("c"))
        grouped = summary.by_phase()
        assert len(grouped["crawl"]) == 2
        assert len(grouped["indexer"]) == 1

    def test_timestamp_is_iso_format(self) -> None:
        summary = ErrorSummary()
        summary.add("test", ValueError("x"))
        ts = summary.records[0].timestamp
        # Should be parseable as ISO datetime
        assert "T" in ts

    def test_traceback_none_when_no_tb(self) -> None:
        summary = ErrorSummary()
        summary.add("test", ValueError("no traceback"))
        assert summary.records[0].traceback is None

    def test_traceback_captured_when_raised(self) -> None:
        summary = ErrorSummary()
        try:
            raise ValueError("with traceback")
        except ValueError as exc:
            summary.add("test", exc)
        assert summary.records[0].traceback is not None


class TestFormatErrorSummary:
    def _render(self, summary: ErrorSummary) -> str:
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        format_error_summary(summary, console)
        return buf.getvalue()

    def test_no_output_when_empty(self) -> None:
        output = self._render(ErrorSummary())
        assert output == ""

    def test_outputs_error_count(self) -> None:
        summary = ErrorSummary()
        summary.add("crawl", ValueError("bad"))
        output = self._render(summary)
        assert "Errors (1)" in output

    def test_outputs_phase_and_message(self) -> None:
        summary = ErrorSummary()
        summary.add("indexer", RuntimeError("broken"), path="src/x.py")
        output = self._render(summary)
        assert "indexer" in output
        assert "broken" in output
        assert "src/x.py" in output
