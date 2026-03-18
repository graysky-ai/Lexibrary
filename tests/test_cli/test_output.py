"""Tests for the plain-text output helpers in ``lexibrary.cli._output``."""

from __future__ import annotations

import io

import pytest

from lexibrary.cli._output import error, hint, info, markdown_table, warn

# ---------------------------------------------------------------------------
# info()
# ---------------------------------------------------------------------------


class TestInfo:
    def test_prints_message_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        info("hello world")
        captured = capsys.readouterr()
        assert captured.out == "hello world\n"
        assert captured.err == ""

    def test_no_prefix(self, capsys: pytest.CaptureFixture[str]) -> None:
        info("plain message")
        captured = capsys.readouterr()
        assert not captured.out.startswith("Info:")

    def test_custom_file(self) -> None:
        buf = io.StringIO()
        info("to buffer", file=buf)
        assert buf.getvalue() == "to buffer\n"


# ---------------------------------------------------------------------------
# warn()
# ---------------------------------------------------------------------------


class TestWarn:
    def test_prints_with_warning_prefix_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        warn("something is off")
        captured = capsys.readouterr()
        assert captured.err == "Warning: something is off\n"
        assert captured.out == ""

    def test_custom_file(self) -> None:
        buf = io.StringIO()
        warn("buffered", file=buf)
        assert buf.getvalue() == "Warning: buffered\n"


# ---------------------------------------------------------------------------
# error()
# ---------------------------------------------------------------------------


class TestError:
    def test_prints_with_error_prefix_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        error("something broke")
        captured = capsys.readouterr()
        assert captured.err == "Error: something broke\n"
        assert captured.out == ""

    def test_custom_file(self) -> None:
        buf = io.StringIO()
        error("buffered", file=buf)
        assert buf.getvalue() == "Error: buffered\n"


# ---------------------------------------------------------------------------
# hint()
# ---------------------------------------------------------------------------


class TestHint:
    def test_prints_with_hint_prefix_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        hint("run `lexi validate`")
        captured = capsys.readouterr()
        assert captured.err == "Hint: run `lexi validate`\n"
        assert captured.out == ""

    def test_custom_file(self) -> None:
        buf = io.StringIO()
        hint("try again", file=buf)
        assert buf.getvalue() == "Hint: try again\n"


# ---------------------------------------------------------------------------
# markdown_table()
# ---------------------------------------------------------------------------


class TestMarkdownTable:
    def test_basic_table(self) -> None:
        result = markdown_table(["Name", "Age"], [["Alice", "30"], ["Bob", "25"]])
        lines = result.split("\n")
        assert len(lines) == 4  # header + separator + 2 data rows
        assert lines[0].startswith("| Name")
        assert "---" in lines[1]
        assert "Alice" in lines[2]
        assert "Bob" in lines[3]

    def test_empty_rows(self) -> None:
        result = markdown_table(["A", "B"], [])
        lines = result.split("\n")
        assert len(lines) == 2  # header + separator only

    def test_column_alignment(self) -> None:
        result = markdown_table(["X"], [["short"], ["much longer cell"]])
        lines = result.split("\n")
        # All rows should have the same length due to padding
        assert len(lines[0]) == len(lines[2])
        assert len(lines[0]) == len(lines[3])

    def test_separator_dashes_match_widths(self) -> None:
        result = markdown_table(["Header"], [["val"]])
        lines = result.split("\n")
        # All chars in separator should be dashes or pipes/spaces
        assert all(c in "-| " for c in lines[1])

    def test_short_rows_padded(self) -> None:
        """Rows with fewer cells than headers are padded with empty strings."""
        result = markdown_table(["A", "B", "C"], [["only-one"]])
        lines = result.split("\n")
        assert len(lines) == 3
        # The data row should still have 3 pipe-separated cells
        cells = [c.strip() for c in lines[2].strip("|").split("|")]
        assert len(cells) == 3
        assert cells[0] == "only-one"

    def test_long_rows_truncated(self) -> None:
        """Rows with more cells than headers are truncated to header count."""
        result = markdown_table(["A"], [["keep", "discard"]])
        lines = result.split("\n")
        assert "discard" not in result
        assert "keep" in lines[2]

    def test_empty_headers_raises(self) -> None:
        with pytest.raises(ValueError, match="headers must not be empty"):
            markdown_table([], [["a", "b"]])

    def test_minimum_column_width(self) -> None:
        """Columns should be at least 3 characters wide for valid Markdown."""
        result = markdown_table(["A"], [["x"]])
        lines = result.split("\n")
        # Separator dashes should be at least 3 chars
        sep_content = lines[1].split("|")[1].strip()
        assert len(sep_content) >= 3

    def test_pipe_structure(self) -> None:
        """Every line should start and end with a pipe character."""
        result = markdown_table(["Col1", "Col2"], [["a", "b"], ["c", "d"]])
        for line in result.split("\n"):
            assert line.startswith("|")
            assert line.endswith("|")
