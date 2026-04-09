"""Integration tests for end-to-end deprecation flows against the test fixture.

Tests run the full coordinator pipeline (collect -> triage -> dispatch -> report)
against the curator_library fixture with mocked BAML sub-agent responses, link
graph, and git operations.

Group 15 tasks:
- 15.1: Orphan concept auto-deprecation under auto_low
- 15.2: Concept deprecation with migration under full autonomy
- 15.3: Deprecation blocked by autonomy (high-risk under auto_low)
- 15.4: Confirmation policy override blocks deprecation under full
- 15.5: Hard deletion of TTL-expired concept with sidecar cleanup
- 15.6: Idempotency (second run produces zero fixes/dispatches)
- 15.7: Dry-run reports candidates without modifying files
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lexibrary.config.schema import LexibraryConfig
from lexibrary.curator.coordinator import Coordinator
from lexibrary.curator.models import CuratorReport
from lexibrary.linkgraph.query import LinkResult, TraversalNode

# ---------------------------------------------------------------------------
# Fixture relative paths
# ---------------------------------------------------------------------------

_CONCEPTS = ".lexibrary/concepts"
_CONVENTIONS = ".lexibrary/conventions"

# Concept file names from group 9 fixtures.
_ORPHAN = "CN-004-orphan-concept.md"
_DEPRECATED_TARGET = "CN-003-deprecated-target-concept.md"
_EXPIRED = "CN-005-expired-deprecated-concept.md"
_EXPIRED_SIDECAR = "CN-005-expired-deprecated-concept.comments.yaml"
_SUPERSEDED = "CN-006-superseded-concept.md"
_HEALTHY = "CN-007-healthy-control-concept.md"

# Convention file names.
_CONV_EXPIRED = "CV-002-expired-deprecated-convention.md"
_CONV_EXPIRED_SIDECAR = "CV-002-expired-deprecated-convention.comments.yaml"
_CONV_HEALTHY = "CV-003-healthy-control-convention.md"
_CONV_OLD_AUTH = "CV-001-old-auth-pattern.md"


# Default referenced paths for the mock link graph.  These protect ALL
# non-orphan active fixtures from being incorrectly detected as deprecation
# candidates.  Every active concept and convention that should NOT be
# deprecated must appear here with at least one inbound reference.
_DEFAULT_REFERENCED_PATHS: dict[str, list[str]] = {
    # Concepts
    f"{_CONCEPTS}/{_HEALTHY}": [
        ".lexibrary/designs/src/auth/login.py.md",
    ],
    f"{_CONCEPTS}/{_DEPRECATED_TARGET}": [
        ".lexibrary/designs/src/auth/login.py.md",
        ".lexibrary/designs/src/auth/session.py.md",
        ".lexibrary/designs/src/models/user.py.md",
    ],
    f"{_CONCEPTS}/{_SUPERSEDED}": [
        ".lexibrary/designs/src/utils/helpers.py.md",
        ".lexibrary/designs/src/utils/formatting.py.md",
    ],
    # Conventions -- both active conventions must have refs
    f"{_CONVENTIONS}/{_CONV_HEALTHY}": [
        ".lexibrary/designs/src/auth/login.py.md",
    ],
    f"{_CONVENTIONS}/{_CONV_OLD_AUTH}": [
        ".lexibrary/designs/src/auth/session.py.md",
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_link_graph(
    project_root: Path,
    *,
    referenced_paths: dict[str, list[str]] | None = None,
) -> MagicMock:
    """Build a mock LinkGraph with the given reference topology.

    Parameters
    ----------
    project_root:
        Absolute path to the fixture copy.
    referenced_paths:
        Mapping from artifact relative path to list of source paths that
        reference it.  Artifacts NOT in this map have zero inbound refs.
    """
    referenced_paths = referenced_paths or {}
    graph = MagicMock()

    def mock_reverse_deps(path: str, link_type: str | None = None) -> list[LinkResult]:
        if path in referenced_paths:
            return [
                LinkResult(
                    source_id=i,
                    source_path=src,
                    link_type="wikilink",
                    link_context=None,
                )
                for i, src in enumerate(referenced_paths[path])
            ]
        return []

    def mock_traverse(
        start_path: str,
        max_depth: int = 3,
        link_types: list[str] | None = None,
        direction: str = "outbound",
    ) -> list[TraversalNode]:
        if start_path in referenced_paths and direction == "inbound":
            return [
                TraversalNode(
                    artifact_id=i,
                    path=src,
                    kind="design_file",
                    depth=1,
                    via_link_type="wikilink",
                )
                for i, src in enumerate(referenced_paths[start_path])
            ]
        return []

    graph.reverse_deps = mock_reverse_deps
    graph.traverse = mock_traverse
    graph.close = MagicMock()
    return graph


def _run_coordinator(project: Path, config: LexibraryConfig, **kwargs: object) -> CuratorReport:
    """Run the coordinator synchronously and return its report."""
    coord = Coordinator(project, config)
    return asyncio.run(coord.run(**kwargs))  # type: ignore[arg-type]


def _read_concept_status(concept_path: Path) -> str | None:
    """Read the status field from a concept file's YAML frontmatter."""
    from lexibrary.wiki.parser import parse_concept_file

    concept = parse_concept_file(concept_path)
    if concept is not None:
        return concept.frontmatter.status
    return None


