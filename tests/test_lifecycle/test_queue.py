"""Unit tests for the enrichment queue module."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from lexibrary.lifecycle.queue import (
    QUEUE_HEADER,
    QUEUE_REL_PATH,
    QueueEntry,
    clear_queue,
    queue_for_enrichment,
    read_queue,
)

# ---------------------------------------------------------------------------
# QueueEntry model
# ---------------------------------------------------------------------------


class TestQueueEntry:
    """Tests for the QueueEntry Pydantic model."""

    def test_create_entry(self) -> None:
        ts = datetime(2026, 3, 3, 14, 22, 1, tzinfo=UTC)
        entry = QueueEntry(source_path=Path("src/foo.py"), queued_at=ts)
        assert entry.source_path == Path("src/foo.py")
        assert entry.queued_at == ts

    def test_entry_serialisation_roundtrip(self) -> None:
        ts = datetime(2026, 3, 3, 14, 22, 1, tzinfo=UTC)
        entry = QueueEntry(source_path=Path("src/foo.py"), queued_at=ts)
        data = entry.model_dump()
        restored = QueueEntry.model_validate(data)
        assert restored == entry


# ---------------------------------------------------------------------------
# queue_for_enrichment()
# ---------------------------------------------------------------------------


class TestQueueForEnrichment:
    """Tests for the queue_for_enrichment() function."""

    def test_creates_queue_file_if_missing(self, tmp_path: Path) -> None:
        queue_for_enrichment(tmp_path, Path("src/module.py"))
        queue_file = tmp_path / QUEUE_REL_PATH
        assert queue_file.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        queue_for_enrichment(tmp_path, Path("src/module.py"))
        assert (tmp_path / ".lexibrary" / "queue").is_dir()

    def test_appended_entry_is_parseable(self, tmp_path: Path) -> None:
        queue_for_enrichment(tmp_path, Path("src/module.py"))
        entries = read_queue(tmp_path)
        assert len(entries) == 1
        assert entries[0].source_path == Path("src/module.py")

    def test_append_to_existing_queue(self, tmp_path: Path) -> None:
        queue_for_enrichment(tmp_path, Path("src/a.py"))
        queue_for_enrichment(tmp_path, Path("src/b.py"))
        entries = read_queue(tmp_path)
        paths = {e.source_path for e in entries}
        assert paths == {Path("src/a.py"), Path("src/b.py")}

    def test_normalises_absolute_path_to_relative(self, tmp_path: Path) -> None:
        abs_path = tmp_path / "src" / "module.py"
        queue_for_enrichment(tmp_path, abs_path)
        entries = read_queue(tmp_path)
        assert len(entries) == 1
        assert entries[0].source_path == Path("src/module.py")

    def test_queue_header_present(self, tmp_path: Path) -> None:
        queue_for_enrichment(tmp_path, Path("src/module.py"))
        content = (tmp_path / QUEUE_REL_PATH).read_text()
        assert content.startswith(QUEUE_HEADER)

    def test_timestamp_is_utc(self, tmp_path: Path) -> None:
        queue_for_enrichment(tmp_path, Path("src/module.py"))
        entries = read_queue(tmp_path)
        assert len(entries) == 1
        # ISO format with +00:00 suffix means UTC-aware
        assert entries[0].queued_at.tzinfo is not None


# ---------------------------------------------------------------------------
# read_queue()
# ---------------------------------------------------------------------------


class TestReadQueue:
    """Tests for the read_queue() function."""

    def test_empty_when_file_missing(self, tmp_path: Path) -> None:
        assert read_queue(tmp_path) == []

    def test_empty_when_file_is_only_comments(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(QUEUE_HEADER)
        assert read_queue(tmp_path) == []

    def test_dedup_keeps_latest_timestamp(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(
            QUEUE_HEADER
            + "src/module.py 2026-03-01T10:00:00+00:00\n"
            + "src/module.py 2026-03-03T14:00:00+00:00\n"
        )
        entries = read_queue(tmp_path)
        assert len(entries) == 1
        assert entries[0].source_path == Path("src/module.py")
        assert entries[0].queued_at == datetime(2026, 3, 3, 14, 0, 0, tzinfo=UTC)

    def test_dedup_with_multiple_paths(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(
            QUEUE_HEADER
            + "src/a.py 2026-03-01T10:00:00+00:00\n"
            + "src/b.py 2026-03-01T11:00:00+00:00\n"
            + "src/a.py 2026-03-02T10:00:00+00:00\n"
        )
        entries = read_queue(tmp_path)
        assert len(entries) == 2
        paths = {e.source_path for e in entries}
        assert paths == {Path("src/a.py"), Path("src/b.py")}

    def test_sorted_by_timestamp_oldest_first(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(
            QUEUE_HEADER
            + "src/late.py 2026-03-05T00:00:00+00:00\n"
            + "src/early.py 2026-03-01T00:00:00+00:00\n"
        )
        entries = read_queue(tmp_path)
        assert entries[0].source_path == Path("src/early.py")
        assert entries[1].source_path == Path("src/late.py")

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(
            QUEUE_HEADER
            + "malformed-no-timestamp\n"
            + "src/good.py 2026-03-03T14:00:00+00:00\n"
            + "bad-timestamp not-a-date\n"
        )
        entries = read_queue(tmp_path)
        assert len(entries) == 1
        assert entries[0].source_path == Path("src/good.py")

    def test_ignores_comment_lines(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(
            "# custom comment\n" + QUEUE_HEADER + "src/module.py 2026-03-03T14:00:00+00:00\n"
        )
        entries = read_queue(tmp_path)
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# clear_queue()
# ---------------------------------------------------------------------------


class TestClearQueue:
    """Tests for the clear_queue() function."""

    def test_removes_processed_entries(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(
            QUEUE_HEADER
            + "src/a.py 2026-03-01T10:00:00+00:00\n"
            + "src/b.py 2026-03-01T11:00:00+00:00\n"
            + "src/c.py 2026-03-01T12:00:00+00:00\n"
        )
        clear_queue(tmp_path, [Path("src/a.py"), Path("src/b.py")])

        entries = read_queue(tmp_path)
        assert len(entries) == 1
        assert entries[0].source_path == Path("src/c.py")

    def test_full_clear_leaves_only_header(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(
            QUEUE_HEADER
            + "src/a.py 2026-03-01T10:00:00+00:00\n"
            + "src/b.py 2026-03-01T11:00:00+00:00\n"
        )
        clear_queue(tmp_path, [Path("src/a.py"), Path("src/b.py")])

        content = queue_file.read_text()
        assert content == QUEUE_HEADER
        assert read_queue(tmp_path) == []

    def test_noop_when_queue_missing(self, tmp_path: Path) -> None:
        # Should not raise.
        clear_queue(tmp_path, [Path("src/a.py")])

    def test_preserves_unprocessed_entries(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(
            QUEUE_HEADER
            + "src/keep.py 2026-03-01T10:00:00+00:00\n"
            + "src/remove.py 2026-03-01T11:00:00+00:00\n"
        )
        clear_queue(tmp_path, [Path("src/remove.py")])

        entries = read_queue(tmp_path)
        assert len(entries) == 1
        assert entries[0].source_path == Path("src/keep.py")

    def test_queue_file_not_deleted(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(QUEUE_HEADER + "src/a.py 2026-03-01T10:00:00+00:00\n")
        clear_queue(tmp_path, [Path("src/a.py")])
        assert queue_file.exists()

    def test_clear_empty_processed_list(self, tmp_path: Path) -> None:
        queue_file = tmp_path / QUEUE_REL_PATH
        queue_file.parent.mkdir(parents=True, exist_ok=True)
        queue_file.write_text(QUEUE_HEADER + "src/a.py 2026-03-01T10:00:00+00:00\n")
        clear_queue(tmp_path, [])

        entries = read_queue(tmp_path)
        assert len(entries) == 1
        assert entries[0].source_path == Path("src/a.py")


# ---------------------------------------------------------------------------
# Integration: append -> read -> clear round-trip
# ---------------------------------------------------------------------------


class TestQueueRoundTrip:
    """End-to-end round-trip tests."""

    def test_append_read_clear_cycle(self, tmp_path: Path) -> None:
        # Append three entries.
        queue_for_enrichment(tmp_path, Path("src/a.py"))
        queue_for_enrichment(tmp_path, Path("src/b.py"))
        queue_for_enrichment(tmp_path, Path("src/c.py"))

        # Read -- should have three unique entries.
        entries = read_queue(tmp_path)
        assert len(entries) == 3

        # Clear two.
        clear_queue(tmp_path, [Path("src/a.py"), Path("src/c.py")])

        # Read again -- only b remains.
        entries = read_queue(tmp_path)
        assert len(entries) == 1
        assert entries[0].source_path == Path("src/b.py")

    def test_duplicate_append_deduplicates_on_read(self, tmp_path: Path) -> None:
        fixed_time_1 = datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC)
        fixed_time_2 = datetime(2026, 3, 2, 10, 0, 0, tzinfo=UTC)

        with patch(
            "lexibrary.lifecycle.queue.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = fixed_time_1
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            queue_for_enrichment(tmp_path, Path("src/module.py"))

        with patch(
            "lexibrary.lifecycle.queue.datetime",
        ) as mock_dt:
            mock_dt.now.return_value = fixed_time_2
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            queue_for_enrichment(tmp_path, Path("src/module.py"))

        entries = read_queue(tmp_path)
        assert len(entries) == 1
        # Should keep the latest one.
        assert entries[0].queued_at == fixed_time_2
