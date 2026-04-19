"""Tests for ``fix_orphaned_iwh_signals`` validator fixer.

Covers the five behaviour branches specified in Group 13:

(a) expired signal is deleted, empty parent dirs cleaned up;
(b) signal now within TTL (re-checked at fix time) is NOT deleted;
(c) file already gone is a no-op;
(d) unparseable signal is left untouched;
(e) kill-switch ``config.validator.fix_orphaned_iwh_signals_delete=False``
    prevents deletion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from lexibrary.config.schema import (
    IWHConfig,
    LexibraryConfig,
    TokenBudgetConfig,
    ValidatorConfig,
)
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR
from lexibrary.validator.fixes import FIXERS, fix_orphaned_iwh_signals
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_CORRUPT_IWH_CONTENT = "this is not valid YAML frontmatter at all {{{"


def _iwh_content(created: datetime, *, scope: str = "incomplete") -> str:
    """Build a minimal valid .iwh file body with a caller-chosen ``created``."""
    iso = created.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"---\nauthor: test-agent\ncreated: {iso}\nscope: {scope}\n---\n\nsignal body\n"


def _write_iwh(
    lexibrary_dir: Path,
    directory_path: str,
    *,
    content: str,
) -> Path:
    """Write an .iwh file under ``.lexibrary/designs/<directory_path>/``."""
    iwh = lexibrary_dir / DESIGNS_DIR / directory_path / ".iwh"
    iwh.parent.mkdir(parents=True, exist_ok=True)
    iwh.write_text(content, encoding="utf-8")
    return iwh


def _make_config(
    *,
    ttl_hours: int = 72,
    delete_enabled: bool = True,
) -> LexibraryConfig:
    return LexibraryConfig(
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
        iwh=IWHConfig(ttl_hours=ttl_hours),
        validator=ValidatorConfig(fix_orphaned_iwh_signals_delete=delete_enabled),
    )


def _make_issue(artifact: str) -> ValidationIssue:
    return ValidationIssue(
        severity="info",
        check="orphaned_iwh_signals",
        message="IWH signal expired",
        artifact=artifact,
    )


# ---------------------------------------------------------------------------
# fix_orphaned_iwh_signals -- per-branch behaviour
# ---------------------------------------------------------------------------


class TestFixOrphanedIwhSignals:
    """Behaviour coverage for ``fix_orphaned_iwh_signals``."""

    def test_expired_signal_deleted_and_parents_cleaned(self, tmp_path: Path) -> None:
        """Expired signal is deleted; empty parents pruned up to designs root."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        designs_dir = lexibrary_dir / DESIGNS_DIR

        # 200h old vs default 72h TTL -> expired
        created = datetime.now(tz=UTC) - timedelta(hours=200)
        iwh_file = _write_iwh(
            lexibrary_dir,
            "src/stale/subpkg",
            content=_iwh_content(created),
        )
        assert iwh_file.exists()

        issue = _make_issue(f"{DESIGNS_DIR}/src/stale/subpkg/.iwh")
        config = _make_config()

        result = fix_orphaned_iwh_signals(issue, project_root, config)

        assert result.fixed is True
        assert "deleted expired IWH" in result.message
        assert "200h old" in result.message or "199h old" in result.message
        assert result.llm_calls == 0
        assert not iwh_file.exists()
        # Empty parents under designs/ are cleaned up
        assert not (designs_dir / "src" / "stale" / "subpkg").exists()
        assert not (designs_dir / "src" / "stale").exists()
        # designs root preserved
        assert designs_dir.exists()

    def test_signal_within_ttl_not_deleted(self, tmp_path: Path) -> None:
        """If TTL has been raised (or the signal is fresh), fixer declines."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        # 10h old — well inside the 72h default TTL.
        created = datetime.now(tz=UTC) - timedelta(hours=10)
        iwh_file = _write_iwh(
            lexibrary_dir,
            "src/recent",
            content=_iwh_content(created),
        )

        issue = _make_issue(f"{DESIGNS_DIR}/src/recent/.iwh")
        config = _make_config(ttl_hours=72)

        result = fix_orphaned_iwh_signals(issue, project_root, config)

        assert result.fixed is False
        assert result.message == "signal within TTL"
        assert iwh_file.exists(), "file must be preserved when within TTL"

    def test_already_consumed(self, tmp_path: Path) -> None:
        """If the file is already gone, returns fixed=False with a notice."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()
        (lexibrary_dir / DESIGNS_DIR).mkdir()

        issue = _make_issue(f"{DESIGNS_DIR}/src/gone/.iwh")
        config = _make_config()

        result = fix_orphaned_iwh_signals(issue, project_root, config)

        assert result.fixed is False
        assert result.message == "already consumed"

    def test_unparseable_not_deleted(self, tmp_path: Path) -> None:
        """Unparseable files are left untouched — orphaned_iwh handles those."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        iwh_file = _write_iwh(
            lexibrary_dir,
            "src/broken",
            content=_CORRUPT_IWH_CONTENT,
        )
        assert iwh_file.exists()
        original_text = iwh_file.read_text(encoding="utf-8")

        issue = _make_issue(f"{DESIGNS_DIR}/src/broken/.iwh")
        config = _make_config()

        result = fix_orphaned_iwh_signals(issue, project_root, config)

        assert result.fixed is False
        assert result.message == "parse error"
        assert iwh_file.exists(), "corrupt file must NOT be deleted by this fixer"
        assert iwh_file.read_text(encoding="utf-8") == original_text

    def test_kill_switch_disabled(self, tmp_path: Path) -> None:
        """When the kill-switch is off, deletion is skipped with a notice."""
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        created = datetime.now(tz=UTC) - timedelta(hours=200)
        iwh_file = _write_iwh(
            lexibrary_dir,
            "src/stale",
            content=_iwh_content(created),
        )

        issue = _make_issue(f"{DESIGNS_DIR}/src/stale/.iwh")
        config = _make_config(delete_enabled=False)

        result = fix_orphaned_iwh_signals(issue, project_root, config)

        assert result.fixed is False
        assert result.message == "auto-delete disabled by config"
        assert iwh_file.exists(), "file preserved when kill-switch is off"

    def test_ttl_zero_treated_as_within_ttl(self, tmp_path: Path) -> None:
        """``ttl_hours <= 0`` disables expiry — fixer declines to delete.

        Parity with ``check_orphaned_iwh_signals`` which also treats
        ``ttl_hours <= 0`` as "expiry disabled".
        """
        project_root = tmp_path
        lexibrary_dir = project_root / LEXIBRARY_DIR
        lexibrary_dir.mkdir()

        created = datetime.now(tz=UTC) - timedelta(hours=1000)
        iwh_file = _write_iwh(
            lexibrary_dir,
            "src/old",
            content=_iwh_content(created),
        )

        issue = _make_issue(f"{DESIGNS_DIR}/src/old/.iwh")
        config = _make_config(ttl_hours=0)

        result = fix_orphaned_iwh_signals(issue, project_root, config)

        assert result.fixed is False
        assert result.message == "signal within TTL"
        assert iwh_file.exists()


# ---------------------------------------------------------------------------
# FIXERS registry
# ---------------------------------------------------------------------------


class TestOrphanedIwhSignalsInFixersRegistry:
    """Verify ``orphaned_iwh_signals`` is registered alongside ``orphaned_iwh``."""

    def test_new_key_registered(self) -> None:
        assert "orphaned_iwh_signals" in FIXERS
        assert FIXERS["orphaned_iwh_signals"] is fix_orphaned_iwh_signals

    def test_existing_key_preserved(self) -> None:
        """Ensure the pre-existing ``orphaned_iwh`` entry is still wired."""
        from lexibrary.validator.fixes import fix_orphaned_iwh  # noqa: PLC0415

        assert "orphaned_iwh" in FIXERS
        assert FIXERS["orphaned_iwh"] is fix_orphaned_iwh
