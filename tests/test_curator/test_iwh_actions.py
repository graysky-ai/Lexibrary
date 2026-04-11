"""Unit and integration tests for curator.iwh_actions (curator-fix group 9).

Each of the three residual IWH handlers is exercised in isolation with a
fabricated :class:`TriageItem` and a minimal :class:`DispatchContext`.  A
separate end-to-end test runs the full ``Coordinator.run()`` pipeline
against a clean fixture and asserts that the resulting
:class:`CuratorReport` reports zero stubbed dispatches — proving every
RISK_TAXONOMY action key produced by the default collect phase now has a
wired handler.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.dispatch_context import DispatchContext
from lexibrary.curator.iwh_actions import (
    consume_superseded_iwh,
    flag_unresolvable_agent_design,
    write_reactive_iwh,
)
from lexibrary.curator.models import CollectItem, TriageItem
from lexibrary.errors import ErrorSummary
from lexibrary.iwh.model import IWHFile
from lexibrary.iwh.serializer import serialize_iwh
from lexibrary.iwh.writer import write_iwh
from lexibrary.utils.paths import iwh_path as production_iwh_path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> tuple[Path, Path]:
    """Build a minimal project with a ``.lexibrary/`` layout."""
    project = tmp_path / "project"
    project.mkdir()
    lex_dir = project / ".lexibrary"
    lex_dir.mkdir()
    (lex_dir / "designs").mkdir()
    (lex_dir / "config.yaml").write_text("", encoding="utf-8")
    return project, lex_dir


def _make_ctx(project: Path, lex_dir: Path) -> DispatchContext:
    """Build a minimal DispatchContext with a real ErrorSummary."""
    return DispatchContext(
        project_root=project,
        config=LexibraryConfig(),
        summary=ErrorSummary(),
        lexibrary_dir=lex_dir,
        dry_run=False,
        uncommitted=set(),
        active_iwh=set(),
    )


def _make_item(
    *,
    action_key: str,
    target_path: Path | None,
    message: str = "planted IWH issue",
) -> TriageItem:
    """Fabricate an IWH triage item."""
    collect = CollectItem(
        source="iwh",
        path=target_path,
        severity="info",
        message=message,
        check="iwh_scan",
    )
    return TriageItem(
        source_item=collect,
        issue_type="orphan",
        action_key=action_key,
        priority=5.0,
    )


def _write_iwh_file(directory: Path, *, body: str = "legacy signal") -> Path:
    """Write a canonical ``.iwh`` file at *directory* via the serializer.

    This helper deliberately bypasses :func:`lexibrary.iwh.writer.write_iwh`
    so the ``consume_superseded_iwh`` test can assert the file is
    discovered and removed without any coupling to the writer under test.
    """
    directory.mkdir(parents=True, exist_ok=True)
    iwh = IWHFile(
        author="previous_agent",
        created=datetime.now(UTC),
        scope="incomplete",
        body=body,
    )
    path = directory / ".iwh"
    path.write_text(serialize_iwh(iwh), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# consume_superseded_iwh
# ---------------------------------------------------------------------------


class TestConsumeSupersededIwh:
    def test_consume_superseded_iwh_calls_reader(self, tmp_path: Path) -> None:
        """When an .iwh file exists the handler consumes (reads+deletes) it."""
        project, lex_dir = _setup_project(tmp_path)
        target_dir = lex_dir / "designs" / "src" / "foo"
        iwh_path = _write_iwh_file(target_dir, body="superseded")
        assert iwh_path.exists()

        item = _make_item(action_key="consume_superseded_iwh", target_path=target_dir)
        result = consume_superseded_iwh(item, _make_ctx(project, lex_dir))

        assert result.success is True
        assert result.outcome == "fixed"
        assert result.action_key == "consume_superseded_iwh"
        # consume_iwh deletes the file after successful read.
        assert not iwh_path.exists()
        # The handler must not record any LLM calls.
        assert result.llm_calls == 0

    def test_consume_superseded_iwh_missing_file_returns_failure(self, tmp_path: Path) -> None:
        """When no .iwh file is present the handler reports a failure."""
        project, lex_dir = _setup_project(tmp_path)
        target_dir = lex_dir / "designs" / "src" / "missing"
        target_dir.mkdir(parents=True)
        # Deliberately do NOT write a .iwh file.

        item = _make_item(action_key="consume_superseded_iwh", target_path=target_dir)
        result = consume_superseded_iwh(item, _make_ctx(project, lex_dir))

        assert result.success is False
        assert result.outcome == "fixer_failed"
        assert result.action_key == "consume_superseded_iwh"
        assert "No IWH signal found" in result.message

    def test_consume_superseded_iwh_no_path_returns_failure(self, tmp_path: Path) -> None:
        """When the triage item has no path the handler reports failure."""
        project, lex_dir = _setup_project(tmp_path)
        item = _make_item(action_key="consume_superseded_iwh", target_path=None)
        result = consume_superseded_iwh(item, _make_ctx(project, lex_dir))

        assert result.success is False
        assert result.outcome == "fixer_failed"
        assert "No directory path" in result.message


# ---------------------------------------------------------------------------
# write_reactive_iwh
# ---------------------------------------------------------------------------


class TestWriteReactiveIwh:
    def test_write_reactive_iwh_creates_signal(self, tmp_path: Path) -> None:
        """The handler writes a scope=warning IWH at the target directory."""
        project, lex_dir = _setup_project(tmp_path)
        target_dir = lex_dir / "designs" / "src" / "reactive"

        item = _make_item(
            action_key="write_reactive_iwh",
            target_path=target_dir,
            message="Reactive run flagged this directory",
        )
        result = write_reactive_iwh(item, _make_ctx(project, lex_dir))

        assert result.success is True
        assert result.outcome == "fixed"
        assert result.action_key == "write_reactive_iwh"
        iwh_path = target_dir / ".iwh"
        assert iwh_path.exists()
        content = iwh_path.read_text(encoding="utf-8")
        assert "scope: warning" in content
        assert "author: curator" in content
        assert "Reactive IWH signal written by curator" in content
        assert "Reactive run flagged this directory" in content

    def test_write_reactive_iwh_creates_missing_directory(self, tmp_path: Path) -> None:
        """``write_iwh`` creates parent directories on demand."""
        project, lex_dir = _setup_project(tmp_path)
        target_dir = lex_dir / "designs" / "src" / "new" / "nested"
        assert not target_dir.exists()

        item = _make_item(action_key="write_reactive_iwh", target_path=target_dir)
        result = write_reactive_iwh(item, _make_ctx(project, lex_dir))

        assert result.success is True
        assert (target_dir / ".iwh").exists()

    def test_write_reactive_iwh_no_path_returns_failure(self, tmp_path: Path) -> None:
        """When the triage item has no path the handler reports failure."""
        project, lex_dir = _setup_project(tmp_path)
        item = _make_item(action_key="write_reactive_iwh", target_path=None)
        result = write_reactive_iwh(item, _make_ctx(project, lex_dir))

        assert result.success is False
        assert result.outcome == "fixer_failed"
        assert "No directory path" in result.message


# ---------------------------------------------------------------------------
# flag_unresolvable_agent_design
# ---------------------------------------------------------------------------


class TestFlagUnresolvableAgentDesign:
    def test_flag_unresolvable_agent_design_writes_warning(self, tmp_path: Path) -> None:
        """The handler writes a scope=warning IWH next to the design file."""
        project, lex_dir = _setup_project(tmp_path)
        design_dir = lex_dir / "designs" / "src" / "lexibrary"
        design_dir.mkdir(parents=True)
        design_path = design_dir / "tricky.py.md"
        design_path.write_text(
            "---\nsource: src/lexibrary/tricky.py\n---\n\n# Tricky\n",
            encoding="utf-8",
        )

        item = _make_item(
            action_key="flag_unresolvable_agent_design",
            target_path=design_path,
            message="Reconciliation confidence below threshold",
        )
        result = flag_unresolvable_agent_design(item, _make_ctx(project, lex_dir))

        assert result.success is True
        assert result.outcome == "fixed"
        assert result.action_key == "flag_unresolvable_agent_design"
        iwh_path = design_dir / ".iwh"
        assert iwh_path.exists()
        content = iwh_path.read_text(encoding="utf-8")
        assert "scope: warning" in content
        assert "author: curator" in content
        # Body must reference the design file path so reviewers can find it.
        assert str(design_path) in content
        assert "human review required" in content

    def test_flag_unresolvable_agent_design_no_path_returns_failure(self, tmp_path: Path) -> None:
        """When the triage item has no path the handler reports failure."""
        project, lex_dir = _setup_project(tmp_path)
        item = _make_item(action_key="flag_unresolvable_agent_design", target_path=None)
        result = flag_unresolvable_agent_design(item, _make_ctx(project, lex_dir))

        assert result.success is False
        assert result.outcome == "fixer_failed"
        assert "No design path" in result.message


# ---------------------------------------------------------------------------
# No-residual-stubs end-to-end test (task 9.8)
# ---------------------------------------------------------------------------


def test_no_residual_stubs_in_default_run(tmp_path: Path) -> None:
    """Running the coordinator against a clean fixture yields zero stubs.

    This guards the group 9 exit criterion: once every IWH residual
    handler is wired, the default collect phase should never produce a
    triage item that falls through to the ``outcome="stubbed"`` branch in
    :meth:`Coordinator._route_to_handler`.  Any stubbed dispatches would
    indicate a missing handler somewhere in the pipeline.
    """
    project = tmp_path / "residual_check"
    project.mkdir()
    lex = project / ".lexibrary"
    lex.mkdir()
    for sub in ("designs", "concepts", "conventions", "playbooks", "stack"):
        (lex / sub).mkdir()
    (lex / "config.yaml").write_text("", encoding="utf-8")

    config = LexibraryConfig.model_validate({"curator": {"autonomy": "full"}})
    coord = Coordinator(project, config)
    report = asyncio.run(coord.run())

    assert report.stubbed == 0, (
        f"Default coordinator run produced {report.stubbed} stubbed "
        f"dispatch(es); expected zero. Dispatched details: "
        f"{report.dispatched_details}"
    )


# ---------------------------------------------------------------------------
# End-to-end pipeline test for consume_superseded_iwh (curator-fix-2 CUR-09)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consume_superseded_iwh_end_to_end(tmp_path: Path) -> None:
    """Full pipeline: plant IWH via production iwh_path, run coordinator, assert consumed.

    This test guards the ``find_all_iwh`` + ``_collect_iwh`` round-trip:
    planting an IWH signal at the production mirror location
    (``.lexibrary/designs/<src-path>/.iwh``) and running the real
    coordinator must result in the file being discovered, classified,
    dispatched to ``consume_superseded_iwh``, and deleted from disk.
    """
    # Minimal project layout.
    proj = tmp_path / "proj"
    src_pkg = proj / "src" / "pkg"
    src_pkg.mkdir(parents=True)
    (src_pkg / "mod.py").write_text("x = 1\n", encoding="utf-8")

    lex = proj / ".lexibrary"
    (lex / "designs").mkdir(parents=True)
    (lex / "concepts").mkdir()
    (lex / "conventions").mkdir()
    (lex / "playbooks").mkdir()
    (lex / "stack").mkdir()
    (lex / "config.yaml").write_text("", encoding="utf-8")

    # Plant a superseded IWH signal using the production path helper so
    # find_all_iwh → _collect_iwh → consume_iwh walk the same path.
    iwh_file = production_iwh_path(proj, src_pkg)
    iwh_mirror_dir = iwh_file.parent
    iwh_mirror_dir.mkdir(parents=True, exist_ok=True)
    write_iwh(
        iwh_mirror_dir,
        author="previous_agent",
        scope="incomplete",
        body="left over from a prior session",
    )
    assert iwh_file.exists(), "Planted IWH file should exist before run"

    # Run the coordinator in "full" autonomy with consistency_collect="off"
    # so only the IWH scan contributes items.  The empty local config.yaml
    # above prevents the global ~/.config/lexibrary/config.yaml from
    # leaking in.
    config = LexibraryConfig.model_validate(
        {
            "curator": {
                "autonomy": "full",
                "consistency_collect": "off",
            }
        }
    )
    coord = Coordinator(proj, config)
    report = await coord.run()

    # The .iwh file must have been consumed (deleted).
    assert not iwh_file.exists(), (
        f"Expected IWH file to be deleted by consume_superseded_iwh, "
        f"but it still exists at {iwh_file}"
    )

    # dispatched_details should contain exactly one consume_superseded_iwh
    # entry with outcome="fixed".
    consumed = [
        d for d in report.dispatched_details if d.get("action_key") == "consume_superseded_iwh"
    ]
    assert len(consumed) == 1, (
        f"Expected 1 consume_superseded_iwh dispatch, got {len(consumed)}. "
        f"All dispatched details: {report.dispatched_details}"
    )
    assert consumed[0].get("outcome") == "fixed", (
        f"Expected outcome='fixed' for consume_superseded_iwh, got "
        f"{consumed[0].get('outcome')!r}. Full entry: {consumed[0]}"
    )
