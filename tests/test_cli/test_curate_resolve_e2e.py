"""End-to-end ``lexictl curate resolve`` against a fixture report.

Curator-4 Group 23.5: drives the admin replay path through a full
scripted interaction — seed a ``pending_decisions`` report with IWH
breadcrumbs, invoke ``lexictl curate resolve``, feed it scripted
input, and assert the breadcrumbs are cleaned up after successful
(non-ignore) resolutions.

Complements ``tests/test_cli/test_lexictl_curate_resolve.py``
(which exercises each behaviour in isolation) with a multi-decision
scripted run that mirrors real admin usage.

Per curator-4 tasks.md Note 4: agents must NOT invoke ``lexictl``
directly — this file uses ``typer.testing.CliRunner`` against the
``lexictl_app`` callable instead of shelling out.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from click.testing import Result
from typer.testing import CliRunner

from lexibrary.cli import lexictl_app

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


def _write_concept(project_root: Path, title: str, *, cid: str = "CN-001") -> Path:
    """Write a minimal active concept."""
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
        "A concept that needs an operator decision.\n",
        encoding="utf-8",
    )
    return path


def _write_iwh_breadcrumb(project_root: Path, concept_title: str) -> Path:
    """Seed an IWH breadcrumb file for *concept_title* in the designs dir."""
    iwh_path = project_root / ".lexibrary" / "designs" / f"{concept_title}.iwh"
    iwh_path.parent.mkdir(parents=True, exist_ok=True)
    iwh_path.write_text(
        "---\n"
        "author: curator\n"
        "created: 2026-04-01T12:00:00Z\n"
        "scope: warning\n"
        "---\n\n"
        f"escalation: orphan_concepts — concept {concept_title} has zero "
        "inbound link-graph references\n",
        encoding="utf-8",
    )
    return iwh_path


def _write_report_with_pending(
    project_root: Path,
    *,
    pending: list[dict[str, object]],
    timestamp: str = "20260410T120000Z",
) -> Path:
    """Write a curator-report JSON with ``pending_decisions`` populated."""
    reports_dir = project_root / ".lexibrary" / "curator" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_file = reports_dir / f"{timestamp}.json"
    data = {
        "schema_version": 4,
        "timestamp": timestamp,
        "trigger": "on_demand",
        "checked": 0,
        "fixed": 0,
        "stubbed": 0,
        "deferred": 0,
        "errored": 0,
        "errors": [],
        "sub_agent_calls": {},
        "dispatched": [],
        "deferred_details": [],
        "deprecated": 0,
        "hard_deleted": 0,
        "migrations_applied": 0,
        "migrations_proposed": 0,
        "budget_condensed": 0,
        "budget_proposed": 0,
        "comments_flagged": 0,
        "descriptions_audited": 0,
        "summaries_audited": 0,
        "pending_decisions": pending,
    }
    report_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return report_file


def _invoke(tmp_path: Path, args: list[str], *, input_: str | None = None) -> Result:
    """Invoke the ``lexictl`` app with ``cwd`` set to the project root."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return runner.invoke(lexictl_app, args, input=input_)
    finally:
        os.chdir(old_cwd)


# ---------------------------------------------------------------------------
# E2E: scripted resolve with mixed decisions
# ---------------------------------------------------------------------------


