"""End-to-end integration test for the wikilink_resolution curator path.

Phase 4 Family D of the ``curator-freshness`` OpenSpec change retired
the curator-side ``check_wikilinks`` detector and wired the narrow
``fix_wikilink_resolution`` action key through three layers:

* ``CHECK_TO_ACTION_KEY`` (coordinator) maps
  ``"wikilink_resolution"`` to ``"fix_wikilink_resolution"``.
* ``FIXERS`` (validator) registers
  :func:`lexibrary.validator.fixes.fix_wikilink_resolution` under the
  ``"wikilink_resolution"`` check name.
* ``RISK_TAXONOMY`` (curator) rates the action as ``low`` so it
  dispatches under ``full`` autonomy.

This test runs the full :meth:`Coordinator.run` pipeline against a
fixture containing a design file with an unresolved wikilink and asserts:

1. The resulting :class:`CuratorReport` contains a dispatched entry
   with ``action_key="fix_wikilink_resolution"`` and ``outcome="fixed"``.
2. No dispatched entry carries ``outcome="no_fixer"`` (which would
   indicate a fixer-registration gap somewhere in the bridge).

``fix_wikilink_resolution`` delegates to
:func:`lexibrary.archivist.pipeline.update_file`, which normally invokes
the BAML/LLM runtime.  The integration test stubs ``update_file`` with a
deterministic stand-in (refreshes footer hashes only) so the assertion
covers the routing — not the LLM behaviour.

Mirrors the structure of
``tests/test_curator/test_bidirectional_integration.py`` (group 4.4)
and ``tests/test_curator/test_orphaned_aindex_integration.py`` (group 6.3).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_integration_project(tmp_path: Path) -> Path:
    """Build a minimal project with a full ``.lexibrary/`` layout."""
    project = tmp_path / "wikilink_resolution_integration"
    project.mkdir()
    lex = project / LEXIBRARY_DIR
    lex.mkdir()
    for sub in ("designs", "concepts", "conventions", "playbooks", "stack"):
        (lex / sub).mkdir()
    (lex / "config.yaml").write_text("", encoding="utf-8")
    return project


def _write_source(project: Path, rel: str, body: str) -> Path:
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_design_with_broken_wikilink(
    project: Path,
    source_rel: str,
    *,
    source_body: str,
    wikilink_target: str,
) -> Path:
    """Write a design file whose wikilinks list contains *wikilink_target*.

    ``source_hash`` is computed from *source_body* so ``hash_freshness``
    does not pre-empt the wikilink_resolution dispatch.  Authorship stays
    ``archivist`` so ``check_stale_agent_design`` does not fire either.
    """
    from lexibrary.ast_parser import compute_hashes  # noqa: PLC0415

    source_path = project / source_rel
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source_body, encoding="utf-8")
    source_hash, interface_hash = compute_hashes(source_path)

    design_path = project / LEXIBRARY_DIR / DESIGNS_DIR / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id="DS-001",
            updated_by="archivist",
            status="active",
        ),
        summary=f"Summary of {source_rel}",
        interface_contract="def foo(): ...",
        dependencies=[],
        dependents=[],
        wikilinks=[wikilink_target],
        metadata=StalenessMetadata(
            source=source_rel,
            source_hash=source_hash,
            interface_hash=interface_hash,
            generated=datetime.now(UTC),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _run(project: Path, *, autonomy: str = "full") -> object:
    """Run the coordinator under ``full`` autonomy so the fixer dispatches."""
    config = LexibraryConfig.model_validate({"curator": {"autonomy": autonomy}})
    coord = Coordinator(project, config)
    return asyncio.run(coord.run())


# ---------------------------------------------------------------------------
# Deterministic archivist stub
# ---------------------------------------------------------------------------


@pytest.fixture()
def deterministic_update_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``archivist.pipeline.update_file`` with a deterministic stub.

    ``fix_wikilink_resolution`` invokes the archivist pipeline, which
    normally regenerates the design body via a BAML/LLM runtime.  The
    integration test must not depend on a live LLM, so this fixture
    swaps the pipeline call for a stand-in that refreshes only the footer
    hashes of the existing design file in place — same return contract as
    the real ``update_file`` so the fixer reads ``result.failed`` and
    reports ``fixed=True`` on success.

    Mirrors the ``deterministic_hash_freshness`` fixture pattern used in
    ``tests/test_curator/test_validation_roundtrip.py``.
    """
    from lexibrary.archivist import pipeline as archivist_pipeline
    from lexibrary.archivist.change_checker import ChangeLevel
    from lexibrary.archivist.pipeline import FileResult, _refresh_footer_hashes
    from lexibrary.ast_parser import compute_hashes
    from lexibrary.utils.paths import mirror_path

    async def stub_update_file(
        source_path: Path,
        project_root: Path,
        config: Any,
        archivist: Any,
        available_artifacts: list[str] | None = None,
        *,
        force: bool = False,
        unlimited: bool = False,
    ) -> FileResult:
        design_path = mirror_path(project_root, source_path)
        if not design_path.exists():
            return FileResult(
                change=ChangeLevel.UNCHANGED,
                failed=True,
                failure_reason="design file missing",
            )
        content_hash, interface_hash = compute_hashes(source_path)
        _refresh_footer_hashes(design_path, content_hash, interface_hash, project_root)
        return FileResult(change=ChangeLevel.CONTENT_ONLY)

    monkeypatch.setattr(archivist_pipeline, "update_file", stub_update_file)


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


class TestWikilinkResolutionCoordinatorRoundtrip:
    """The full coordinator pipeline fixes a ``wikilink_resolution`` issue."""

    def test_coordinator_dispatches_fix_wikilink_resolution(
        self,
        tmp_path: Path,
        deterministic_update_file: None,
    ) -> None:
        project = _setup_integration_project(tmp_path)

        # Plant a design file with an unresolved wikilink. No matching
        # concept file exists, so ``check_wikilink_resolution`` will emit
        # an error-severity issue against the design path.  The
        # coordinator routes it via ``CHECK_TO_ACTION_KEY`` to
        # ``fix_wikilink_resolution``, which delegates to the
        # (stubbed) archivist pipeline.
        _write_design_with_broken_wikilink(
            project,
            "src/foo.py",
            source_body="def foo(): pass\n",
            wikilink_target="NonexistentConcept",
        )

        report = _run(project)

        # The pipeline returns a CuratorReport with dispatched_details.
        assert hasattr(report, "dispatched_details")
        dispatched: list[dict[str, object]] = list(getattr(report, "dispatched_details", []))

        # No dispatched entry should be an un-routed validation issue
        # (``outcome="no_fixer"``).  A ``no_fixer`` here would mean the
        # validation bridge failed to locate a fixer for one of the
        # checks that fired — the fixture is tuned so only
        # ``wikilink_resolution`` (and possibly other fixable checks)
        # produce issues.
        no_fixer_entries = [entry for entry in dispatched if entry.get("outcome") == "no_fixer"]
        assert not no_fixer_entries, (
            "Found dispatched entries with outcome='no_fixer'; "
            "fixer registration gaps. Entries: "
            f"{no_fixer_entries}"
        )

        # At least one dispatched entry must be the wikilink fixer with
        # ``outcome="fixed"``.
        wikilink_fixed = [
            entry
            for entry in dispatched
            if entry.get("action_key") == "fix_wikilink_resolution"
            and entry.get("outcome") == "fixed"
        ]
        assert wikilink_fixed, (
            "Expected at least one dispatched entry with "
            "action_key='fix_wikilink_resolution' and outcome='fixed'; "
            f"dispatched_details={dispatched}"
        )
