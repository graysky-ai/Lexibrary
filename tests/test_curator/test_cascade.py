"""Tests for cascade analysis module.

Covers ``build_cascade()``, ``snapshot_link_graph()``, and
``LinkGraphSnapshot`` using mocked link graph queries.

Group 5 tests (TestBuildCascade, TestLinkGraphSnapshot, TestSnapshotLinkGraph)
verify core behaviour with generic mock data.  Group 12 tests
(TestCascadeWithFixtures) verify the same functions using realistic artifact
paths from the Group 9 fixture library at ``tests/fixtures/curator_library/``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lexibrary.curator.cascade import (
    CascadeResult,
    LinkGraphSnapshot,
    build_cascade,
    snapshot_link_graph,
)
from lexibrary.linkgraph.query import LinkResult, TraversalNode

# ---------------------------------------------------------------------------
# Helpers — build mock link graph objects
# ---------------------------------------------------------------------------


def _make_link_result(source_path: str, link_type: str = "wikilink") -> LinkResult:
    """Create a ``LinkResult`` with sensible defaults."""
    return LinkResult(
        source_id=hash(source_path) % 10000,
        source_path=source_path,
        link_type=link_type,
        link_context=None,
    )


def _make_traversal_node(
    path: str,
    depth: int,
    kind: str = "concept",
    link_type: str = "wikilink",
) -> TraversalNode:
    """Create a ``TraversalNode`` with sensible defaults."""
    return TraversalNode(
        artifact_id=hash(path) % 10000,
        path=path,
        kind=kind,
        depth=depth,
        via_link_type=link_type,
    )


def _mock_link_graph(
    reverse_deps_result: list[LinkResult] | None = None,
    traverse_result: list[TraversalNode] | None = None,
) -> MagicMock:
    """Create a mock ``LinkGraph`` with configurable query results."""
    mock = MagicMock()
    mock.reverse_deps.return_value = reverse_deps_result or []
    mock.traverse.return_value = traverse_result or []
    return mock


# ===========================================================================
# build_cascade tests
# ===========================================================================


class TestBuildCascade:
    """Tests for ``build_cascade()``."""

    def test_concept_with_direct_and_transitive_dependents(self) -> None:
        """Concept with 3 direct + 7 transitive deps yields correct counts.

        Task 5.3 / 12.1: concept having 3 direct + 7 transitive dependents.
        """
        # 3 direct dependents
        direct = [
            _make_link_result("designs/file_a.md"),
            _make_link_result("designs/file_b.md"),
            _make_link_result("designs/file_c.md"),
        ]

        # Traverse returns all 10 (3 direct at depth=1 + 7 transitive at depth 2/3)
        traversal = [
            # depth 1 — same as direct deps
            _make_traversal_node("designs/file_a.md", depth=1),
            _make_traversal_node("designs/file_b.md", depth=1),
            _make_traversal_node("designs/file_c.md", depth=1),
            # depth 2 — transitive
            _make_traversal_node("designs/file_d.md", depth=2),
            _make_traversal_node("designs/file_e.md", depth=2),
            _make_traversal_node("designs/file_f.md", depth=2),
            _make_traversal_node("designs/file_g.md", depth=2),
            # depth 3 — further transitive
            _make_traversal_node("designs/file_h.md", depth=3),
            _make_traversal_node("designs/file_i.md", depth=3),
            _make_traversal_node("designs/file_j.md", depth=3),
        ]

        graph = _mock_link_graph(reverse_deps_result=direct, traverse_result=traversal)
        result = build_cascade("concepts/my-concept.md", graph)

        assert isinstance(result, CascadeResult)
        assert len(result.dependents) == 3
        assert len(result.transitive_dependents) == 7
        assert result.dependent_count == 10

        # Verify direct dependents are correct (sorted)
        assert result.dependents == [
            "designs/file_a.md",
            "designs/file_b.md",
            "designs/file_c.md",
        ]

        # Verify transitive dependents exclude direct deps
        assert "designs/file_a.md" not in result.transitive_dependents
        assert "designs/file_b.md" not in result.transitive_dependents
        assert "designs/file_c.md" not in result.transitive_dependents

        # Verify graph was called correctly
        graph.reverse_deps.assert_called_once_with("concepts/my-concept.md")
        graph.traverse.assert_called_once_with(
            "concepts/my-concept.md",
            max_depth=3,
            direction="inbound",
        )

    def test_orphan_concept_zero_dependents(self) -> None:
        """Orphan concept with 0 inbound links yields empty result.

        Task 5.3 / 12.2: orphan with 0 deps.
        """
        graph = _mock_link_graph(reverse_deps_result=[], traverse_result=[])
        result = build_cascade("concepts/orphan.md", graph)

        assert result.dependents == []
        assert result.transitive_dependents == []
        assert result.dependent_count == 0

    def test_cycle_detection_each_artifact_appears_once(self) -> None:
        """When traversal encounters a cycle, each artifact appears at most once.

        Task 5.3 / 12.3: cycle detection in traversal.

        The ``traverse()`` method in ``LinkGraph`` handles cycle detection
        internally via the recursive CTE ``visited`` column.  We verify
        that ``build_cascade()`` deduplicates correctly regardless.
        """
        # Direct: A depends on target
        direct = [_make_link_result("artifacts/a.md")]

        # Traverse: A at depth 1, B at depth 2 (A -> B -> A cycle detected)
        # The traverse() CTE prevents re-visiting, so A appears once.
        traversal = [
            _make_traversal_node("artifacts/a.md", depth=1),
            _make_traversal_node("artifacts/b.md", depth=2),
        ]

        graph = _mock_link_graph(reverse_deps_result=direct, traverse_result=traversal)
        result = build_cascade("concepts/target.md", graph)

        # Each path should appear at most once across both lists
        all_paths = result.dependents + result.transitive_dependents
        assert len(all_paths) == len(set(all_paths)), "Duplicate path found in cascade result"
        assert result.dependent_count == 2

    def test_graceful_degradation_link_graph_none(self) -> None:
        """When link_graph is None, return empty CascadeResult without error.

        Task 5.3 / 12.4: graceful degradation when link graph is None.
        """
        result = build_cascade("concepts/anything.md", None)

        assert result.dependents == []
        assert result.transitive_dependents == []
        assert result.dependent_count == 0

    def test_deduplicate_reverse_deps(self) -> None:
        """Duplicate paths in reverse_deps are deduplicated."""
        direct = [
            _make_link_result("designs/file_a.md", link_type="wikilink"),
            _make_link_result("designs/file_a.md", link_type="ast_import"),
        ]
        traversal = [
            _make_traversal_node("designs/file_a.md", depth=1),
        ]

        graph = _mock_link_graph(reverse_deps_result=direct, traverse_result=traversal)
        result = build_cascade("concepts/dup-test.md", graph)

        assert len(result.dependents) == 1
        assert result.dependents == ["designs/file_a.md"]
        assert result.dependent_count == 1

    def test_only_transitive_no_direct(self) -> None:
        """When reverse_deps is empty but traverse finds nodes, all are transitive."""
        # No direct deps returned by reverse_deps
        # But traverse finds artifacts (possibly through different link types)
        traversal = [
            _make_traversal_node("designs/indirect_a.md", depth=2),
            _make_traversal_node("designs/indirect_b.md", depth=3),
        ]

        graph = _mock_link_graph(reverse_deps_result=[], traverse_result=traversal)
        result = build_cascade("concepts/indirect.md", graph)

        assert result.dependents == []
        assert len(result.transitive_dependents) == 2
        assert result.dependent_count == 2

    def test_results_are_sorted(self) -> None:
        """Both dependent lists are sorted alphabetically."""
        direct = [
            _make_link_result("z_file.md"),
            _make_link_result("a_file.md"),
            _make_link_result("m_file.md"),
        ]
        traversal = [
            _make_traversal_node("z_file.md", depth=1),
            _make_traversal_node("a_file.md", depth=1),
            _make_traversal_node("m_file.md", depth=1),
            _make_traversal_node("z_transitive.md", depth=2),
            _make_traversal_node("a_transitive.md", depth=2),
        ]

        graph = _mock_link_graph(reverse_deps_result=direct, traverse_result=traversal)
        result = build_cascade("concepts/sort-test.md", graph)

        assert result.dependents == ["a_file.md", "m_file.md", "z_file.md"]
        assert result.transitive_dependents == ["a_transitive.md", "z_transitive.md"]


# ===========================================================================
# LinkGraphSnapshot tests
# ===========================================================================


class TestLinkGraphSnapshot:
    """Tests for ``LinkGraphSnapshot``."""

    def test_reverse_deps_cached(self) -> None:
        """Second call to ``reverse_deps`` returns cached result."""
        graph = _mock_link_graph(
            reverse_deps_result=[_make_link_result("designs/a.md")]
        )
        snapshot = LinkGraphSnapshot(_link_graph=graph)

        result1 = snapshot.reverse_deps("concepts/test.md")
        result2 = snapshot.reverse_deps("concepts/test.md")

        assert result1 == result2
        # Only one call to the underlying graph
        graph.reverse_deps.assert_called_once()

    def test_traverse_cached(self) -> None:
        """Second call to ``traverse`` returns cached result."""
        graph = _mock_link_graph(
            traverse_result=[_make_traversal_node("designs/a.md", depth=1)]
        )
        snapshot = LinkGraphSnapshot(_link_graph=graph)

        result1 = snapshot.traverse("concepts/test.md", max_depth=3, direction="inbound")
        result2 = snapshot.traverse("concepts/test.md", max_depth=3, direction="inbound")

        assert result1 == result2
        graph.traverse.assert_called_once()

    def test_different_paths_cached_separately(self) -> None:
        """Different paths produce separate cache entries."""
        graph = _mock_link_graph(
            reverse_deps_result=[_make_link_result("designs/a.md")]
        )
        snapshot = LinkGraphSnapshot(_link_graph=graph)

        snapshot.reverse_deps("concepts/one.md")
        snapshot.reverse_deps("concepts/two.md")

        assert graph.reverse_deps.call_count == 2

    def test_reverse_deps_with_link_type_filter(self) -> None:
        """Link type filter creates separate cache entries."""
        graph = _mock_link_graph(
            reverse_deps_result=[_make_link_result("designs/a.md")]
        )
        snapshot = LinkGraphSnapshot(_link_graph=graph)

        snapshot.reverse_deps("concepts/test.md", link_type=None)
        snapshot.reverse_deps("concepts/test.md", link_type="wikilink")

        assert graph.reverse_deps.call_count == 2

    def test_no_graph_returns_empty(self) -> None:
        """When link graph is None, all queries return empty lists."""
        snapshot = LinkGraphSnapshot(_link_graph=None)

        assert snapshot.reverse_deps("concepts/test.md") == []
        assert snapshot.traverse("concepts/test.md") == []

    def test_build_cascade_delegates_to_cached_queries(self) -> None:
        """``build_cascade()`` on snapshot uses cached queries."""
        direct = [
            _make_link_result("designs/a.md"),
            _make_link_result("designs/b.md"),
        ]
        traversal = [
            _make_traversal_node("designs/a.md", depth=1),
            _make_traversal_node("designs/b.md", depth=1),
            _make_traversal_node("designs/c.md", depth=2),
        ]
        graph = _mock_link_graph(
            reverse_deps_result=direct,
            traverse_result=traversal,
        )
        snapshot = LinkGraphSnapshot(_link_graph=graph)

        result = snapshot.build_cascade("concepts/test.md")

        assert result.dependent_count == 3
        assert len(result.dependents) == 2
        assert len(result.transitive_dependents) == 1
        assert result.transitive_dependents == ["designs/c.md"]

    def test_build_cascade_no_graph_returns_empty(self) -> None:
        """``build_cascade()`` with no graph returns empty result."""
        snapshot = LinkGraphSnapshot(_link_graph=None)
        result = snapshot.build_cascade("concepts/test.md")

        assert result == CascadeResult()

    def test_snapshot_consistency_across_calls(self) -> None:
        """Multiple build_cascade calls see the same snapshot data.

        Verifies that even if the underlying graph were to change,
        the snapshot returns consistent cached results.
        """
        direct = [_make_link_result("designs/a.md")]
        traversal = [_make_traversal_node("designs/a.md", depth=1)]
        graph = _mock_link_graph(
            reverse_deps_result=direct,
            traverse_result=traversal,
        )
        snapshot = LinkGraphSnapshot(_link_graph=graph)

        result1 = snapshot.build_cascade("concepts/test.md")

        # Modify the mock return value — snapshot should still use cache
        graph.reverse_deps.return_value = [
            _make_link_result("designs/a.md"),
            _make_link_result("designs/new.md"),
        ]

        result2 = snapshot.build_cascade("concepts/test.md")

        assert result1.dependent_count == result2.dependent_count
        assert result1.dependents == result2.dependents


# ===========================================================================
# snapshot_link_graph tests
# ===========================================================================


class TestSnapshotLinkGraph:
    """Tests for ``snapshot_link_graph()``."""

    def test_creates_snapshot_with_graph(self, tmp_path: Path) -> None:
        """When link graph is available, snapshot wraps it."""
        mock_graph = _mock_link_graph()

        with patch(
            "lexibrary.linkgraph.query.open_index",
            return_value=mock_graph,
        ):
            snapshot = snapshot_link_graph(tmp_path)

        assert snapshot._link_graph is mock_graph

    def test_creates_snapshot_without_graph(self, tmp_path: Path) -> None:
        """When link graph is unavailable, snapshot has None graph."""
        with patch(
            "lexibrary.linkgraph.query.open_index",
            return_value=None,
        ):
            snapshot = snapshot_link_graph(tmp_path)

        assert snapshot._link_graph is None
        assert snapshot.reverse_deps("any/path.md") == []

    def test_logs_warning_when_no_graph(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Warning is logged when link graph is unavailable."""
        with patch(
            "lexibrary.linkgraph.query.open_index",
            return_value=None,
        ):
            snapshot_link_graph(tmp_path)

        assert any("Link graph unavailable" in record.message for record in caplog.records)
        assert any("lexictl update" in record.message for record in caplog.records)


