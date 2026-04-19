"""Tests for curator-4 Group 15 ``escalate_*`` validator fixers.

Covers the four escalation fixers (``escalate_orphan_concepts``,
``escalate_stale_concept``, ``escalate_convention_stale``,
``escalate_playbook_staleness``) plus the ``_is_autonomous_context``
guard and the bridge propagation through
``fix_validation_issue``.

Each ``escalate_*`` fixer:

* Does NOT mutate the target artifact.
* Writes a ``.iwh`` signal in the artifact's parent directory when the
  caller is autonomous.
* Returns a ``FixResult`` with ``fixed=False``, ``llm_calls=0``, and
  ``outcome_hint="escalation_required"``.
* Populates ``iwh_path`` on the ``FixResult`` when a signal was written.

The bridge in ``curator.validation_fixers.fix_validation_issue`` maps
``outcome_hint="escalation_required"`` to
``SubAgentResult.outcome = "escalation_required"`` with ``success=False``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from lexibrary.config.schema import (
    LexibraryConfig,
    ScopeRoot,
    TokenBudgetConfig,
)
from lexibrary.curator.models import CollectItem, SubAgentResult, TriageItem
from lexibrary.curator.validation_fixers import fix_validation_issue
from lexibrary.validator.fixes import (
    ESCALATION_CHECKS,
    FIXERS,
    FixResult,
    _is_autonomous_context,
    escalate_convention_stale,
    escalate_orphan_concepts,
    escalate_playbook_staleness,
    escalate_stale_concept,
)
from lexibrary.validator.report import ValidationIssue

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> LexibraryConfig:
    return LexibraryConfig(
        scope_roots=[ScopeRoot(path=".")],
        token_budgets=TokenBudgetConfig(design_file_tokens=400),
    )


_concept_id_counter = 0


def _next_concept_id() -> str:
    global _concept_id_counter
    _concept_id_counter += 1
    return f"CN-{_concept_id_counter:03d}"


def _write_concept(
    concepts_dir: Path,
    *,
    slug: str = "lonely-concept",
    title: str = "Lonely Concept",
    aliases: tuple[str, ...] = (),
    file_refs: tuple[str, ...] = (),
    body_extra: str = "",
) -> Path:
    """Write a minimally-valid concept file."""
    concepts_dir.mkdir(parents=True, exist_ok=True)
    path = concepts_dir / f"{slug}.md"

    ref_lines = [f"- `{ref}` is a source file." for ref in file_refs]
    body_parts = [
        f"# {title}",
        "",
        "Linked files:",
        "",
        *ref_lines,
    ]
    if body_extra:
        body_parts.extend(["", body_extra])

    alias_str = ", ".join(aliases)
    lines = [
        "---",
        f"title: {title}",
        f"id: {_next_concept_id()}",
        f"aliases: [{alias_str}]",
        "tags: []",
        "status: active",
        "---",
        "",
        *body_parts,
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


_convention_id_counter = 0


def _next_convention_id() -> str:
    global _convention_id_counter
    _convention_id_counter += 1
    return f"CV-{_convention_id_counter:03d}"


def _write_convention(
    project_root: Path,
    *,
    slug: str = "stale-convention",
    title: str = "Stale Convention",
    scope: str = "src/gone/",
    body: str = "Rule body.\n",
) -> Path:
    conventions_dir = project_root / ".lexibrary" / "conventions"
    conventions_dir.mkdir(parents=True, exist_ok=True)
    path = conventions_dir / f"{slug}.md"

    lines = [
        "---",
        f"title: '{title}'",
        f"id: {_next_convention_id()}",
        f"scope: {scope}",
        "tags: []",
        "status: active",
        "source: user",
        "priority: 0",
        "---",
        "",
        body,
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


_playbook_id_counter = 0


def _next_playbook_id() -> str:
    global _playbook_id_counter
    _playbook_id_counter += 1
    return f"PB-{_playbook_id_counter:03d}"


def _write_playbook(
    playbooks_dir: Path,
    *,
    slug: str = "stale-playbook",
    title: str = "Stale Playbook",
    last_verified: date | None = None,
    body: str = "## Overview\n\nA playbook.\n",
) -> Path:
    playbooks_dir.mkdir(parents=True, exist_ok=True)
    path = playbooks_dir / f"{slug}.md"

    lines = [
        "---",
        f"title: {title}",
        f"id: {_next_playbook_id()}",
        "trigger_files: []",
        "tags: []",
        "status: active",
        "source: user",
    ]
    if last_verified is not None:
        lines.append(f"last_verified: {last_verified.isoformat()}")
    lines.extend(["---", "", body])

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _make_triage_item(
    *,
    check: str,
    action_key: str,
    path: Path | None,
    message: str = "",
) -> TriageItem:
    collect = CollectItem(
        source="validation",
        path=path,
        severity="warning",
        message=message,
        check=check,
    )
    return TriageItem(
        source_item=collect,
        issue_type="orphan",
        action_key=action_key,
        priority=10.0,
    )


# ---------------------------------------------------------------------------
# ESCALATION_CHECKS constant shape
# ---------------------------------------------------------------------------


class TestEscalationChecksFrozenset:
    """``ESCALATION_CHECKS`` is a frozenset with exactly four entries."""

    def test_contains_four_expected_checks(self) -> None:
        """All four checks in curator-4 Group 15 are present."""
        expected = frozenset(
            {
                "orphan_concepts",
                "stale_concept",
                "convention_stale",
                "playbook_staleness",
            }
        )
        assert expected == ESCALATION_CHECKS

    def test_is_frozenset(self) -> None:
        """The constant is a ``frozenset`` (immutable)."""
        assert isinstance(ESCALATION_CHECKS, frozenset)


# ---------------------------------------------------------------------------
# FixResult — new fields
# ---------------------------------------------------------------------------


class TestFixResultNewFields:
    """``outcome_hint`` and ``iwh_path`` default to ``None``."""

    def test_defaults(self) -> None:
        """Existing callers unaffected — both new fields default to None."""
        result = FixResult(
            check="x",
            path=Path("/tmp/x"),
            fixed=False,
            message="m",
        )

        assert result.outcome_hint is None
        assert result.iwh_path is None

    def test_accepts_escalation_hint(self) -> None:
        """``outcome_hint`` accepts the ``"escalation_required"`` Literal."""
        result = FixResult(
            check="orphan_concepts",
            path=Path("/tmp/x"),
            fixed=False,
            message="queued",
            outcome_hint="escalation_required",
            iwh_path=Path("/tmp/x.iwh"),
        )

        assert result.outcome_hint == "escalation_required"
        assert result.iwh_path == Path("/tmp/x.iwh")


# ---------------------------------------------------------------------------
# _is_autonomous_context
# ---------------------------------------------------------------------------


class TestIsAutonomousContext:
    """The TTY belt-and-braces guard flips with ``sys.stdout.isatty()``."""

    def test_returns_true_when_stdout_not_tty(self) -> None:
        """Non-TTY stdout → autonomous (IWH writes allowed)."""
        config = _make_config()
        with patch("sys.stdout.isatty", return_value=False):
            assert _is_autonomous_context(config) is True

    def test_returns_false_when_stdout_is_tty(self) -> None:
        """TTY stdout → non-autonomous (interactive CLI ran us by mistake)."""
        config = _make_config()
        with patch("sys.stdout.isatty", return_value=True):
            assert _is_autonomous_context(config) is False


# ---------------------------------------------------------------------------
# escalate_orphan_concepts
# ---------------------------------------------------------------------------


class TestEscalateOrphanConcepts:
    """Pure-escalation behaviour — no artifact mutation, IWH written autonomously."""

    def test_writes_iwh_when_autonomous(self, tmp_path: Path) -> None:
        """Autonomous run → IWH signal is written at the concept's parent dir."""
        project_root = tmp_path
        concepts_dir = project_root / ".lexibrary" / "concepts"
        concept_path = _write_concept(concepts_dir, slug="foo-concept", title="Foo Concept")
        before_bytes = concept_path.read_bytes()

        issue = ValidationIssue(
            severity="warning",
            check="orphan_concepts",
            message="Concept has no inbound wikilink references.",
            artifact="concepts/Foo Concept",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            result = escalate_orphan_concepts(issue, project_root, config)

        # Result shape
        assert result.fixed is False
        assert result.llm_calls == 0
        assert result.outcome_hint == "escalation_required"
        assert result.iwh_path is not None
        assert result.iwh_path.name == ".iwh"
        assert result.iwh_path.parent == concept_path.parent
        assert result.iwh_path.exists()
        assert "escalation queued: orphan_concepts" in result.message

        # Concept artifact is untouched
        assert concept_path.read_bytes() == before_bytes

        # IWH body mentions the trigger
        iwh_body = result.iwh_path.read_text(encoding="utf-8")
        assert "orphan_concepts" in iwh_body
        assert "zero inbound" in iwh_body

    def test_no_iwh_when_interactive(self, tmp_path: Path) -> None:
        """TTY-detected interactive run → no IWH written (helper still returns escalation)."""
        project_root = tmp_path
        concepts_dir = project_root / ".lexibrary" / "concepts"
        concept_path = _write_concept(concepts_dir, slug="bar-concept", title="Bar Concept")

        issue = ValidationIssue(
            severity="warning",
            check="orphan_concepts",
            message="no inbound",
            artifact="concepts/Bar Concept",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=True):
            result = escalate_orphan_concepts(issue, project_root, config)

        assert result.outcome_hint == "escalation_required"
        assert result.iwh_path is None
        # No .iwh should have been created next to the concept
        assert not (concept_path.parent / ".iwh").exists()

    def test_missing_concept_still_returns_escalation(self, tmp_path: Path) -> None:
        """Concept not resolvable on disk → still returns escalation outcome, no IWH."""
        project_root = tmp_path

        issue = ValidationIssue(
            severity="warning",
            check="orphan_concepts",
            message="no inbound",
            artifact="concepts/Ghost",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            result = escalate_orphan_concepts(issue, project_root, config)

        assert result.fixed is False
        assert result.outcome_hint == "escalation_required"
        assert result.iwh_path is None


# ---------------------------------------------------------------------------
# escalate_stale_concept
# ---------------------------------------------------------------------------


class TestEscalateStaleConcept:
    """Re-scans linked_files at fix time for the IWH body; no artifact mutation."""

    def test_writes_iwh_with_missing_count(self, tmp_path: Path) -> None:
        """Autonomous run → IWH body mentions the re-scanned missing count."""
        project_root = tmp_path
        concepts_dir = project_root / ".lexibrary" / "concepts"
        # One real file, one missing — expect ``1`` missing on re-scan.
        (project_root / "src").mkdir()
        (project_root / "src" / "present.py").write_text("# a\n", encoding="utf-8")

        concept_path = _write_concept(
            concepts_dir,
            slug="stale-one",
            title="Stale One",
            file_refs=("src/present.py", "src/vanished.py"),
        )
        before_bytes = concept_path.read_bytes()

        issue = ValidationIssue(
            severity="info",
            check="stale_concept",
            message="Active concept references missing file(s): src/vanished.py",
            artifact="concepts/Stale One",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            result = escalate_stale_concept(issue, project_root, config)

        assert result.fixed is False
        assert result.llm_calls == 0
        assert result.outcome_hint == "escalation_required"
        assert result.iwh_path is not None and result.iwh_path.exists()
        assert "1 missing linked_files" in result.message

        # Artifact untouched
        assert concept_path.read_bytes() == before_bytes

        # IWH body reflects the count
        iwh_body = result.iwh_path.read_text(encoding="utf-8")
        assert "stale_concept" in iwh_body
        assert "1 linked_files" in iwh_body


# ---------------------------------------------------------------------------
# escalate_convention_stale
# ---------------------------------------------------------------------------


class TestEscalateConventionStale:
    """Enumerates missing scope paths in IWH body; no artifact mutation."""

    def test_writes_iwh_listing_missing_scope(self, tmp_path: Path) -> None:
        """Autonomous run → IWH body lists the missing scope paths."""
        project_root = tmp_path
        # ``src/gone/`` intentionally absent.
        convention_path = _write_convention(
            project_root,
            slug="gone-scope",
            title="Gone Scope",
            scope="src/gone/",
        )
        before_bytes = convention_path.read_bytes()

        issue = ValidationIssue(
            severity="info",
            check="convention_stale",
            message="scope directories empty",
            artifact="conventions/gone-scope.md",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            result = escalate_convention_stale(issue, project_root, config)

        assert result.fixed is False
        assert result.llm_calls == 0
        assert result.outcome_hint == "escalation_required"
        assert result.iwh_path is not None and result.iwh_path.exists()
        assert "missing scope" in result.message
        # ``split_scope`` strips trailing slashes: "src/gone/" -> "src/gone"
        assert "src/gone" in result.message

        # Artifact untouched
        assert convention_path.read_bytes() == before_bytes

        # IWH body lists the stale scope path
        iwh_body = result.iwh_path.read_text(encoding="utf-8")
        assert "convention_stale" in iwh_body
        assert "src/gone" in iwh_body

    def test_no_iwh_when_convention_missing(self, tmp_path: Path) -> None:
        """No on-disk convention → still returns escalation, no IWH."""
        project_root = tmp_path

        issue = ValidationIssue(
            severity="info",
            check="convention_stale",
            message="",
            artifact="conventions/ghost.md",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            result = escalate_convention_stale(issue, project_root, config)

        assert result.fixed is False
        assert result.outcome_hint == "escalation_required"
        assert result.iwh_path is None


# ---------------------------------------------------------------------------
# escalate_playbook_staleness
# ---------------------------------------------------------------------------


class TestEscalatePlaybookStaleness:
    """IWH body notes days-since-last_verified; no artifact mutation."""

    def test_writes_iwh_with_staleness_delta(self, tmp_path: Path) -> None:
        """Autonomous run → IWH body reports days-since-last_verified."""
        project_root = tmp_path
        playbooks_dir = project_root / ".lexibrary" / "playbooks"
        prior = date.today() - timedelta(days=365)
        playbook_path = _write_playbook(
            playbooks_dir,
            slug="old-playbook",
            title="Old Playbook",
            last_verified=prior,
        )
        before_bytes = playbook_path.read_bytes()

        issue = ValidationIssue(
            severity="info",
            check="playbook_staleness",
            message="stale",
            artifact=".lexibrary/playbooks/old-playbook.md",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            result = escalate_playbook_staleness(issue, project_root, config)

        assert result.fixed is False
        assert result.llm_calls == 0
        assert result.outcome_hint == "escalation_required"
        assert result.iwh_path is not None and result.iwh_path.exists()
        assert "days since last_verified" in result.message

        # Artifact untouched
        assert playbook_path.read_bytes() == before_bytes

        # IWH body mentions the trigger
        iwh_body = result.iwh_path.read_text(encoding="utf-8")
        assert "playbook_staleness" in iwh_body

    def test_never_verified_playbook(self, tmp_path: Path) -> None:
        """Playbook with ``last_verified=None`` → message says "never verified"."""
        project_root = tmp_path
        playbooks_dir = project_root / ".lexibrary" / "playbooks"
        playbook_path = _write_playbook(
            playbooks_dir,
            slug="never-verified",
            title="Never Verified",
            last_verified=None,
        )
        _ = playbook_path  # satisfy linter

        issue = ValidationIssue(
            severity="info",
            check="playbook_staleness",
            message="",
            artifact=".lexibrary/playbooks/never-verified.md",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            result = escalate_playbook_staleness(issue, project_root, config)

        assert result.outcome_hint == "escalation_required"
        assert "never verified" in result.message


# ---------------------------------------------------------------------------
# Bridge: fix_validation_issue maps outcome_hint → SubAgentResult.outcome
# ---------------------------------------------------------------------------


class TestBridgeEscalationMapping:
    """``fix_validation_issue`` honours the escalation outcome hint."""

    def test_fixed_true_returns_fixed_outcome(self) -> None:
        """Sanity: without the hint the bridge still returns ``"fixed"``."""
        item = _make_triage_item(
            check="custom_check",
            action_key="custom_action",
            path=Path("/tmp/x"),
        )

        def _fake_fixer(
            issue: ValidationIssue, project_root: Path, config: LexibraryConfig
        ) -> FixResult:
            return FixResult(
                check=issue.check,
                path=Path("/tmp/x"),
                fixed=True,
                message="did it",
                llm_calls=0,
            )

        config = _make_config()
        # Inject a fake fixer by patching the FIXERS dict entry for the bridge call.
        with patch.dict(FIXERS, {"custom_check": _fake_fixer}):
            result = fix_validation_issue(item, Path("/tmp"), config)

        assert isinstance(result, SubAgentResult)
        assert result.outcome == "fixed"
        assert result.success is True

    def test_escalation_hint_maps_to_escalation_required(self) -> None:
        """``outcome_hint="escalation_required"`` → outcome flipped, success=False."""
        item = _make_triage_item(
            check="orphan_concepts",
            action_key="escalate_orphan_concepts",
            path=Path("/tmp/concept.md"),
        )

        iwh_path = Path("/tmp/concept.iwh")

        def _fake_escalator(
            issue: ValidationIssue, project_root: Path, config: LexibraryConfig
        ) -> FixResult:
            return FixResult(
                check=issue.check,
                path=Path("/tmp/concept.md"),
                fixed=False,
                message="escalation queued: orphan_concepts (concept.md)",
                llm_calls=0,
                outcome_hint="escalation_required",
                iwh_path=iwh_path,
            )

        config = _make_config()
        with patch.dict(FIXERS, {"orphan_concepts": _fake_escalator}):
            result = fix_validation_issue(item, Path("/tmp"), config)

        assert result.outcome == "escalation_required"
        assert result.success is False
        assert result.llm_calls == 0
        # Narrow per-check action_key preserved.
        assert result.action_key == "escalate_orphan_concepts"
        # Path from the fixer is preserved.
        assert result.path == Path("/tmp/concept.md")

    def test_fixed_false_without_hint_is_fixer_failed(self) -> None:
        """Guard: a plain ``fixed=False`` without the hint keeps the legacy outcome."""
        item = _make_triage_item(
            check="plain_check",
            action_key="plain_action",
            path=Path("/tmp/x"),
        )

        def _fake_fixer(
            issue: ValidationIssue, project_root: Path, config: LexibraryConfig
        ) -> FixResult:
            return FixResult(
                check=issue.check,
                path=Path("/tmp/x"),
                fixed=False,
                message="no escalation",
                llm_calls=0,
            )

        config = _make_config()
        with patch.dict(FIXERS, {"plain_check": _fake_fixer}):
            result = fix_validation_issue(item, Path("/tmp"), config)

        assert result.outcome == "fixer_failed"
        assert result.success is False


# ---------------------------------------------------------------------------
# IWH_CONTENT field spot-check (scope value)
# ---------------------------------------------------------------------------


def _parse_iwh_scope(iwh_path: Path) -> str:
    """Extract the ``scope:`` line from an IWH file for coarse assertions.

    The real parser lives at ``lexibrary.iwh.parser.parse_iwh`` but we only
    need the scope string for these tests.
    """
    lines = iwh_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.startswith("scope:"):
            return line.split(":", 1)[1].strip()
    return ""


class TestIwhShape:
    """All four escalate_* fixers emit ``scope=warning`` signals (current schema).

    ``IWHScope`` is ``Literal["warning", "incomplete", "blocked"]`` — there
    is no ``"escalation"`` member. We use ``warning`` to match the existing
    curator precedent (``write_reactive_iwh``, ``consistency_fixes``).
    """

    def test_orphan_concepts_iwh_uses_warning_scope(self, tmp_path: Path) -> None:
        concepts_dir = tmp_path / ".lexibrary" / "concepts"
        concept_path = _write_concept(concepts_dir, slug="scope-test", title="Scope Test")
        _ = concept_path

        issue = ValidationIssue(
            severity="warning",
            check="orphan_concepts",
            message="no inbound",
            artifact="concepts/Scope Test",
        )
        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            result = escalate_orphan_concepts(issue, tmp_path, config)

        assert result.iwh_path is not None
        assert _parse_iwh_scope(result.iwh_path) == "warning"


# ---------------------------------------------------------------------------
# Artifact immutability — cross-fixer
# ---------------------------------------------------------------------------


class TestArtifactImmutability:
    """None of the four ``escalate_*`` fixers mutate the target artifact."""

    def test_all_four_do_not_mutate_artifacts(self, tmp_path: Path) -> None:
        project_root = tmp_path

        # Concept
        concepts_dir = project_root / ".lexibrary" / "concepts"
        concept = _write_concept(concepts_dir, slug="imm-concept", title="Imm Concept")
        concept_before = concept.read_bytes()

        # Convention
        convention = _write_convention(project_root, slug="imm-convention", scope="src/void/")
        convention_before = convention.read_bytes()

        # Playbook
        playbooks_dir = project_root / ".lexibrary" / "playbooks"
        playbook = _write_playbook(
            playbooks_dir,
            slug="imm-playbook",
            last_verified=date.today() - timedelta(days=500),
        )
        playbook_before = playbook.read_bytes()

        config = _make_config()

        with patch("sys.stdout.isatty", return_value=False):
            escalate_orphan_concepts(
                ValidationIssue(
                    severity="warning",
                    check="orphan_concepts",
                    message="",
                    artifact="concepts/Imm Concept",
                ),
                project_root,
                config,
            )
            escalate_stale_concept(
                ValidationIssue(
                    severity="info",
                    check="stale_concept",
                    message="",
                    artifact="concepts/Imm Concept",
                ),
                project_root,
                config,
            )
            escalate_convention_stale(
                ValidationIssue(
                    severity="info",
                    check="convention_stale",
                    message="",
                    artifact="conventions/imm-convention.md",
                ),
                project_root,
                config,
            )
            escalate_playbook_staleness(
                ValidationIssue(
                    severity="info",
                    check="playbook_staleness",
                    message="",
                    artifact=".lexibrary/playbooks/imm-playbook.md",
                ),
                project_root,
                config,
            )

        assert concept.read_bytes() == concept_before
        assert convention.read_bytes() == convention_before
        assert playbook.read_bytes() == playbook_before


# ---------------------------------------------------------------------------
# Cross-fixer contract: all four report same shape
# ---------------------------------------------------------------------------


class TestContractSymmetry:
    """All four fixers share the same escalation result contract."""

    def test_all_four_return_expected_shape(self, tmp_path: Path, _unused: None = None) -> None:
        """fixed=False / llm_calls=0 / outcome_hint='escalation_required'."""
        _ = _unused  # appease flake8
        project_root = tmp_path
        concepts_dir = project_root / ".lexibrary" / "concepts"
        _write_concept(concepts_dir, slug="contract-concept", title="Contract Concept")
        _write_convention(project_root, slug="contract-convention", scope="src/none/")
        playbooks_dir = project_root / ".lexibrary" / "playbooks"
        _write_playbook(playbooks_dir, slug="contract-playbook", last_verified=None)

        config = _make_config()
        fixers = {
            "orphan_concepts": (
                escalate_orphan_concepts,
                "concepts/Contract Concept",
            ),
            "stale_concept": (
                escalate_stale_concept,
                "concepts/Contract Concept",
            ),
            "convention_stale": (
                escalate_convention_stale,
                "conventions/contract-convention.md",
            ),
            "playbook_staleness": (
                escalate_playbook_staleness,
                ".lexibrary/playbooks/contract-playbook.md",
            ),
        }
        with patch("sys.stdout.isatty", return_value=False):
            for check, (fn, artifact) in fixers.items():
                issue = ValidationIssue(
                    severity="info",
                    check=check,
                    message="",
                    artifact=artifact,
                )
                result = fn(issue, project_root, config)
                assert result.fixed is False, f"{check} should not mutate"
                assert result.llm_calls == 0, f"{check} should not charge LLM"
                assert result.outcome_hint == "escalation_required", f"{check} missing hint"


# ---------------------------------------------------------------------------
# Suppress unused datetime import warning (datetime used via timedelta + tests)
# ---------------------------------------------------------------------------


def _quiet_unused_imports() -> datetime:
    """Placeholder reference so linters see ``datetime`` usage."""
    return datetime.now(tz=UTC)
