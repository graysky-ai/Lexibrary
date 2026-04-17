"""End-to-end integration test for the orphaned_aindex curator path.

Phase 3 of the ``curator-freshness`` OpenSpec change retired the curator-side
``detect_orphaned_aindex`` detector and wired the narrow
``fix_orphaned_aindex`` action key through three layers:

* ``CHECK_TO_ACTION_KEY`` (coordinator) maps
  ``"orphaned_aindex"`` to ``"fix_orphaned_aindex"``.
* ``FIXERS`` (validator) registers
  :func:`lexibrary.validator.fixes.fix_orphaned_aindex` under the
  ``"orphaned_aindex"`` check name.
* ``RISK_TAXONOMY`` (curator) rates the action as ``low`` so it
  dispatches under ``full`` autonomy.

This test runs the full :meth:`Coordinator.run` pipeline against a
fixture containing an orphaned ``.aindex`` file (one whose corresponding
source directory has been removed) and asserts:

1. The resulting :class:`CuratorReport` contains a dispatched entry
   with ``action_key="fix_orphaned_aindex"`` and ``outcome="fixed"``.
2. The orphaned ``.aindex`` file is actually removed from disk.
3. No dispatched entry carries ``outcome="no_fixer"`` (which would
   indicate the validation bridge failed to locate a fixer for some
   check that fired).

Mirrors the structure of
``tests/test_curator/test_bidirectional_integration.py`` (group 4.4).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_integration_project(tmp_path: Path) -> Path:
    """Build a minimal project with a full ``.lexibrary/`` layout."""
    project = tmp_path / "orphaned_aindex_integration"
    project.mkdir()
    lex = project / LEXIBRARY_DIR
    lex.mkdir()
    for sub in ("designs", "concepts", "conventions", "playbooks", "stack"):
        (lex / sub).mkdir()
    (lex / "config.yaml").write_text("", encoding="utf-8")
    return project


def _write_orphan_aindex(project: Path, directory_path: str) -> Path:
    """Write an orphaned ``.aindex`` at ``.lexibrary/designs/<directory_path>/.aindex``.

    The source directory ``project/<directory_path>`` is deliberately NOT
    created — that is what makes the ``.aindex`` "orphaned".  The body is
    minimal non-parseable text so ``check_aindex_entries`` (which calls
    ``parse_aindex`` and returns ``None`` for malformed files) does not
    emit a spurious issue.
    """
    aindex = project / LEXIBRARY_DIR / DESIGNS_DIR / directory_path / ".aindex"
    aindex.parent.mkdir(parents=True, exist_ok=True)
    aindex.write_text("# placeholder\n", encoding="utf-8")
    return aindex


def _run(project: Path, *, autonomy: str = "full") -> object:
    """Run the coordinator under ``full`` autonomy so the fixer dispatches."""
    config = LexibraryConfig.model_validate({"curator": {"autonomy": autonomy}})
    coord = Coordinator(project, config)
    return asyncio.run(coord.run())


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestOrphanedAindexCoordinatorRoundtrip:
    """The full coordinator pipeline fixes an ``orphaned_aindex`` issue."""

    def test_coordinator_dispatches_fix_orphaned_aindex(self, tmp_path: Path) -> None:
        project = _setup_integration_project(tmp_path)

        # Seed a single orphaned .aindex whose corresponding source
        # directory (`src/removed_module/`) does not exist on disk.  The
        # validator's ``find_orphaned_aindex`` check will emit a
        # ``warning``-severity issue; the coordinator routes it via the
        # ``CHECK_TO_ACTION_KEY`` mapping to ``fix_orphaned_aindex``.
        orphan = _write_orphan_aindex(project, "src/removed_module")
        assert orphan.exists()

        report = _run(project)

        # The pipeline returns a CuratorReport with dispatched_details.
        assert hasattr(report, "dispatched_details")
        dispatched: list[dict[str, object]] = list(getattr(report, "dispatched_details", []))

        # No dispatched entry should be an un-routed validation issue
        # (``outcome="no_fixer"``).  A ``no_fixer`` here would indicate a
        # fixer-registration gap somewhere in the bridge.
        no_fixer_entries = [entry for entry in dispatched if entry.get("outcome") == "no_fixer"]
        assert not no_fixer_entries, (
            "Found dispatched entries with outcome='no_fixer'; "
            "fixer registration gaps. Entries: "
            f"{no_fixer_entries}"
        )

        # At least one dispatched entry must be the orphaned_aindex fixer
        # with ``outcome="fixed"``.
        orphaned_fixed = [
            entry
            for entry in dispatched
            if entry.get("action_key") == "fix_orphaned_aindex" and entry.get("outcome") == "fixed"
        ]
        assert orphaned_fixed, (
            "Expected at least one dispatched entry with "
            "action_key='fix_orphaned_aindex' and outcome='fixed'; "
            f"dispatched_details={dispatched}"
        )

        # The fixer deletes the orphan on disk — confirm the side effect
        # lands, not just the report bookkeeping.
        assert not orphan.exists(), (
            f"Expected orphan .aindex at {orphan} to be deleted by "
            "fix_orphaned_aindex, but it still exists."
        )
