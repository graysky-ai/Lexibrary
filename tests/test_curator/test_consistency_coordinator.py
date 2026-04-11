"""Coordinator-level tests for the consistency integration (group 8).

Exercises ``_collect_consistency``, ``_classify_consistency``, and the
``_dispatch_consistency_fix`` routing — all three glue points between
``ConsistencyChecker`` and the concrete fix helpers in
``consistency_fixes.py``.

Unlike ``test_consistency_fixes.py`` (unit tests), these tests build a
real :class:`Coordinator` against a minimal fixture and verify the
coordinator wires signals through the collect/triage/dispatch pipeline
correctly.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import yaml

from lexibrary.artifacts.design_file import (
    DesignFile,
    DesignFileFrontmatter,
    StalenessMetadata,
)
from lexibrary.artifacts.design_file_serializer import serialize_design_file
from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.consistency_fixes import CONSISTENCY_ACTION_KEYS
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import (
    CollectItem,
    CollectResult,
    SubAgentResult,
    TriageItem,
)
from lexibrary.curator.risk_taxonomy import RISK_TAXONOMY
from lexibrary.iwh.model import IWHFile
from lexibrary.iwh.serializer import serialize_iwh
from lexibrary.utils.paths import iwh_path as production_iwh_path

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _setup_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    lex = project / ".lexibrary"
    lex.mkdir()
    (lex / "designs").mkdir()
    (lex / "concepts").mkdir()
    (lex / "conventions").mkdir()
    (lex / "playbooks").mkdir()
    (lex / "stack").mkdir()
    (lex / "config.yaml").write_text("", encoding="utf-8")
    return project


def _make_source(project: Path, rel: str, content: str = "def foo(): pass\n") -> Path:
    src = project / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(content, encoding="utf-8")
    return src


def _make_design_with_wikilink(
    project: Path,
    source_rel: str,
    *,
    wikilink_target: str,
) -> Path:
    """Create a design file with a single planted wikilink."""
    _make_source(project, source_rel)
    design_path = project / ".lexibrary" / "designs" / f"{source_rel}.md"
    design_path.parent.mkdir(parents=True, exist_ok=True)

    df = DesignFile(
        source_path=source_rel,
        frontmatter=DesignFileFrontmatter(
            description=f"Design for {source_rel}",
            id=source_rel.replace("/", "-").replace(".", "-"),
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
            source_hash="a" * 64,
            interface_hash=None,
            generated=datetime.now(UTC),
            generator="test",
        ),
    )
    design_path.write_text(serialize_design_file(df), encoding="utf-8")
    return design_path


def _make_concept(lex_dir: Path, concept_id: str, title: str) -> Path:
    slug_id = f"{concept_id}-{title.lower().replace(' ', '-')}"
    path = lex_dir / "concepts" / f"{slug_id}.md"
    data = {"title": title, "id": concept_id, "status": "active", "aliases": [], "tags": []}
    path.write_text(
        f"---\n{yaml.dump(data, default_flow_style=False)}---\n\n# {title}\n\nBody\n",
        encoding="utf-8",
    )
    return path


def _plant_old_blocked_iwh(
    project: Path,
    source_rel: str,
    *,
    age_hours: int = 96,
    body: str = "Blocked on upstream",
) -> Path:
    """Plant a ``scope=blocked`` IWH older than the 72h promotion threshold.

    The file is written at the production mirror location
    (``.lexibrary/designs/<source_rel>/.iwh``) with a ``created``
    timestamp *age_hours* in the past so ``detect_promotable_iwh``
    treats it as promotable.
    """
    source_dir = project / source_rel
    source_dir.mkdir(parents=True, exist_ok=True)
    iwh_file = production_iwh_path(project, source_dir)
    iwh_file.parent.mkdir(parents=True, exist_ok=True)
    iwh = IWHFile(
        author="previous_agent",
        created=datetime.now(UTC) - timedelta(hours=age_hours),
        scope="blocked",
        body=body,
    )
    iwh_file.write_text(serialize_iwh(iwh), encoding="utf-8")
    return iwh_file


# ---------------------------------------------------------------------------
# _collect_consistency
# ---------------------------------------------------------------------------


class TestCollectConsistency:
    def test_collect_consistency_populates_items(self, tmp_path: Path) -> None:
        """Planting a broken wikilink produces a ``source='consistency'`` item."""
        project = _setup_project(tmp_path)
        _make_design_with_wikilink(project, "src/foo.py", wikilink_target="NonexistentConcept")
        coord = Coordinator(project, LexibraryConfig())
        result = CollectResult()
        coord._collect_consistency(  # noqa: SLF001
            result, scope=None, uncommitted=set(), active_iwh=set()
        )
        consistency_items = [i for i in result.items if i.source == "consistency"]
        assert len(consistency_items) >= 1
        # At least one should be a strip instruction for NonexistentConcept
        hints = [i.action_hint for i in consistency_items]
        assert "strip_unresolved_wikilink" in hints

    def test_collect_consistency_respects_scope(self, tmp_path: Path) -> None:
        """``consistency_collect='scope'`` runs scope-bounded checks only."""
        project = _setup_project(tmp_path)
        _make_design_with_wikilink(project, "src/foo.py", wikilink_target="NonexistentConcept")
        config = LexibraryConfig.model_validate({"curator": {"consistency_collect": "scope"}})
        coord = Coordinator(project, config)
        result = CollectResult()
        coord._collect_consistency(  # noqa: SLF001
            result, scope=None, uncommitted=set(), active_iwh=set()
        )
        # Scope mode should still produce wikilink hygiene items.
        assert any(i.source == "consistency" for i in result.items)

    def test_collect_consistency_off(self, tmp_path: Path) -> None:
        """``consistency_collect='off'`` short-circuits without producing items."""
        project = _setup_project(tmp_path)
        _make_design_with_wikilink(project, "src/foo.py", wikilink_target="Nonexistent")
        config = LexibraryConfig.model_validate({"curator": {"consistency_collect": "off"}})
        coord = Coordinator(project, config)
        result = CollectResult()
        coord._collect_consistency(  # noqa: SLF001
            result, scope=None, uncommitted=set(), active_iwh=set()
        )
        assert [i for i in result.items if i.source == "consistency"] == []

    def test_collect_consistency_filters_uncommitted(self, tmp_path: Path) -> None:
        """Paths listed in ``uncommitted`` are skipped during collect."""
        project = _setup_project(tmp_path)
        design_path = _make_design_with_wikilink(
            project, "src/foo.py", wikilink_target="Nonexistent"
        )
        coord = Coordinator(project, LexibraryConfig())
        result = CollectResult()
        coord._collect_consistency(  # noqa: SLF001
            result,
            scope=None,
            uncommitted={design_path.resolve()},
            active_iwh=set(),
        )
        # When the design path is treated as uncommitted, its wikilink
        # hygiene findings should be filtered out.
        hints = [i.action_hint for i in result.items if i.source == "consistency"]
        assert "strip_unresolved_wikilink" not in hints

    def test_collect_consistency_scope_mode_includes_promotable_iwh(
        self, tmp_path: Path
    ) -> None:
        """``consistency_collect='scope'`` surfaces stale blocked IWH for promotion.

        Pins the CUR-05 contract: promotable blocked IWH detection is
        now a scope-level check, not a full-only check, so a qualifying
        blocked IWH must produce a ``promote_blocked_iwh`` consistency
        item under the default mode.
        """
        project = _setup_project(tmp_path)
        _plant_old_blocked_iwh(project, "src/auth", age_hours=96)

        config = LexibraryConfig.model_validate(
            {"curator": {"consistency_collect": "scope"}}
        )
        coord = Coordinator(project, config)
        result = CollectResult()
        coord._collect_consistency(  # noqa: SLF001
            result, scope=None, uncommitted=set(), active_iwh=set()
        )

        hints = [
            i.action_hint for i in result.items if i.source == "consistency"
        ]
        assert "promote_blocked_iwh" in hints, (
            f"Expected promote_blocked_iwh hint in scope mode; got {hints}"
        )

    def test_collect_consistency_off_skips_promotable_iwh(
        self, tmp_path: Path
    ) -> None:
        """``consistency_collect='off'`` still suppresses promotable IWH detection."""
        project = _setup_project(tmp_path)
        _plant_old_blocked_iwh(project, "src/auth", age_hours=96)

        config = LexibraryConfig.model_validate(
            {"curator": {"consistency_collect": "off"}}
        )
        coord = Coordinator(project, config)
        result = CollectResult()
        coord._collect_consistency(  # noqa: SLF001
            result, scope=None, uncommitted=set(), active_iwh=set()
        )

        hints = [
            i.action_hint for i in result.items if i.source == "consistency"
        ]
        assert "promote_blocked_iwh" not in hints


# ---------------------------------------------------------------------------
# _classify_consistency
# ---------------------------------------------------------------------------


class TestClassifyConsistency:
    def test_classify_consistency_maps_action_hint(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        coord = Coordinator(project, LexibraryConfig())

        item = CollectItem(
            source="consistency",
            path=tmp_path / "fake.md",
            severity="info",
            message="strip it",
            check="consistency",
            action_hint="strip_unresolved_wikilink",
            fix_instruction_detail="Wikilink [[Dead]] cannot be resolved",
        )
        triage = coord._classify_consistency(item)  # noqa: SLF001
        assert triage.issue_type == "consistency_fix"
        assert triage.action_key == "strip_unresolved_wikilink"
        assert triage.risk_level == "low"

    def test_classify_consistency_medium_risk(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        coord = Coordinator(project, LexibraryConfig())

        item = CollectItem(
            source="consistency",
            path=tmp_path / "CN-999.md",
            severity="warning",
            message="suggest",
            check="consistency",
            action_hint="suggest_new_concept",
            fix_instruction_detail="Domain term 'rate limiter' appears in 3 files",
        )
        triage = coord._classify_consistency(item)  # noqa: SLF001
        assert triage.action_key == "suggest_new_concept"
        assert triage.risk_level == "medium"

    def test_classify_iwh_scan_path_routes_promote_to_consistency_fix(
        self, tmp_path: Path
    ) -> None:
        """Scan-path IWH items for blocked signals get ``issue_type='consistency_fix'``.

        Pins the CUR-05 routing contract: ``_collect_iwh`` produces a
        blocked-scope ``CollectItem``; ``_classify_iwh`` must mark it as
        ``consistency_fix`` so it reaches ``_dispatch_consistency_fix``
        (where ``apply_promote_blocked_iwh`` lives) instead of falling
        back to the orphan stub handler.
        """
        project = _setup_project(tmp_path)
        coord = Coordinator(project, LexibraryConfig())

        blocked_item = CollectItem(
            source="iwh",
            path=project / ".lexibrary" / "designs" / "src" / "auth",
            severity="info",
            message="IWH signal: scope=blocked, body=upstream not ready",
            check="iwh_scan",
        )
        triage = coord._classify_iwh(blocked_item)  # noqa: SLF001
        assert triage.action_key == "promote_blocked_iwh"
        assert triage.issue_type == "consistency_fix"

    def test_classify_iwh_scan_path_consume_remains_orphan(
        self, tmp_path: Path
    ) -> None:
        """Non-blocked IWH scan items remain ``issue_type='orphan'``.

        ``consume_superseded_iwh`` deletes stale signals and has no
        escalation path; it must stay on the orphan route.
        """
        project = _setup_project(tmp_path)
        coord = Coordinator(project, LexibraryConfig())

        superseded_item = CollectItem(
            source="iwh",
            path=project / ".lexibrary" / "designs" / "src" / "old",
            severity="info",
            message="IWH signal: scope=incomplete, body=stale leftover",
            check="iwh_scan",
        )
        triage = coord._classify_iwh(superseded_item)  # noqa: SLF001
        assert triage.action_key == "consume_superseded_iwh"
        assert triage.issue_type == "orphan"


# ---------------------------------------------------------------------------
# _dispatch_consistency_fix
# ---------------------------------------------------------------------------


class TestDispatchConsistencyFix:
    def test_dispatch_consistency_fix_routes_by_action_key(self, tmp_path: Path) -> None:
        """The dispatcher calls the matching fix helper by action_key."""
        project = _setup_project(tmp_path)
        design_path = _make_design_with_wikilink(project, "src/foo.py", wikilink_target="Dead")
        coord = Coordinator(project, LexibraryConfig())

        collect = CollectItem(
            source="consistency",
            path=design_path,
            severity="info",
            message="strip",
            check="consistency",
            action_hint="strip_unresolved_wikilink",
            fix_instruction_detail="Wikilink [[Dead]] cannot be resolved",
        )
        triage = TriageItem(
            source_item=collect,
            issue_type="consistency_fix",
            action_key="strip_unresolved_wikilink",
            priority=15.0,
        )
        result = coord._dispatch_consistency_fix(triage)  # noqa: SLF001
        assert isinstance(result, SubAgentResult)
        assert result.success is True
        assert result.outcome == "fixed"

    def test_dispatch_consistency_fix_unknown_key_stubbed(self, tmp_path: Path) -> None:
        project = _setup_project(tmp_path)
        coord = Coordinator(project, LexibraryConfig())

        collect = CollectItem(
            source="consistency",
            path=tmp_path / "x.md",
            severity="info",
            message="x",
            check="consistency",
            action_hint="unknown_thing",
            fix_instruction_detail="",
        )
        triage = TriageItem(
            source_item=collect,
            issue_type="consistency_fix",
            action_key="unknown_thing",
            priority=15.0,
        )
        result = coord._dispatch_consistency_fix(triage)  # noqa: SLF001
        assert result.outcome == "stubbed"


# ---------------------------------------------------------------------------
# Autonomy gating
# ---------------------------------------------------------------------------


class TestConsistencyAutonomyGating:
    def test_consistency_dispatch_respects_autonomy(self, tmp_path: Path) -> None:
        """Medium-risk consistency actions are deferred under ``auto_low``.

        The guarantee is enforced by ``should_dispatch`` (not the
        consistency dispatcher itself).  Asserting the policy here locks
        in the contract tests depend on: Medium-risk consistency action
        keys are gated under ``auto_low`` and allowed under ``full``.
        """
        from lexibrary.curator.risk_taxonomy import should_dispatch  # noqa: PLC0415

        # Under auto_low, Medium consistency actions are deferred.
        assert should_dispatch("suggest_new_concept", "auto_low", {}) is False
        assert should_dispatch("promote_blocked_iwh", "auto_low", {}) is False
        # Under full, both are allowed.
        assert should_dispatch("suggest_new_concept", "full", {}) is True
        assert should_dispatch("promote_blocked_iwh", "full", {}) is True

    def test_consistency_fix_not_called_in_dry_run(self, tmp_path: Path) -> None:
        """Dry-run mode records ``outcome='dry_run'`` without invoking helpers."""
        project = _setup_project(tmp_path)
        _make_design_with_wikilink(project, "src/foo.py", wikilink_target="Dead")

        with patch("lexibrary.curator.consistency_fixes.apply_strip_wikilink") as mock_helper:
            mock_helper.side_effect = AssertionError("should not be called in dry_run")
            coord = Coordinator(project, LexibraryConfig())
            report = asyncio.run(coord.run(dry_run=True))
            assert report is not None
            # Helper must not have been invoked in dry-run.
            mock_helper.assert_not_called()


# ---------------------------------------------------------------------------
# Taxonomy registration
# ---------------------------------------------------------------------------


class TestConsistencyActionKeysRegistered:
    def test_consistency_action_keys_registered(self) -> None:
        """Every CONSISTENCY_ACTION_KEYS value has a RISK_TAXONOMY entry."""
        for action_key in CONSISTENCY_ACTION_KEYS.values():
            assert action_key in RISK_TAXONOMY, f"{action_key} missing from RISK_TAXONOMY"
