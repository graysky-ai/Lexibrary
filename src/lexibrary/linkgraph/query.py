"""Read-only query interface for the link graph index.

Provides the :class:`LinkGraph` class and structured result dataclasses
for querying the SQLite link graph populated by the builder (Phase 10b).

Result dataclasses are defined at module level and returned by all query
methods instead of raw tuples or dictionaries:

- :class:`ArtifactResult` -- common return type for artifact lookups
- :class:`LinkResult` -- for reference/dependency queries
- :class:`TraversalNode` -- for multi-hop graph traversal results
- :class:`ConventionResult` -- for convention inheritance
- :class:`BuildSummaryEntry` -- for build summary statistics
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from lexibrary.linkgraph.schema import SCHEMA_VERSION, check_schema_version, set_pragmas

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ArtifactResult:
    """An artifact row from the link graph index.

    Common return type for single-entity lookups (``get_artifact``,
    ``resolve_alias``), tag search, and full-text search.
    """

    id: int
    path: str
    kind: str
    title: str | None
    status: str | None


@dataclass
class LinkResult:
    """A link (edge) pointing *to* a queried artifact.

    Returned by ``reverse_deps`` to describe inbound references.
    ``source_id`` and ``source_path`` identify the artifact that holds
    the reference; ``link_type`` classifies it (e.g. ``"ast_import"``,
    ``"wikilink"``); ``link_context`` carries optional contextual text.
    """

    source_id: int
    source_path: str
    link_type: str
    link_context: str | None


@dataclass
class TraversalNode:
    """A node discovered during multi-hop graph traversal.

    Returned by ``traverse``.  ``depth`` indicates how many hops from
    the start node this artifact was reached, and ``via_link_type``
    records the edge type of the last hop.
    """

    artifact_id: int
    path: str
    kind: str
    depth: int
    via_link_type: str | None


@dataclass
class ConventionResult:
    """A local convention body scoped to a directory path.

    Returned by ``get_conventions``, ordered by directory depth
    (root-to-leaf) then ordinal within each directory.
    """

    body: str
    directory_path: str
    ordinal: int


@dataclass
class BuildSummaryEntry:
    """Aggregate statistics for one action type in the most recent build.

    Returned by ``build_summary``.  ``action`` is one of
    ``"created"``, ``"updated"``, ``"deleted"``, ``"unchanged"``, or
    ``"failed"``.  ``count`` is the number of artifacts with that action.
    ``total_duration_ms`` is the sum of ``duration_ms`` for those artifacts.
    """

    action: str
    count: int
    total_duration_ms: int | None


# ---------------------------------------------------------------------------
# LinkGraph — read-only query interface
# ---------------------------------------------------------------------------


class LinkGraph:
    """Read-only query interface for the link graph SQLite index.

    The primary constructor accepts an already-open :class:`sqlite3.Connection`.
    Most callers should use the :meth:`open` classmethod, which handles file
    existence checks, corruption detection, and schema version validation,
    returning ``None`` when the database cannot be used (graceful degradation).

    Supports the context manager protocol (``with LinkGraph.open(...) as g:``)
    and explicit :meth:`close`.

    All queries use parameterised statements (``?`` placeholders) and the
    connection is opened in read-only mode via the SQLite URI syntax
    (``?mode=ro``).  Any accidental write will raise
    :class:`sqlite3.OperationalError`.
    """

    # -- construction -------------------------------------------------------

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Wrap an already-open SQLite connection for read-only queries.

        Parameters
        ----------
        conn:
            An open :class:`sqlite3.Connection`.  Callers are responsible
            for ensuring pragmas have been set and the schema version is
            compatible.  Prefer :meth:`open` for normal usage.
        """
        self._conn = conn

    @classmethod
    def open(cls, db_path: str | Path) -> LinkGraph | None:
        """Open the link graph database at *db_path* for read-only queries.

        Returns a :class:`LinkGraph` instance on success, or ``None`` when:

        * The database file does not exist.
        * The file is corrupt (``sqlite3.DatabaseError``).
        * The schema version is missing or does not match
          :data:`~lexibrary.linkgraph.schema.SCHEMA_VERSION`.

        The connection is opened in **read-only** mode using SQLite URI
        syntax (``file:<path>?mode=ro``).  On success, WAL and FK pragmas
        are applied via :func:`set_pragmas`.

        Parameters
        ----------
        db_path:
            Path to the ``index.db`` file (typically
            ``<project_root>/.lexibrary/index.db``).

        Returns
        -------
        LinkGraph | None
            A ready-to-query instance, or ``None`` for graceful degradation.
        """
        db_path = Path(db_path)

        # Guard: file must exist on disk
        if not db_path.is_file():
            return None

        conn: sqlite3.Connection | None = None
        try:
            # Open in read-only mode via URI syntax
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)

            # Apply WAL / FK / synchronous pragmas
            set_pragmas(conn)

            # Verify schema version
            version = check_schema_version(conn)
            if version is None or version != SCHEMA_VERSION:
                logger.warning(
                    "Schema version mismatch for %s: expected %s, got %s",
                    db_path,
                    SCHEMA_VERSION,
                    version,
                )
                conn.close()
                return None

        except sqlite3.DatabaseError as exc:
            logger.warning("Cannot open link graph %s: %s", db_path, exc)
            if conn is not None:
                with contextlib.suppress(Exception):
                    conn.close()
            return None

        return cls(conn)

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def __enter__(self) -> LinkGraph:
        """Enter the context manager, returning *self*."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager, closing the connection."""
        self.close()

    # -- single-entity queries ----------------------------------------------

    def get_artifact(self, path: str) -> ArtifactResult | None:
        """Look up an artifact by its path.

        Parameters
        ----------
        path:
            The project-relative path of the artifact (e.g.
            ``"src/auth/service.py"``).

        Returns
        -------
        ArtifactResult | None
            The matching artifact, or ``None`` if no artifact with
            that path exists in the index.
        """
        row = self._conn.execute(
            "SELECT id, path, kind, title, status FROM artifacts WHERE path = ?",
            (path,),
        ).fetchone()
        if row is None:
            return None
        return ArtifactResult(
            id=row[0],
            path=row[1],
            kind=row[2],
            title=row[3],
            status=row[4],
        )

    def resolve_alias(self, alias: str) -> ArtifactResult | None:
        """Resolve a concept alias to its artifact.

        Matching is **case-insensitive** (the ``aliases`` table uses
        ``COLLATE NOCASE``).

        Parameters
        ----------
        alias:
            The alias string to resolve (e.g. ``"auth"``).

        Returns
        -------
        ArtifactResult | None
            The artifact that owns the alias, or ``None`` if no
            matching alias exists.
        """
        row = self._conn.execute(
            "SELECT a.id, a.path, a.kind, a.title, a.status "
            "FROM aliases AS al "
            "JOIN artifacts AS a ON al.artifact_id = a.id "
            "WHERE al.alias = ? COLLATE NOCASE",
            (alias,),
        ).fetchone()
        if row is None:
            return None
        return ArtifactResult(
            id=row[0],
            path=row[1],
            kind=row[2],
            title=row[3],
            status=row[4],
        )

    # -- relationship queries -----------------------------------------------

    def reverse_deps(self, path: str, link_type: str | None = None) -> list[LinkResult]:
        """Return all inbound links to the artifact at *path*.

        Looks up the artifact by path, then queries the ``links`` table
        for all rows whose ``target_id`` matches.  When *link_type* is
        provided, only links of that type are returned.

        Parameters
        ----------
        path:
            The project-relative path of the target artifact.
        link_type:
            Optional filter restricting results to a single link type
            (e.g. ``"ast_import"``, ``"wikilink"``).

        Returns
        -------
        list[LinkResult]
            All inbound links, or an empty list when the artifact is
            not in the index or has no inbound references.
        """
        # Resolve the target artifact id first
        target_row = self._conn.execute(
            "SELECT id FROM artifacts WHERE path = ?",
            (path,),
        ).fetchone()
        if target_row is None:
            return []

        target_id = target_row[0]

        if link_type is not None:
            rows = self._conn.execute(
                "SELECT a.id, a.path, l.link_type, l.link_context "
                "FROM links AS l "
                "JOIN artifacts AS a ON l.source_id = a.id "
                "WHERE l.target_id = ? AND l.link_type = ?",
                (target_id, link_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT a.id, a.path, l.link_type, l.link_context "
                "FROM links AS l "
                "JOIN artifacts AS a ON l.source_id = a.id "
                "WHERE l.target_id = ?",
                (target_id,),
            ).fetchall()

        return [
            LinkResult(
                source_id=row[0],
                source_path=row[1],
                link_type=row[2],
                link_context=row[3],
            )
            for row in rows
        ]

    def search_by_tag(self, tag: str) -> list[ArtifactResult]:
        """Find all artifacts tagged with *tag*.

        Queries the ``tags`` table and joins with ``artifacts`` to
        return full artifact records.

        Parameters
        ----------
        tag:
            The tag string to search for (exact match).

        Returns
        -------
        list[ArtifactResult]
            All artifacts that carry the given tag, or an empty list
            when no artifacts match.
        """
        rows = self._conn.execute(
            "SELECT a.id, a.path, a.kind, a.title, a.status "
            "FROM tags AS t "
            "JOIN artifacts AS a ON t.artifact_id = a.id "
            "WHERE t.tag = ?",
            (tag,),
        ).fetchall()

        return [
            ArtifactResult(
                id=row[0],
                path=row[1],
                kind=row[2],
                title=row[3],
                status=row[4],
            )
            for row in rows
        ]

    def full_text_search(self, query: str, limit: int = 20) -> list[ArtifactResult]:
        """Search indexed artifacts via FTS5 full-text search.

        The *query* string is wrapped in double quotes so that FTS5
        operators (``AND``, ``OR``, ``NOT``, etc.) are treated as
        literal terms, preventing syntax errors from user input.

        Results are ordered by FTS5 relevance rank (lower is better)
        and capped at *limit*.

        Parameters
        ----------
        query:
            The search string.  Special FTS5 characters are
            automatically escaped by literal quoting.
        limit:
            Maximum number of results to return (default 20).

        Returns
        -------
        list[ArtifactResult]
            Matching artifacts ordered by relevance, or an empty list
            when nothing matches.
        """
        # Escape any embedded double quotes then wrap for literal matching
        safe_query = '"' + query.replace('"', '""') + '"'

        rows = self._conn.execute(
            "SELECT a.id, a.path, a.kind, a.title, a.status "
            "FROM artifacts_fts AS f "
            "JOIN artifacts AS a ON f.rowid = a.id "
            "WHERE artifacts_fts MATCH ? "
            "ORDER BY f.rank "
            "LIMIT ?",
            (safe_query, limit),
        ).fetchall()

        return [
            ArtifactResult(
                id=row[0],
                path=row[1],
                kind=row[2],
                title=row[3],
                status=row[4],
            )
            for row in rows
        ]

    def get_conventions(self, directory_paths: list[str]) -> list[ConventionResult]:
        """Retrieve conventions for a list of directory paths.

        Returns conventions ordered by their position in
        *directory_paths* (which should be ordered root-to-leaf),
        then by ``ordinal`` within each directory.  This gives
        convention inheritance: root conventions first, then
        progressively more specific overrides.

        Parameters
        ----------
        directory_paths:
            Directory paths to query, ordered from root to leaf
            (e.g. ``["src", "src/auth", "src/auth/middleware"]``).

        Returns
        -------
        list[ConventionResult]
            All matching conventions in inheritance order, or an
            empty list when no conventions exist for any of the
            given paths.
        """
        if not directory_paths:
            return []

        # Build a mapping from path to its order index for sorting
        path_order = {p: i for i, p in enumerate(directory_paths)}

        placeholders = ", ".join("?" for _ in directory_paths)
        rows = self._conn.execute(
            "SELECT body, directory_path, ordinal "
            "FROM conventions "
            f"WHERE directory_path IN ({placeholders}) "
            "ORDER BY directory_path, ordinal",
            tuple(directory_paths),
        ).fetchall()

        results = [
            ConventionResult(
                body=row[0],
                directory_path=row[1],
                ordinal=row[2],
            )
            for row in rows
        ]

        # Sort by the caller-specified path order, then ordinal
        results.sort(key=lambda c: (path_order.get(c.directory_path, 0), c.ordinal))

        return results

    # -- multi-hop traversal -----------------------------------------------

    _MAX_DEPTH_CAP = 10
    """Hard upper limit for ``traverse`` depth to guarantee termination."""

    def traverse(
        self,
        start_path: str,
        max_depth: int = 3,
        link_types: list[str] | None = None,
        direction: str = "outbound",
    ) -> list[TraversalNode]:
        """Perform multi-hop graph traversal from *start_path*.

        Uses a recursive CTE to walk the link graph up to *max_depth*
        hops.  Cycle detection is built into the CTE via a
        comma-separated ``visited`` column that prevents revisiting
        nodes already on the current traversal path.

        Parameters
        ----------
        start_path:
            The project-relative path of the starting artifact
            (e.g. ``"src/api/controller.py"``).
        max_depth:
            Maximum number of hops to traverse (default 3).  Clamped
            to a hard cap of 10 regardless of the value supplied.
        link_types:
            Optional list of link type strings (e.g.
            ``["ast_import"]``) to restrict which edges are followed.
            When ``None`` (default), all link types are followed.
        direction:
            ``"outbound"`` (default) follows links from source to
            target (forward dependencies).  ``"inbound"`` follows
            links from target to source (reverse dependency chain).

        Returns
        -------
        list[TraversalNode]
            All reachable artifacts up to *max_depth* hops, excluding
            the start node itself.  Returns an empty list when the
            start path is not in the index.
        """
        # Clamp max_depth to hard cap
        max_depth = min(max_depth, self._MAX_DEPTH_CAP)

        # Resolve the starting artifact
        start = self.get_artifact(start_path)
        if start is None:
            return []

        # Determine traversal direction columns
        if direction == "inbound":
            # Follow edges backwards: find rows where target_id matches,
            # then move to source_id
            match_col = "target_id"
            next_col = "source_id"
        else:
            # Follow edges forwards: find rows where source_id matches,
            # then move to target_id
            match_col = "source_id"
            next_col = "target_id"

        # Build the optional link_type filter clause
        if link_types:
            lt_placeholders = ", ".join("?" for _ in link_types)
            link_filter = f" AND l.link_type IN ({lt_placeholders})"
            link_params: tuple[object, ...] = tuple(link_types)
        else:
            link_filter = ""
            link_params = ()

        # Recursive CTE for multi-hop traversal with cycle detection.
        #
        # The ``visited`` column accumulates a comma-separated list of
        # artifact ids seen along the current path.  The recursive step
        # only follows an edge when the next node's id does not appear
        # in the visited list, preventing infinite loops on cyclic graphs.
        sql = (
            "WITH RECURSIVE reachable(artifact_id, depth, link_type, visited) AS ("
            "  SELECT"
            f"    l.{next_col},"
            "    1,"
            "    l.link_type,"
            f"    ',' || ? || ',' || CAST(l.{next_col} AS TEXT) || ','"
            "  FROM links AS l"
            f"  WHERE l.{match_col} = ?"
            f"  {link_filter}"
            "  UNION ALL"
            "  SELECT"
            f"    l.{next_col},"
            "    r.depth + 1,"
            "    l.link_type,"
            f"    r.visited || CAST(l.{next_col} AS TEXT) || ','"
            "  FROM reachable AS r"
            f"  JOIN links AS l ON l.{match_col} = r.artifact_id"
            "  WHERE r.depth < ?"
            f"    AND r.visited NOT LIKE '%,' || CAST(l.{next_col} AS TEXT) || ',%'"
            f"  {link_filter}"
            ")"
            " SELECT DISTINCT r.artifact_id, a.path, a.kind, r.depth, r.link_type"
            " FROM reachable AS r"
            " JOIN artifacts AS a ON r.artifact_id = a.id"
            " ORDER BY r.depth, a.path"
        )

        # Build parameter tuple: start_id (for visited init), start_id
        # (for WHERE), optional link_type params (base case),
        # max_depth, optional link_type params (recursive case)
        params: tuple[object, ...] = (
            start.id,
            start.id,
            *link_params,
            max_depth,
            *link_params,
        )

        rows = self._conn.execute(sql, params).fetchall()

        return [
            TraversalNode(
                artifact_id=row[0],
                path=row[1],
                kind=row[2],
                depth=row[3],
                via_link_type=row[4],
            )
            for row in rows
        ]

    # -- build summary ------------------------------------------------------

    def build_summary(self) -> list[BuildSummaryEntry]:
        """Return aggregate statistics for the most recent build.

        Identifies the most recent ``build_started`` timestamp in the
        ``build_log`` table and groups entries by ``action``, returning
        the count and sum of ``duration_ms`` for each action type.

        Returns
        -------
        list[BuildSummaryEntry]
            One entry per action type in the most recent build, or
            an empty list when the build log has no entries.
        """
        # Find the most recent build timestamp
        ts_row = self._conn.execute("SELECT MAX(build_started) FROM build_log").fetchone()
        if ts_row is None or ts_row[0] is None:
            return []

        latest_ts = ts_row[0]

        rows = self._conn.execute(
            "SELECT action, COUNT(*) AS cnt, SUM(duration_ms) AS total_ms "
            "FROM build_log "
            "WHERE build_started = ? "
            "GROUP BY action "
            "ORDER BY action",
            (latest_ts,),
        ).fetchall()

        return [
            BuildSummaryEntry(
                action=row[0],
                count=row[1],
                total_duration_ms=row[2],
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# Module-level convenience opener
# ---------------------------------------------------------------------------

_INDEX_DB_NAME = "index.db"
"""Filename of the SQLite index database within ``.lexibrary/``."""


def open_index(project_root: Path) -> LinkGraph | None:
    """Open the link graph index for read-only queries.

    Computes the database path as ``<project_root>/.lexibrary/index.db``
    and delegates to :meth:`LinkGraph.open`.  Returns ``None`` when the
    database is missing, corrupt, or has an incompatible schema version
    -- callers should branch on ``None`` for graceful degradation.

    Parameters
    ----------
    project_root:
        Absolute path to the repository root.

    Returns
    -------
    LinkGraph | None
        A ready-to-query :class:`LinkGraph` instance, or ``None``.
    """
    from lexibrary.utils.paths import LEXIBRARY_DIR

    db_path = project_root / LEXIBRARY_DIR / _INDEX_DB_NAME
    return LinkGraph.open(db_path)
