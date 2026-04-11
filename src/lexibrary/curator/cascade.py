"""Cascade analysis for deprecation impact assessment.

Uses link graph APIs to compute the direct and transitive dependents
of an artifact before deprecation dispatch.  The :func:`build_cascade`
function is called during the coordinator's triage phase; the
:func:`snapshot_link_graph` function creates an immutable snapshot of
link graph query results at the start of a run so the coordinator works
from a consistent view.

Public API
----------
- :func:`build_cascade` -- compute direct and transitive dependents
- :func:`snapshot_link_graph` -- create immutable snapshot for a run
- :class:`CascadeResult` -- direct + transitive dependent data
- :class:`LinkGraphSnapshot` -- cached, immutable link graph queries
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lexibrary.linkgraph.query import LinkGraph, LinkResult, TraversalNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CascadeResult:
    """Direct and transitive dependents of an artifact.

    Attributes
    ----------
    dependents:
        Paths of artifacts that directly reference the target artifact
        (via ``reverse_deps``).
    transitive_dependents:
        Paths of artifacts reachable via multi-hop inbound traversal
        (up to ``max_depth=3``), *excluding* direct dependents.
    dependent_count:
        Total count of unique dependents (direct + transitive).
    """

    dependents: list[str] = field(default_factory=list)
    transitive_dependents: list[str] = field(default_factory=list)
    dependent_count: int = 0


# ---------------------------------------------------------------------------
# Cascade analysis
# ---------------------------------------------------------------------------


def build_cascade(
    artifact_path: str,
    link_graph: LinkGraph | None,
) -> CascadeResult:
    """Compute direct and transitive dependents of an artifact.

    Uses ``reverse_deps()`` for direct dependents and
    ``traverse(max_depth=3, direction='inbound')`` for transitive
    dependents.  When *link_graph* is ``None``, returns an empty
    :class:`CascadeResult` (graceful degradation).

    Parameters
    ----------
    artifact_path:
        Project-relative path to the artifact (e.g.
        ``".lexibrary/concepts/my-concept.md"``).
    link_graph:
        Open link graph instance, or ``None`` if unavailable.

    Returns
    -------
    CascadeResult
        The cascade analysis result with direct dependents,
        transitive dependents, and total dependent count.
    """
    if link_graph is None:
        logger.warning(
            "Link graph unavailable -- skipping cascade analysis for %s. "
            "Run `lexictl update` to rebuild the link graph.",
            artifact_path,
        )
        return CascadeResult()

    # Direct dependents via reverse_deps
    direct_links: list[LinkResult] = link_graph.reverse_deps(artifact_path)
    direct_paths: list[str] = sorted({link.source_path for link in direct_links})

    # Transitive dependents via inbound traversal (who depends on this
    # artifact, and who depends on *those* artifacts, etc.)
    traversal_nodes: list[TraversalNode] = link_graph.traverse(
        artifact_path,
        max_depth=3,
        direction="inbound",
    )

    # All traversal paths (includes direct dependents at depth=1)
    all_traversal_paths: set[str] = {node.path for node in traversal_nodes}

    # Transitive-only = traversal results minus direct dependents
    direct_set = set(direct_paths)
    transitive_paths: list[str] = sorted(all_traversal_paths - direct_set)

    # Total unique count
    all_unique = direct_set | set(transitive_paths)
    dependent_count = len(all_unique)

    return CascadeResult(
        dependents=direct_paths,
        transitive_dependents=transitive_paths,
        dependent_count=dependent_count,
    )


# ---------------------------------------------------------------------------
# Link graph snapshot
# ---------------------------------------------------------------------------


@dataclass
class LinkGraphSnapshot:
    """Immutable snapshot of link graph queries for a single coordinator run.

    Created at the start of a run by :func:`snapshot_link_graph`.
    Caches ``reverse_deps`` and ``traverse`` results so that all
    triage and dispatch decisions within the run use a consistent view
    of the link graph, even if deprecations within the run modify
    the underlying artifacts.

    The snapshot is discarded at the end of the run (not persisted).
    """

    _reverse_deps_cache: dict[str, list[LinkResult]] = field(default_factory=dict)
    _traverse_cache: dict[tuple[str, int, str], list[TraversalNode]] = field(
        default_factory=dict,
    )
    _link_graph: LinkGraph | None = field(default=None, repr=False)

    def reverse_deps(
        self,
        path: str,
        link_type: str | None = None,
    ) -> list[LinkResult]:
        """Return cached reverse dependencies for *path*.

        On first call for a given path, queries the underlying link
        graph and caches the result.  Subsequent calls return the
        cached value.

        Parameters
        ----------
        path:
            Project-relative artifact path.
        link_type:
            Optional link type filter (passed through to the
            underlying ``reverse_deps`` call).

        Returns
        -------
        list[LinkResult]
            Inbound links to the artifact, or an empty list if the
            link graph is unavailable or the artifact has no inbound
            references.
        """
        cache_key = f"{path}:{link_type}"
        if cache_key not in self._reverse_deps_cache:
            if self._link_graph is None:
                self._reverse_deps_cache[cache_key] = []
            else:
                self._reverse_deps_cache[cache_key] = self._link_graph.reverse_deps(path, link_type)
        return self._reverse_deps_cache[cache_key]

    def traverse(
        self,
        start_path: str,
        max_depth: int = 3,
        direction: str = "inbound",
    ) -> list[TraversalNode]:
        """Return cached traversal results from *start_path*.

        On first call for a given (path, depth, direction) tuple,
        queries the underlying link graph and caches the result.
        Subsequent calls return the cached value.

        Parameters
        ----------
        start_path:
            Project-relative path of the starting artifact.
        max_depth:
            Maximum traversal depth (default 3).
        direction:
            Traversal direction (``"inbound"`` or ``"outbound"``).

        Returns
        -------
        list[TraversalNode]
            Reachable artifacts, or an empty list if the link graph
            is unavailable.
        """
        cache_key = (start_path, max_depth, direction)
        if cache_key not in self._traverse_cache:
            if self._link_graph is None:
                self._traverse_cache[cache_key] = []
            else:
                self._traverse_cache[cache_key] = self._link_graph.traverse(
                    start_path,
                    max_depth=max_depth,
                    direction=direction,
                )
        return self._traverse_cache[cache_key]

    def build_cascade(self, artifact_path: str) -> CascadeResult:
        """Build cascade analysis using the snapshot's cached queries.

        Convenience method that delegates to :func:`build_cascade`
        using the snapshot's own caching layer.

        Parameters
        ----------
        artifact_path:
            Project-relative path to the artifact.

        Returns
        -------
        CascadeResult
            The cascade analysis result.
        """
        if self._link_graph is None:
            return CascadeResult()

        # Use cached reverse_deps for direct dependents
        direct_links = self.reverse_deps(artifact_path)
        direct_paths: list[str] = sorted({link.source_path for link in direct_links})

        # Use cached traverse for transitive dependents
        traversal_nodes = self.traverse(artifact_path, max_depth=3, direction="inbound")
        all_traversal_paths: set[str] = {node.path for node in traversal_nodes}

        direct_set = set(direct_paths)
        transitive_paths: list[str] = sorted(all_traversal_paths - direct_set)
        all_unique = direct_set | set(transitive_paths)

        return CascadeResult(
            dependents=direct_paths,
            transitive_dependents=transitive_paths,
            dependent_count=len(all_unique),
        )


def snapshot_link_graph(project_root: Path) -> LinkGraphSnapshot:
    """Create an immutable link graph snapshot for a coordinator run.

    Opens the link graph index and wraps it in a
    :class:`LinkGraphSnapshot`.  All subsequent queries during the run
    use the snapshot's cache, ensuring a consistent view.

    When the link graph is unavailable (``open_index`` returns ``None``),
    the snapshot is created with no underlying graph -- all queries
    return empty results and a warning is logged.

    Parameters
    ----------
    project_root:
        Absolute path to the project root directory.

    Returns
    -------
    LinkGraphSnapshot
        A snapshot that caches link graph queries for the run.
    """
    from lexibrary.linkgraph.query import open_index  # noqa: PLC0415

    link_graph = open_index(project_root)

    if link_graph is None:
        logger.warning(
            "Link graph unavailable at %s -- cascade analysis and orphan detection "
            "will be skipped. Run `lexictl update` to rebuild.",
            project_root,
        )

    return LinkGraphSnapshot(_link_graph=link_graph)
