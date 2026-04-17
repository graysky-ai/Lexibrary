"""End-to-end integration tests for the duplicate_slugs / duplicate_aliases paths.

Phase 4 Family B of the ``curator-freshness`` OpenSpec change retired the
curator-side ``detect_slug_collisions`` / ``detect_alias_collisions``
detectors and wired narrow ``fix_duplicate_slugs`` / ``fix_duplicate_aliases``
action keys through three layers:

* ``CHECK_TO_ACTION_KEY`` (coordinator) maps
  ``"duplicate_slugs"`` → ``"fix_duplicate_slugs"`` and
  ``"duplicate_aliases"`` → ``"fix_duplicate_aliases"``.
* ``FIXERS`` (validator) registers
  :func:`lexibrary.validator.fixes.fix_duplicate_slugs` and
  :func:`lexibrary.validator.fixes.fix_duplicate_aliases`. Both are
  **propose-only** — they emit ``FixResult(fixed=False,
  message="requires manual resolution")``.
* ``RISK_TAXONOMY`` (curator) rates both actions as ``low`` so they
  dispatch under ``full`` autonomy.

These tests run the full :meth:`Coordinator.run` pipeline against
fixtures containing the collisions the validator checks target and
assert that:

1. The resulting ``CuratorReport`` contains a dispatched entry with
   ``action_key="fix_duplicate_slugs"`` / ``"fix_duplicate_aliases"``
   and ``outcome="fixer_failed"`` (the bridge's mapping for ``fixed=False``).
2. The fixer message is exactly ``"requires manual resolution"``.
3. The colliding artifacts are still present on disk — propose-only
   fixers must not mutate the library.
4. No dispatched entry carries ``outcome="no_fixer"`` (which would
   indicate a registration gap in the bridge).

Mirrors the structure of :mod:`tests.test_curator.test_orphaned_aindex_integration`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.utils.paths import LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_integration_project(tmp_path: Path) -> Path:
    """Build a minimal project with a full ``.lexibrary/`` layout."""
    project = tmp_path / "duplicate_integration"
    project.mkdir()
    lex = project / LEXIBRARY_DIR
    lex.mkdir()
    for sub in ("designs", "concepts", "conventions", "playbooks", "stack"):
        (lex / sub).mkdir()
    (lex / "config.yaml").write_text("", encoding="utf-8")
    return project


def _write_concept(
    project: Path,
    file_name: str,
    *,
    title: str,
    concept_id: str,
    aliases: list[str] | None = None,
) -> Path:
    """Write a concept file with the given filename + frontmatter."""
    path = project / LEXIBRARY_DIR / "concepts" / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = {
        "title": title,
        "id": concept_id,
        "status": "active",
        "aliases": aliases or [],
        "tags": ["general"],
    }
    path.write_text(
        f"---\n{yaml.dump(fm, default_flow_style=False)}---\n\n{title}\n",
        encoding="utf-8",
    )
    return path


def _run(project: Path, *, autonomy: str = "full") -> object:
    """Run the coordinator under ``full`` autonomy so the fixer dispatches."""
    config = LexibraryConfig.model_validate({"curator": {"autonomy": autonomy}})
    coord = Coordinator(project, config)
    return asyncio.run(coord.run())


def _dispatched(report: object) -> list[dict[str, object]]:
    assert hasattr(report, "dispatched_details")
    return list(getattr(report, "dispatched_details", []))


def _assert_no_family_b_no_fixer_entries(dispatched: list[dict[str, object]]) -> None:
    """Guard against Family B bridge-registration regressions.

    Only flags ``no_fixer`` outcomes whose ``action_key`` is one of the
    narrow Family B keys — unrelated validator checks
    (e.g. ``orphan_concepts``, ``supersession_candidate``) are expected
    to emit ``no_fixer`` entries because their fixers are intentionally
    unregistered (they require human review).
    """
    family_b_keys = {"fix_duplicate_slugs", "fix_duplicate_aliases"}
    regressions = [
        e
        for e in dispatched
        if e.get("outcome") == "no_fixer" and e.get("action_key") in family_b_keys
    ]
    assert not regressions, (
        "Found Family B dispatched entries with outcome='no_fixer'; "
        f"fixer registration gap. Entries: {regressions}"
    )


# ---------------------------------------------------------------------------
# duplicate_slugs integration
# ---------------------------------------------------------------------------


class TestDuplicateSlugsCoordinatorRoundtrip:
    """The full coordinator pipeline dispatches ``fix_duplicate_slugs`` propose-only."""

    def test_coordinator_dispatches_fix_duplicate_slugs(self, tmp_path: Path) -> None:
        project = _setup_integration_project(tmp_path)

        # Two concept files whose filename stems (after stripping the
        # ``CN-NNN-`` ID prefix) both reduce to ``error-handling``.  The
        # validator's ``check_duplicate_slugs`` emits a ``warning``-severity
        # issue; the coordinator routes it via ``CHECK_TO_ACTION_KEY`` to
        # ``fix_duplicate_slugs`` (propose-only).
        colliding_a = _write_concept(
            project,
            "CN-001-error-handling.md",
            title="Error Handling",
            concept_id="CN-001",
        )
        colliding_b = _write_concept(
            project,
            "CN-002-error-handling.md",
            title="Error Handling v2",
            concept_id="CN-002",
        )

        report = _run(project)
        dispatched = _dispatched(report)
        _assert_no_family_b_no_fixer_entries(dispatched)

        proposed = [
            e
            for e in dispatched
            if e.get("action_key") == "fix_duplicate_slugs" and e.get("outcome") == "fixer_failed"
        ]
        assert proposed, (
            "Expected at least one dispatched entry with "
            "action_key='fix_duplicate_slugs' and outcome='fixer_failed' "
            f"(propose-only); dispatched_details={dispatched}"
        )

        # Every ``fix_duplicate_slugs`` entry must carry the documented
        # propose-only message.
        messages = {e.get("message") for e in proposed}
        assert messages == {"requires manual resolution"}, (
            "Expected every fix_duplicate_slugs entry to surface the "
            f"'requires manual resolution' message; got {messages!r}"
        )

        # Propose-only means nothing on disk changes.
        assert colliding_a.exists()
        assert colliding_b.exists()


# ---------------------------------------------------------------------------
# duplicate_aliases integration
# ---------------------------------------------------------------------------


class TestDuplicateAliasesCoordinatorRoundtrip:
    """The full coordinator pipeline dispatches ``fix_duplicate_aliases`` propose-only."""

    def test_coordinator_dispatches_fix_duplicate_aliases(self, tmp_path: Path) -> None:
        project = _setup_integration_project(tmp_path)

        # Two concept files sharing an alias (``auth``).  The validator's
        # ``check_duplicate_aliases`` emits an ``error``-severity issue
        # per affected file; the coordinator routes both through
        # ``fix_duplicate_aliases`` (propose-only).
        colliding_a = _write_concept(
            project,
            "CN-010-alpha.md",
            title="Alpha",
            concept_id="CN-010",
            aliases=["auth"],
        )
        colliding_b = _write_concept(
            project,
            "CN-011-beta.md",
            title="Beta",
            concept_id="CN-011",
            aliases=["auth"],
        )

        report = _run(project)
        dispatched = _dispatched(report)
        _assert_no_family_b_no_fixer_entries(dispatched)

        proposed = [
            e
            for e in dispatched
            if e.get("action_key") == "fix_duplicate_aliases" and e.get("outcome") == "fixer_failed"
        ]
        assert proposed, (
            "Expected at least one dispatched entry with "
            "action_key='fix_duplicate_aliases' and outcome='fixer_failed' "
            f"(propose-only); dispatched_details={dispatched}"
        )

        messages = {e.get("message") for e in proposed}
        assert messages == {"requires manual resolution"}, (
            "Expected every fix_duplicate_aliases entry to surface the "
            f"'requires manual resolution' message; got {messages!r}"
        )

        # Propose-only means nothing on disk changes.
        assert colliding_a.exists()
        assert colliding_b.exists()
