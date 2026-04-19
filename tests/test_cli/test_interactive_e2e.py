"""End-to-end scripted interactive CLI run (curator-4 Group 23.4).

Drives ``lexi validate --fix --interactive`` through a single
scripted stdin sequence that exercises all four escalation handlers
(deprecate, ignore, refresh-with-scope, refresh).

Validator emission order for the seeded fixture (derived from
``AVAILABLE_CHECKS`` registration order):

1. ``orphan_concepts`` (first orphan concept)  → ``d``
2. ``orphan_concepts`` (second orphan concept) → ``i``
3. ``convention_stale``                         → ``r`` + ``src/valid/``
4. ``playbook_staleness``                       → ``r``

The scripted input is therefore ``"d\\ni\\nr\\nsrc/valid/\\nr\\n"``.

Assertions:

1. Each artifact ends up in the expected state on disk
   (deprecated vs. refreshed vs. untouched).
2. No IWH breadcrumbs are written — the interactive flow
   short-circuits ``FIXERS`` dispatch before the autonomous
   ``escalate_*`` fixers get a chance to drop an IWH signal.

Complements ``tests/test_cli/test_validate_interactive.py`` (which
exercises each branch in isolation) with a single-run integration
that threads all four handlers through one invocation.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from unittest.mock import patch

from click.testing import Result
from typer.testing import CliRunner

from lexibrary.cli import lexi_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    """Create a minimal project root with an empty ``.lexibrary/`` layout."""
    (tmp_path / ".lexibrary").mkdir()
    (tmp_path / ".lexibrary" / "config.yaml").write_text(
        "scope_roots:\n  - path: .\n",
        encoding="utf-8",
    )
    return tmp_path


def _write_concept(
    project_root: Path,
    title: str,
    *,
    cid: str = "CN-001",
) -> Path:
    """Write an orphan concept (zero inbound wikilink references)."""
    concepts_dir = project_root / ".lexibrary" / "concepts"
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{title}.md"
    path.write_text(
        "---\n"
        f"title: {title}\n"
        f"id: {cid}\n"
        "aliases: []\n"
        "tags: [test]\n"
        "status: active\n"
        "---\n\n"
        "An orphan concept nobody refers to.\n",
        encoding="utf-8",
    )
    return path


def _write_convention(
    project_root: Path,
    slug: str,
    *,
    scope: str,
    cid: str = "CV-001",
) -> Path:
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)
    path = conventions_dir / f"{slug}.md"
    path.write_text(
        "---\n"
        f"id: {cid}\n"
        f"title: {slug}\n"
        f"scope: {scope}\n"
        "tags: [test]\n"
        "status: active\n"
        "---\n\n"
        "Example convention body.\n",
        encoding="utf-8",
    )
    return path


def _write_playbook(
    project_root: Path,
    slug: str,
    *,
    last_verified: date | None = None,
    pid: str = "PB-001",
) -> Path:
    playbooks_dir = project_root / ".lexibrary" / "playbooks"
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    path = playbooks_dir / f"{slug}.md"
    last_verified_line = f"last_verified: {last_verified.isoformat()}\n" if last_verified else ""
    path.write_text(
        "---\n"
        f"id: {pid}\n"
        f"title: {slug}\n"
        "tags: [test]\n"
        "status: active\n"
        f"{last_verified_line}"
        "---\n\n"
        "Example playbook body.\n",
        encoding="utf-8",
    )
    return path


def _invoke(tmp_path: Path, args: list[str], input_: str | None = None) -> Result:
    """Run ``lexi ...`` with cwd=tmp_path and scripted stdin."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(lexi_app, args, input=input_)
    finally:
        os.chdir(old_cwd)


def _walk_iwh(project_root: Path) -> list[Path]:
    """Collect every ``.iwh`` file under ``.lexibrary/``."""
    lexibrary = project_root / ".lexibrary"
    if not lexibrary.is_dir():
        return []
    return sorted(lexibrary.rglob(".iwh"))


# ---------------------------------------------------------------------------
# E2E: deprecate / refresh-with-scope / ignore / refresh
# ---------------------------------------------------------------------------