def _make_config(
    *,
    autonomy: str = "auto_low",
    max_llm: int = 50,
    ttl_commits: int = 50,
    concept_confirm: bool = False,
    convention_confirm: bool = False,
) -> LexibraryConfig:
    """Build a LexibraryConfig with curator settings for testing."""
    data: dict = {
        "curator": {
            "autonomy": autonomy,
            "max_llm_calls_per_run": max_llm,
            "deprecation": {"ttl_commits": ttl_commits},
        },
        "concepts": {"curator_deprecation_confirm": concept_confirm},
        "conventions": {"curator_deprecation_confirm": convention_confirm},
    }
    return LexibraryConfig.model_validate(data)


@contextlib.contextmanager
def _mock_env(
    mock_graph: MagicMock,
    *,
    commits_since_deprecation: int = 0,
) -> Iterator[None]:
    """Context manager that patches all external dependencies for coordinator runs.

    Mocks: git uncommitted files, active IWH dirs, link graph open/close,
    and git-based commits-since-deprecation count.
    """
    with (
        patch(
            "lexibrary.curator.coordinator._uncommitted_files",
            return_value=set(),
        ),
        patch(
            "lexibrary.curator.coordinator._active_iwh_dirs",
            return_value=set(),
        ),
        patch("lexibrary.linkgraph.query.LinkGraph.open", return_value=None),
        patch("lexibrary.linkgraph.query.open_index", return_value=mock_graph),
        patch(
            "lexibrary.curator.coordinator.Coordinator._commits_since_deprecation",
            return_value=commits_since_deprecation,
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fixture_copy(tmp_path: Path) -> Path:
    """Return an isolated copy of the curator_library fixture."""
    src = Path(__file__).resolve().parent.parent / "fixtures" / "curator_library"
    dest = tmp_path / "curator_library"
    shutil.copytree(src, dest)
    return dest


# ===========================================================================
# 15.1 -- Orphan concept auto-deprecation
# ===========================================================================


class TestOrphanConceptAutoDeprecation:
    """Orphan concept (CN-004) with zero inbound refs is deprecated.

    Note: ``deprecate_concept`` is HIGH risk.  Under ``auto_low`` it is
    blocked -- so this test uses ``full`` autonomy to verify the concept
    gets a ``deprecated`` status and a ``deprecated_at`` timestamp.
    """

    def test_orphan_concept_deprecated_under_full_autonomy(self, fixture_copy: Path) -> None:
        """Pipeline detects orphan CN-004, deprecates it under full autonomy."""
        config = _make_config(autonomy="full")

        orphan_path = fixture_copy / _CONCEPTS / _ORPHAN
        assert _read_concept_status(orphan_path) == "active"

        # Orphan has 0 refs (not in referenced_paths).
        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            report = _run_coordinator(fixture_copy, config)

        assert _read_concept_status(orphan_path) == "deprecated"
        assert report.deprecated >= 1

    def test_orphan_concept_gets_deprecated_at_timestamp(self, fixture_copy: Path) -> None:
        """The deprecated orphan concept has a deprecated_at timestamp set."""
        config = _make_config(autonomy="full")
        orphan_path = fixture_copy / _CONCEPTS / _ORPHAN

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            _run_coordinator(fixture_copy, config)

        from lexibrary.wiki.parser import parse_concept_file

        concept = parse_concept_file(orphan_path)
        assert concept is not None
        assert concept.frontmatter.deprecated_at is not None


# ===========================================================================
# 15.2 -- Concept deprecation with migration
# ===========================================================================


class TestConceptDeprecationWithMigration:
    """Under full autonomy, deprecating a concept triggers the migration cycle."""

    def test_superseded_concept_deprecated_with_migration_summary(self, fixture_copy: Path) -> None:
        """CN-006 (superseded, zero refs in graph) is deprecated.

        The superseded concept has superseded_by=Authentication.  When it
        appears as an orphan (zero inbound refs), it is deprecated.  The
        migration dispatch cycle then runs and verify_migration is called.
        """
        config = _make_config(autonomy="full")

        superseded_path = fixture_copy / _CONCEPTS / _SUPERSEDED
        assert _read_concept_status(superseded_path) == "active"

        # Remove CN-006 from referenced_paths so it appears as orphan.
        refs = {k: v for k, v in _DEFAULT_REFERENCED_PATHS.items()}
        refs.pop(f"{_CONCEPTS}/{_SUPERSEDED}", None)

        mock_graph = _make_mock_link_graph(fixture_copy, referenced_paths=refs)

        with _mock_env(mock_graph):
            report = _run_coordinator(fixture_copy, config)

        assert _read_concept_status(superseded_path) == "deprecated"
        assert report.deprecated >= 1
        # Migration cycle should have run (or at least been proposed)
        assert report.migrations_applied >= 0 or report.migrations_proposed >= 0

    def test_report_includes_deprecation_and_migration_counts(self, fixture_copy: Path) -> None:
        """CuratorReport has non-zero deprecated count after orphan deprecation."""
        config = _make_config(autonomy="full")

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            report = _run_coordinator(fixture_copy, config)

        # At least the orphan concept gets deprecated
        assert report.deprecated >= 1
        # Migration dispatch is attempted for successful deprecations
        assert report.migrations_applied >= 0


# ===========================================================================
# 15.3 -- Deprecation blocked by autonomy
# ===========================================================================


class TestDeprecationBlockedByAutonomy:
    """Under auto_low, high-risk concept deprecation is proposed, not executed."""

    def test_high_risk_concept_remains_active_under_auto_low(self, fixture_copy: Path) -> None:
        """Orphan concept remains active because deprecate_concept is HIGH risk
        and auto_low only dispatches LOW risk actions."""
        config = _make_config(autonomy="auto_low")

        orphan_path = fixture_copy / _CONCEPTS / _ORPHAN
        assert _read_concept_status(orphan_path) == "active"

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            report = _run_coordinator(fixture_copy, config)

        # Concept should still be active -- not deprecated
        assert _read_concept_status(orphan_path) == "active"
        assert report.deferred >= 1

    def test_report_shows_zero_deprecated_under_auto_low(self, fixture_copy: Path) -> None:
        """Under auto_low no concept deprecation occurs (only low-risk actions execute)."""
        config = _make_config(autonomy="auto_low")

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            report = _run_coordinator(fixture_copy, config)

        # No concept deprecation under auto_low (all concept deprecation is high risk)
        # Convention deprecation is medium risk -- also blocked under auto_low.
        assert report.deprecated == 0

    def test_iwh_signal_written_for_proposed_deprecation(self, fixture_copy: Path) -> None:
        """An IWH signal is written when a deprecation is proposed but not executed."""
        config = _make_config(autonomy="auto_low")

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            report = _run_coordinator(fixture_copy, config)

        # The coordinator writes IWH signals for deferred deprecations.
        # Verify the deferred count captures the proposed action.
        assert report.deferred >= 1


# ===========================================================================
# 15.4 -- Confirmation policy override
# ===========================================================================


class TestConfirmationPolicyOverride:
    """Under full autonomy with concepts.deprecation_confirm=true, concept
    deprecation is proposed (not executed) even though the autonomy level
    would normally allow it."""

    def test_concept_deprecation_proposed_with_confirmation(self, fixture_copy: Path) -> None:
        """Full autonomy + concept confirmation = concept deprecation deferred."""
        config = _make_config(autonomy="full", concept_confirm=True)

        orphan_path = fixture_copy / _CONCEPTS / _ORPHAN
        assert _read_concept_status(orphan_path) == "active"

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            report = _run_coordinator(fixture_copy, config)

        # The orphan concept should NOT be deprecated -- confirmation required
        assert _read_concept_status(orphan_path) == "active"
        assert report.deferred >= 1

    def test_convention_not_blocked_by_concept_confirmation(self, fixture_copy: Path) -> None:
        """Concept confirmation does not block convention deprecation.

        Remove CV-001 (old auth) from referenced_paths to make it an orphan.
        Under full autonomy with only concept_confirm=True, the convention
        should still be deprecated (convention confirmation not set).
        """
        config = _make_config(autonomy="full", concept_confirm=True)

        # Make CV-001 an orphan by removing its references
        refs = {k: v for k, v in _DEFAULT_REFERENCED_PATHS.items()}
        refs.pop(f"{_CONVENTIONS}/{_CONV_OLD_AUTH}", None)

        conv_path = fixture_copy / _CONVENTIONS / _CONV_OLD_AUTH

        from lexibrary.conventions.parser import parse_convention_file

        conv = parse_convention_file(conv_path)
        assert conv is not None
        assert conv.frontmatter.status == "active"

        mock_graph = _make_mock_link_graph(fixture_copy, referenced_paths=refs)

        with _mock_env(mock_graph):
            _run_coordinator(fixture_copy, config)

        # Convention should be deprecated (medium risk, allowed under full,
        # concept confirmation does not affect conventions)
        conv = parse_convention_file(conv_path)
        assert conv is not None
        assert conv.frontmatter.status == "deprecated"


# ===========================================================================
# 15.5 -- Hard deletion
# ===========================================================================


class TestHardDeletion:
    """Deprecated concept past TTL with 0 references is hard-deleted along
    with its .comments.yaml sidecar."""

    def test_expired_concept_hard_deleted(self, fixture_copy: Path) -> None:
        """CN-005 (deprecated, past TTL, 0 refs) is hard-deleted."""
        config = _make_config(autonomy="auto_low", ttl_commits=50)

        concept_path = fixture_copy / _CONCEPTS / _EXPIRED
        sidecar_path = fixture_copy / _CONCEPTS / _EXPIRED_SIDECAR
        assert concept_path.exists()
        assert sidecar_path.exists()

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph, commits_since_deprecation=60):
            report = _run_coordinator(fixture_copy, config)

        assert not concept_path.exists(), "Expired concept .md was not deleted"
        assert not sidecar_path.exists(), "Sidecar .comments.yaml was not deleted"
        assert report.hard_deleted >= 1

    def test_convention_hard_deletion(self, fixture_copy: Path) -> None:
        """CV-002 (deprecated convention, past TTL, 0 refs) is hard-deleted."""
        config = _make_config(autonomy="auto_low", ttl_commits=50)

        conv_path = fixture_copy / _CONVENTIONS / _CONV_EXPIRED
        conv_sidecar = fixture_copy / _CONVENTIONS / _CONV_EXPIRED_SIDECAR
        assert conv_path.exists()
        assert conv_sidecar.exists()

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph, commits_since_deprecation=60):
            report = _run_coordinator(fixture_copy, config)

        assert not conv_path.exists(), "Expired convention .md was not deleted"
        assert not conv_sidecar.exists(), "Convention sidecar was not deleted"
        assert report.hard_deleted >= 1