class TestResolveEndToEndIwhCleanup:
    """Scripted ``lexictl curate resolve`` against a multi-decision report.

    Seeds three concepts with three corresponding pending decisions and
    three IWH breadcrumbs, then feeds ``d\\nr\\ni\\n`` to the CLI:

    * decision 1 (concept DeprecateMe)  → ``d`` (deprecate)  → IWH deleted
    * decision 2 (concept RefreshMe)    → ``r`` (refresh)    → IWH deleted
    * decision 3 (concept IgnoreMe)     → ``i`` (ignore)     → IWH preserved

    Assertions:

    1. IWH breadcrumbs for the first two decisions are gone after the run.
    2. IWH breadcrumb for the ignored decision survives.
    3. The CLI reports ``resolved: 3/3`` and per-action counters match.
    """

    def test_deprecate_and_refresh_delete_iwh_ignore_preserves(
        self,
        tmp_path: Path,
    ) -> None:
        project = _setup_project(tmp_path)

        concept_deprecate = _write_concept(project, "DeprecateMe", cid="CN-D01")
        concept_refresh = _write_concept(project, "RefreshMe", cid="CN-R01")
        concept_ignore = _write_concept(project, "IgnoreMe", cid="CN-I01")

        iwh_deprecate = _write_iwh_breadcrumb(project, "DeprecateMe")
        iwh_refresh = _write_iwh_breadcrumb(project, "RefreshMe")
        iwh_ignore = _write_iwh_breadcrumb(project, "IgnoreMe")
        assert iwh_deprecate.exists()
        assert iwh_refresh.exists()
        assert iwh_ignore.exists()

        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_deprecate),
                    "message": "concept has zero inbound refs",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_deprecate),
                },
                {
                    "check": "orphan_concepts",
                    "path": str(concept_refresh),
                    "message": "concept has zero inbound refs",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_refresh),
                },
                {
                    "check": "orphan_concepts",
                    "path": str(concept_ignore),
                    "message": "concept has zero inbound refs",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_ignore),
                },
            ],
        )

        # Run `lexictl curate resolve` without any mocks — the real
        # lifecycle helpers run and mutate the concepts on disk.
        result = _invoke(tmp_path, ["curate", "resolve"], input_="d\nr\ni\n")

        assert result.exit_code == 0, f"Output:\n{result.output}"

        # --- Assertion 1: breadcrumbs for deprecate + refresh are gone. ---
        assert not iwh_deprecate.exists(), (
            "IWH for the deprecated concept should be deleted on success; "
            f"still present at {iwh_deprecate}. Output:\n{result.output}"
        )
        assert not iwh_refresh.exists(), (
            "IWH for the refreshed concept should be deleted on success; "
            f"still present at {iwh_refresh}. Output:\n{result.output}"
        )

        # --- Assertion 2: breadcrumb for ignored decision survives. ---
        assert iwh_ignore.exists(), (
            "IWH for an ignored decision must survive for later review; "
            f"missing at {iwh_ignore}. Output:\n{result.output}"
        )

        # --- Assertion 3: summary reports the counters. ---
        output = result.output
        assert "resolved: 3/3" in output, (
            f"Summary line should report resolved: 3/3; output:\n{output}"
        )
        assert "deprecated: 1" in output, f"Summary should count one deprecation; output:\n{output}"
        assert "refreshed: 1" in output, f"Summary should count one refresh; output:\n{output}"
        assert "ignored: 1" in output, f"Summary should count one ignore; output:\n{output}"

        # --- Assertion 4: on-disk concept states reflect the decisions. ---
        deprecate_body = concept_deprecate.read_text(encoding="utf-8")
        assert "status: deprecated" in deprecate_body, (
            f"DeprecateMe should be marked deprecated after resolve. Body:\n{deprecate_body}"
        )

        refresh_body = concept_refresh.read_text(encoding="utf-8")
        assert "last_verified:" in refresh_body, (
            f"RefreshMe should have a last_verified date after resolve. Body:\n{refresh_body}"
        )

        ignore_body = concept_ignore.read_text(encoding="utf-8")
        assert "status: active" in ignore_body, (
            f"IgnoreMe should remain active after resolve. Body:\n{ignore_body}"
        )


# ---------------------------------------------------------------------------
# E2E: --batch-ignore-all preserves all breadcrumbs and resolves everything
# ---------------------------------------------------------------------------


class TestResolveBatchIgnoreAllEndToEnd:
    """``--batch-ignore-all`` resolves everything as ignored, keeps IWH."""

    def test_batch_ignore_resolves_all_and_keeps_breadcrumbs(
        self,
        tmp_path: Path,
    ) -> None:
        project = _setup_project(tmp_path)

        concept_a = _write_concept(project, "AlphaConcept", cid="CN-A01")
        concept_b = _write_concept(project, "BetaConcept", cid="CN-B01")

        iwh_a = _write_iwh_breadcrumb(project, "AlphaConcept")
        iwh_b = _write_iwh_breadcrumb(project, "BetaConcept")

        _write_report_with_pending(
            project,
            pending=[
                {
                    "check": "orphan_concepts",
                    "path": str(concept_a),
                    "message": "msg",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_a),
                },
                {
                    "check": "orphan_concepts",
                    "path": str(concept_b),
                    "message": "msg",
                    "suggested_actions": ["ignore", "deprecate", "refresh"],
                    "iwh_path": str(iwh_b),
                },
            ],
        )

        # Don't pass stdin — --batch-ignore-all must skip prompts.
        result = _invoke(tmp_path, ["curate", "resolve", "--batch-ignore-all"])

        assert result.exit_code == 0, f"Output:\n{result.output}"
        assert "resolved: 2/2" in result.output
        assert "ignored: 2" in result.output
        # Batch mode preserves breadcrumbs — the durable marker survives.
        assert iwh_a.exists(), "batch-ignore-all must preserve IWH breadcrumbs for later review"
        assert iwh_b.exists(), "batch-ignore-all must preserve IWH breadcrumbs for later review"