# ===========================================================================
# Fixture-based cascade analysis tests (Group 12)
#
# These tests use artifact paths from the Group 9 test fixture library at
# tests/fixtures/curator_library/ and mock link graph queries with data
# that matches the fixture's link graph topology.
#
# Fixture topology (from linkgraph.db):
#   CN-003 (Deprecated Target Concept): 3 inbound wikilinks
#     from designs/src/auth/login.py.md, session.py.md, models/user.py.md
#   CN-004 (Orphan Concept): 0 inbound links
#   CN-006 (Superseded Concept): 2 inbound wikilinks
#     from designs/src/utils/helpers.py.md, formatting.py.md
#   CN-007 (Healthy Control Concept): 1 inbound wikilink
#     from designs/src/auth/__init__.py.md
# ===========================================================================


# Fixture artifact paths (match tests/fixtures/curator_library/.lexibrary/)
_CN003_PATH = "concepts/CN-003-deprecated-target-concept.md"
_CN004_PATH = "concepts/CN-004-orphan-concept.md"
_CN006_PATH = "concepts/CN-006-superseded-concept.md"
_CN007_PATH = "concepts/CN-007-healthy-control-concept.md"

# Design file paths that reference CN-003
_DS_LOGIN = "designs/src/auth/login.py.md"
_DS_SESSION = "designs/src/auth/session.py.md"
_DS_USER = "designs/src/models/user.py.md"