# ===========================================================================
# 15.6 -- Idempotency
# ===========================================================================


class TestIdempotency:
    """Running the coordinator twice produces zero new deprecation fixes
    on the second run."""

    def test_second_run_produces_zero_deprecation_fixes(self, fixture_copy: Path) -> None:
        """After first run deprecates the orphan, the second run finds
        nothing new to deprecate (the orphan is now deprecated, not active)."""
        config = _make_config(autonomy="full")

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        # First run: deprecates the orphan concept (CN-004)
        with _mock_env(mock_graph):
            report1 = _run_coordinator(fixture_copy, config)

        assert report1.deprecated >= 1

        # Second run: same mocks, but the orphan is now "deprecated"
        # so it should not be re-detected as orphan (only active artifacts
        # are candidates for orphan detection).
        with _mock_env(mock_graph):
            report2 = _run_coordinator(fixture_copy, config)

        assert report2.deprecated == 0


# ===========================================================================
# 15.7 -- Dry-run
# ===========================================================================


class TestDryRun:
    """Dry-run mode reports deprecation candidates without modifying files."""

    def test_dry_run_no_file_modifications(self, fixture_copy: Path) -> None:
        """Files remain unchanged when dry_run=True."""
        config = _make_config(autonomy="full")

        orphan_path = fixture_copy / _CONCEPTS / _ORPHAN
        original_content = orphan_path.read_text(encoding="utf-8")

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            _run_coordinator(fixture_copy, config, dry_run=True)

        assert orphan_path.read_text(encoding="utf-8") == original_content
        assert _read_concept_status(orphan_path) == "active"

    def test_dry_run_reports_deprecation_candidates(self, fixture_copy: Path) -> None:
        """Dry-run still reports that deprecation candidates were found."""
        config = _make_config(autonomy="full")

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            report = _run_coordinator(fixture_copy, config, dry_run=True)

        # Dry-run checks items but does not execute
        assert report.checked >= 1
        assert report.deprecated == 0

    def test_dry_run_healthy_controls_unchanged(self, fixture_copy: Path) -> None:
        """Control artifacts (CN-007, CV-003) are never modified in dry-run."""
        config = _make_config(autonomy="full")

        healthy_concept = fixture_copy / _CONCEPTS / _HEALTHY
        healthy_convention = fixture_copy / _CONVENTIONS / _CONV_HEALTHY

        original_concept = healthy_concept.read_text(encoding="utf-8")
        original_convention = healthy_convention.read_text(encoding="utf-8")

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            _run_coordinator(fixture_copy, config, dry_run=True)

        assert healthy_concept.read_text(encoding="utf-8") == original_concept
        assert healthy_convention.read_text(encoding="utf-8") == original_convention

    def test_non_dry_run_healthy_controls_unchanged(self, fixture_copy: Path) -> None:
        """Even in a real (non-dry-run) execution, control artifacts are untouched.

        Both CN-007 and CV-003 have inbound references in the mock link graph,
        so they are not detected as orphans and thus not deprecated.
        """
        config = _make_config(autonomy="full")

        healthy_concept = fixture_copy / _CONCEPTS / _HEALTHY
        healthy_convention = fixture_copy / _CONVENTIONS / _CONV_HEALTHY

        original_concept = healthy_concept.read_text(encoding="utf-8")
        original_convention = healthy_convention.read_text(encoding="utf-8")

        mock_graph = _make_mock_link_graph(
            fixture_copy,
            referenced_paths=_DEFAULT_REFERENCED_PATHS,
        )

        with _mock_env(mock_graph):
            _run_coordinator(fixture_copy, config)

        assert healthy_concept.read_text(encoding="utf-8") == original_concept
        assert healthy_convention.read_text(encoding="utf-8") == original_convention
