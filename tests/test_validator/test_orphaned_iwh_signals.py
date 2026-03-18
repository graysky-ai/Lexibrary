"""Tests for check_orphaned_iwh_signals validation check.

Covers: expired signal detected, fresh signal not flagged, TTL disabled,
no IWH files, unparseable skipped, registry presence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from lexibrary.utils.paths import LEXIBRARY_DIR
from lexibrary.validator.checks import check_orphaned_iwh_signals

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iwh_content(*, hours_ago: int) -> str:
    """Generate a valid .iwh file with a created timestamp N hours ago."""
    created = datetime.now(tz=UTC) - timedelta(hours=hours_ago)
    return (
        f"---\n"
        f"author: test-agent\n"
        f"created: {created.isoformat()}\n"
        f"scope: incomplete\n"
        f"---\n"
        f"\n"
        f"Work in progress.\n"
    )


def _setup_project(
    tmp_path: Path,
    *,
    ttl_hours: int = 72,
) -> tuple[Path, Path]:
    """Create a minimal project with config.yaml."""
    project_root = tmp_path
    lexibrary_dir = project_root / LEXIBRARY_DIR
    lexibrary_dir.mkdir()

    config = {"iwh": {"ttl_hours": ttl_hours}}
    (lexibrary_dir / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")

    return project_root, lexibrary_dir


def _write_iwh(
    lexibrary_dir: Path,
    mirror_path: str,
    *,
    hours_ago: int,
) -> Path:
    """Write an .iwh file at .lexibrary/<mirror_path>/.iwh."""
    iwh_dir = lexibrary_dir / mirror_path
    iwh_dir.mkdir(parents=True, exist_ok=True)
    iwh_file = iwh_dir / ".iwh"
    iwh_file.write_text(_iwh_content(hours_ago=hours_ago), encoding="utf-8")
    return iwh_file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckOrphanedIwhSignals:
    """Tests for check_orphaned_iwh_signals()."""

    def test_expired_signal_detected(self, tmp_path: Path) -> None:
        """An IWH signal older than ttl_hours is flagged."""
        project_root, lexibrary_dir = _setup_project(tmp_path, ttl_hours=24)
        _write_iwh(lexibrary_dir, "src/auth", hours_ago=48)

        issues = check_orphaned_iwh_signals(project_root, lexibrary_dir)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == "info"
        assert issue.check == "orphaned_iwh_signals"
        assert "expired" in issue.message
        assert "24h" in issue.message  # TTL value
        assert issue.suggestion is not None

    def test_fresh_signal_not_flagged(self, tmp_path: Path) -> None:
        """An IWH signal within ttl_hours produces no issues."""
        project_root, lexibrary_dir = _setup_project(tmp_path, ttl_hours=72)
        _write_iwh(lexibrary_dir, "src/auth", hours_ago=1)

        issues = check_orphaned_iwh_signals(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_ttl_disabled(self, tmp_path: Path) -> None:
        """When ttl_hours=0, no signals are flagged (TTL disabled)."""
        project_root, lexibrary_dir = _setup_project(tmp_path, ttl_hours=0)
        _write_iwh(lexibrary_dir, "src/old", hours_ago=1000)

        issues = check_orphaned_iwh_signals(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_no_iwh_files(self, tmp_path: Path) -> None:
        """When no .iwh files exist, returns empty list."""
        project_root, lexibrary_dir = _setup_project(tmp_path)

        issues = check_orphaned_iwh_signals(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_unparseable_iwh_skipped(self, tmp_path: Path) -> None:
        """Unparseable .iwh files are skipped (not flagged by this check)."""
        project_root, lexibrary_dir = _setup_project(tmp_path, ttl_hours=24)
        iwh_dir = lexibrary_dir / "src" / "broken"
        iwh_dir.mkdir(parents=True)
        (iwh_dir / ".iwh").write_text("not valid yaml frontmatter {{{", encoding="utf-8")

        issues = check_orphaned_iwh_signals(project_root, lexibrary_dir)
        assert len(issues) == 0

    def test_mixed_fresh_and_expired(self, tmp_path: Path) -> None:
        """Only expired signals are flagged; fresh ones are left alone."""
        project_root, lexibrary_dir = _setup_project(tmp_path, ttl_hours=24)
        _write_iwh(lexibrary_dir, "src/fresh", hours_ago=1)
        _write_iwh(lexibrary_dir, "src/expired", hours_ago=48)

        issues = check_orphaned_iwh_signals(project_root, lexibrary_dir)
        assert len(issues) == 1
        assert "src/expired" in issues[0].artifact


class TestOrphanedIwhSignalsInAvailableChecks:
    """Verify orphaned_iwh_signals is registered in AVAILABLE_CHECKS."""

    def test_registered(self) -> None:
        from lexibrary.validator import AVAILABLE_CHECKS

        assert "orphaned_iwh_signals" in AVAILABLE_CHECKS
        check_fn, severity = AVAILABLE_CHECKS["orphaned_iwh_signals"]
        assert check_fn is check_orphaned_iwh_signals
        assert severity == "info"