# Design file paths that reference CN-006
_DS_HELPERS = "designs/src/utils/helpers.py.md"
_DS_FORMATTING = "designs/src/utils/formatting.py.md"

# Design file path that references CN-007
_DS_INIT = "designs/src/auth/__init__.py.md"


class TestCascadeWithFixtures:
    """Cascade analysis tests using paths from the Group 9 fixture library.

    These tests mock ``reverse_deps()`` and ``traverse()`` with data that
    mirrors the actual link graph topology in the fixture, verifying that
    ``build_cascade()`` correctly processes realistic artifact structures.

    Task 12.1-12.4: cascade analysis with link graph queries.
    """

    def test_concept_cn003_three_direct_seven_transitive(self) -> None:
        """CN-003 has 3 direct dependents and 7 transitive for total of 10.

        Task 12.1: concept with 3 direct + 7 transitive dependents.

        CN-003 is referenced directly by 3 design files (login, session,
        user).  The transitive dependents model the realistic scenario where
        those design files are themselves referenced by other artifacts,
        reaching 7 additional unique paths at depth 2 and 3.
        """
        # 3 direct dependents matching fixture link graph edges
        direct = [
            _make_link_result(_DS_LOGIN, link_type="wikilink"),
            _make_link_result(_DS_SESSION, link_type="wikilink"),
            _make_link_result(_DS_USER, link_type="wikilink"),
        ]

        # Traverse returns all 10: 3 direct at depth=1, 7 transitive at depth 2/3
        # Transitive dependents model realistic cascade through the fixture topology
        traversal = [
            # depth 1 -- direct dependents (same as reverse_deps)
            _make_traversal_node(_DS_LOGIN, depth=1, kind="design"),
            _make_traversal_node(_DS_SESSION, depth=1, kind="design"),
            _make_traversal_node(_DS_USER, depth=1, kind="design"),
            # depth 2 -- artifacts that reference the direct dependents
            _make_traversal_node("concepts/CN-001-authentication.md", depth=2, kind="concept"),
            _make_traversal_node(
                "conventions/CV-001-old-auth-pattern.md", depth=2, kind="convention",
            ),
            _make_traversal_node(_DS_HELPERS, depth=2, kind="design"),
            _make_traversal_node(_DS_FORMATTING, depth=2, kind="design"),
            # depth 3 -- further transitive
            _make_traversal_node(_DS_INIT, depth=3, kind="design"),
            _make_traversal_node(_CN006_PATH, depth=3, kind="concept"),
            _make_traversal_node(_CN007_PATH, depth=3, kind="concept"),
        ]

        graph = _mock_link_graph(reverse_deps_result=direct, traverse_result=traversal)
        result = build_cascade(_CN003_PATH, graph)

        assert isinstance(result, CascadeResult)
        assert len(result.dependents) == 3
        assert len(result.transitive_dependents) == 7
        assert result.dependent_count == 10

        # Direct dependents are the 3 design files referencing CN-003
        assert result.dependents == sorted([_DS_LOGIN, _DS_SESSION, _DS_USER])

        # Transitive dependents exclude direct dependents
        for direct_path in [_DS_LOGIN, _DS_SESSION, _DS_USER]:
            assert direct_path not in result.transitive_dependents

        # All transitive dependents present
        assert _CN006_PATH in result.transitive_dependents
        assert _CN007_PATH in result.transitive_dependents
        assert "concepts/CN-001-authentication.md" in result.transitive_dependents

        # Verify link graph was called with the correct fixture path
        graph.reverse_deps.assert_called_once_with(_CN003_PATH)
        graph.traverse.assert_called_once_with(
            _CN003_PATH,
            max_depth=3,
            direction="inbound",
        )

    def test_orphan_cn004_zero_dependents(self) -> None:
        """CN-004 (orphan) has zero inbound links, yielding empty cascade.

        Task 12.2: orphan concept with empty lists and dependent_count=0.

        CN-004 is a planted orphan fixture with no edges targeting it in
        the link graph.
        """
        graph = _mock_link_graph(reverse_deps_result=[], traverse_result=[])
        result = build_cascade(_CN004_PATH, graph)

        assert result.dependents == []
        assert result.transitive_dependents == []
        assert result.dependent_count == 0

        graph.reverse_deps.assert_called_once_with(_CN004_PATH)
        graph.traverse.assert_called_once_with(
            _CN004_PATH,
            max_depth=3,
            direction="inbound",
        )

    def test_cycle_detection_cn006_with_mutual_reference(self) -> None:
        """Cycle in traversal from CN-006 -- each artifact appears at most once.

        Task 12.3: mock traverse() encountering a cycle.

        Simulates a scenario where CN-006 (Superseded Concept) has
        dependents that form a cycle: helpers.py.md references CN-006,
        formatting.py.md references helpers.py.md, and CN-006 references
        formatting.py.md -- creating a loop.  The traverse() CTE detects
        cycles internally, so each node appears once in the output.
        """
        # Direct dependents of CN-006 from fixture
        direct = [
            _make_link_result(_DS_HELPERS, link_type="wikilink"),
            _make_link_result(_DS_FORMATTING, link_type="wikilink"),
        ]

        # Traversal with cycle: CN-006 -> helpers -> formatting -> CN-006 (stopped)
        # The CTE prevents re-visiting CN-006, so it does not appear in traversal
        traversal = [
            _make_traversal_node(_DS_HELPERS, depth=1, kind="design"),
            _make_traversal_node(_DS_FORMATTING, depth=1, kind="design"),
            # depth 2: formatting references helpers (already visited at depth 1,
            # but traverse may still report it once depending on graph structure)
        ]

        graph = _mock_link_graph(reverse_deps_result=direct, traverse_result=traversal)
        result = build_cascade(_CN006_PATH, graph)

        # Each path appears at most once across both lists
        all_paths = result.dependents + result.transitive_dependents
        assert len(all_paths) == len(set(all_paths)), (
            f"Duplicate path in cascade result: {all_paths}"
        )

        # Both dependents are direct (no unique transitive paths beyond the cycle)
        assert result.dependent_count == 2
        assert _DS_HELPERS in result.dependents
        assert _DS_FORMATTING in result.dependents

    def test_cycle_detection_deep_cycle_deduplication(self) -> None:
        """Deep cycle involving fixture paths -- artifacts deduplicated.

        Task 12.3 (extended): A more complex cycle scenario where
        traverse() returns nodes that overlap with direct dependents
        and each other, verifying thorough deduplication.
        """
        # CN-003 direct dependents
        direct = [
            _make_link_result(_DS_LOGIN, link_type="wikilink"),
            _make_link_result(_DS_SESSION, link_type="wikilink"),
        ]

        # Traverse returns a cycle: login -> session -> login (cycle stopped)
        # Plus one additional transitive node
        traversal = [
            _make_traversal_node(_DS_LOGIN, depth=1, kind="design"),
            _make_traversal_node(_DS_SESSION, depth=1, kind="design"),
            # session references login, but login already visited -- cycle
            # traverse stops, but reports one more node found before cycle
            _make_traversal_node(_DS_USER, depth=2, kind="design"),
        ]

        graph = _mock_link_graph(reverse_deps_result=direct, traverse_result=traversal)
        result = build_cascade(_CN003_PATH, graph)

        all_paths = result.dependents + result.transitive_dependents
        assert len(all_paths) == len(set(all_paths)), (
            f"Duplicate path in cascade result: {all_paths}"
        )
        assert result.dependent_count == 3
        assert result.dependents == sorted([_DS_LOGIN, _DS_SESSION])
        assert result.transitive_dependents == [_DS_USER]

    def test_graceful_degradation_link_graph_none_fixture_path(self) -> None:
        """link_graph=None with fixture path returns empty CascadeResult.

        Task 12.4: graceful degradation when link graph is None.

        Uses a real fixture path to confirm that build_cascade() returns
        safely regardless of which artifact path is queried.
        """
        result = build_cascade(_CN003_PATH, None)

        assert result.dependents == []
        assert result.transitive_dependents == []
        assert result.dependent_count == 0

    def test_graceful_degradation_none_logs_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """link_graph=None logs a warning with the artifact path.

        Task 12.4 (extended): verify the warning includes enough context
        for operators to diagnose the issue.
        """
        with caplog.at_level(logging.INFO, logger="lexibrary.curator.cascade"):
            build_cascade(_CN004_PATH, None)

        warning_records = [
            r for r in caplog.records
            if r.levelname == "WARNING" and _CN004_PATH in r.message
        ]
        assert len(warning_records) == 1
        assert "lexictl update" in warning_records[0].message