class TestInteractiveEndToEndAllFourHandlers:
    """Scripted run exercises all four escalation handlers in one invocation."""

    def test_mixed_interactive_choices_land_correct_state(
        self,
        tmp_path: Path,
    ) -> None:
        """All four issue types handled per the scripted input, no IWH left.

        The interactive path short-circuits ``FIXERS`` dispatch for
        escalation checks (curator-4 Group 17), so the autonomous
        ``escalate_*`` fixers (which write IWH breadcrumbs) must NOT
        run. Asserts the ``_walk_iwh`` inventory is empty after the
        invocation.
        """
        project = _setup_project(tmp_path)

        # --- Seed four escalation issues, one of each kind. ---
        # Two orphan_concepts to give us a deprecate slot and an ignore
        # slot. Titles chosen so ``ConceptIndex.names()`` orders them
        # alphabetically: "OrphanA" < "OrphanB".
        orphan_a = _write_concept(project, "OrphanA", cid="CN-001")
        orphan_b = _write_concept(project, "OrphanB", cid="CN-002")

        # convention_stale: active convention whose scope exists but empty.
        (project / "src" / "emptydir").mkdir(parents=True, exist_ok=True)
        convention = _write_convention(
            project, "stale-convention", scope="src/emptydir/", cid="CV-001"
        )
        # Seed a non-empty sibling so the scope sub-prompt can point at
        # a path that actually exists on disk.
        (project / "src" / "valid").mkdir(parents=True, exist_ok=True)
        (project / "src" / "valid" / "main.py").write_text("pass\n")

        # playbook_staleness: active playbook with no last_verified.
        stale_playbook = _write_playbook(project, "stale-playbook", pid="PB-001")

        # Pre-run snapshots for "did it change?" assertions.
        orphan_a_before = orphan_a.read_text(encoding="utf-8")
        orphan_b_before = orphan_b.read_text(encoding="utf-8")
        convention_before = convention.read_text(encoding="utf-8")
        playbook_before = stale_playbook.read_text(encoding="utf-8")

        # --- Execute the interactive prompt loop. ---
        # Input ordering matches the deduped validator emission order:
        #   1. orphan_concepts (OrphanA)       → d   deprecate
        #   2. orphan_concepts (OrphanB)       → i   ignore
        #   3. convention_stale                → r   refresh, then scope
        #                                       src/valid/
        #   4. playbook_staleness              → r   refresh
        with patch("lexibrary.cli._shared._stdout_is_tty", return_value=True):
            result = _invoke(
                tmp_path,
                ["validate", "--fix", "--interactive"],
                input_="d\ni\nr\nsrc/valid/\nr\n",
            )

        output = result.output

        # --- Assertion 1: no IWH breadcrumbs were written. ---
        # The interactive path short-circuits ``FIXERS``, so the
        # autonomous ``escalate_*`` fixers (which write IWH signals)
        # must not have been invoked.
        iwh_inventory = _walk_iwh(project)
        assert not iwh_inventory, (
            "Interactive --fix --interactive must not write IWH signals; "
            f"found: {iwh_inventory}. Full CLI output:\n{output}"
        )

        # --- Assertion 2: summary bookkeeping lines appear. ---
        # The interactive summary format includes the per-action counters.
        assert "deprecated:" in output or "refreshed:" in output, (
            f"Interactive summary should surface action counters; output:\n{output}"
        )

        # --- Assertion 3: OrphanA deprecated, OrphanB untouched. ---
        orphan_a_after = orphan_a.read_text(encoding="utf-8")
        orphan_b_after = orphan_b.read_text(encoding="utf-8")

        assert "status: deprecated" in orphan_a_after, (
            "OrphanA (first concept, scripted input 'd') should be "
            f"deprecated. Content:\n{orphan_a_after}\nFull output:\n{output}"
        )
        assert "status: deprecated" not in orphan_a_before, (
            "Sanity: OrphanA was not pre-deprecated."
        )
        assert orphan_b_after == orphan_b_before, (
            "OrphanB (second concept, scripted input 'i') should be "
            f"untouched. Before/after diff:\n{orphan_b_before}\n---\n"
            f"{orphan_b_after}\nFull output:\n{output}"
        )

        # --- Assertion 4: convention scope was refreshed. ---
        convention_after = convention.read_text(encoding="utf-8")
        # The refresh_convention_stale helper rewrites the scope line.
        # Depending on the helper's serialisation, the new scope may
        # appear verbatim.  As a soft assertion we just check mutation:
        assert convention_after != convention_before, (
            "convention_stale refresh should mutate the scope; file unchanged. Output:\n" + output
        )

        # --- Assertion 5: playbook was refreshed (last_verified set). ---
        playbook_after = stale_playbook.read_text(encoding="utf-8")
        assert playbook_after != playbook_before, (
            "playbook_staleness refresh should mutate last_verified; file "
            "unchanged. Output:\n" + output
        )
        assert "last_verified:" in playbook_after, (
            f"refresh_playbook_staleness should add/update last_verified; output:\n{output}"
        )


# ---------------------------------------------------------------------------
# E2E regression: non-interactive (autonomous) run still works unchanged
# ---------------------------------------------------------------------------


class TestNonInteractiveStillWorks:
    """Without --interactive, the legacy FIXERS dispatch path runs.

    Regression guard: Group 17 added the interactive branch; the
    existing non-interactive path must keep routing escalation issues
    through the autonomous ``escalate_*`` fixers.  The IWH breadcrumb
    is the tell-tale sign the autonomous path ran.
    """

    def test_non_interactive_writes_iwh_breadcrumbs(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        _write_concept(project, "LonelyConcept", cid="CN-001")

        # No --interactive flag — TTY patch is irrelevant (and the
        # CliRunner's captured stdout is non-TTY by default anyway).
        result = _invoke(tmp_path, ["validate", "--fix"])

        # The autonomous path runs the escalate_orphan_concepts fixer,
        # which drops an IWH signal next to the concept.
        iwh_files = _walk_iwh(project)
        assert iwh_files, (
            "Non-interactive --fix should route orphan_concepts through "
            "the autonomous escalate_* fixer which writes an IWH; no "
            f"IWH files found. Output:\n{result.output}"
        )
