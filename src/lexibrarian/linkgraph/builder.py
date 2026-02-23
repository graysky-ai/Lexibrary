"""LinkGraph index builder -- populates the SQLite index from parsed artifacts.

Reads four artifact families (design files, concept files, Stack posts, and
``.aindex`` convention files), resolves cross-references, and writes rows into
the link graph schema created by :mod:`lexibrarian.linkgraph.schema`.

Two entry modes:

* **Full build** (``full_build``) -- clears all data and rebuilds from scratch.
* **Incremental update** (``incremental_update``) -- reprocesses only the
  changed files, deleting stale outbound data and reinserting from current
  content.

Public helpers ``build_index`` and ``open_index`` provide the module-level API.
"""

from __future__ import annotations

import contextlib
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lexibrarian.archivist.dependency_extractor import extract_dependencies
from lexibrarian.artifacts.aindex import AIndexFile  # noqa: F401
from lexibrarian.artifacts.aindex_parser import parse_aindex
from lexibrarian.artifacts.concept import ConceptFile  # noqa: F401
from lexibrarian.artifacts.design_file import DesignFile  # noqa: F401
from lexibrarian.artifacts.design_file_parser import parse_design_file
from lexibrarian.linkgraph.schema import (
    ensure_schema,
    set_pragmas,
)
from lexibrarian.stack.models import StackPost  # noqa: F401
from lexibrarian.stack.parser import parse_stack_post  # noqa: F401
from lexibrarian.utils.hashing import hash_file
from lexibrarian.utils.paths import LEXIBRARY_DIR
from lexibrarian.wiki.parser import parse_concept_file  # noqa: F401

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex for extracting [[wikilinks]] from arbitrary text
# ---------------------------------------------------------------------------

_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class BuildResult:
    """Summary returned by ``full_build`` and ``incremental_update``."""

    artifact_count: int = 0
    link_count: int = 0
    duration_ms: int = 0
    errors: list[str] = field(default_factory=list)
    build_type: str = "full"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _extract_wikilinks(text: str) -> list[str]:
    """Extract ``[[wikilink]]`` targets from *text*, returning deduplicated names.

    Matches ``[[...]]`` patterns where the content contains no nested brackets.
    Duplicate names are removed while preserving first-occurrence order.

    Args:
        text: Arbitrary text that may contain ``[[WikilinkName]]`` patterns.

    Returns:
        Deduplicated list of wikilink target names in order of first appearance.
    """
    seen: set[str] = set()
    result: list[str] = []
    for match in _WIKILINK_RE.finditer(text):
        name = match.group(1).strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


# ---------------------------------------------------------------------------
# Builder version identifier
# ---------------------------------------------------------------------------

_BUILDER_ID = "lexibrarian-v2"
"""Builder identifier stored in the ``meta`` table."""

# ---------------------------------------------------------------------------
# Stale build log retention (days)
# ---------------------------------------------------------------------------

_STALE_LOG_DAYS = 30
"""Build log entries older than this many days are deleted at build start."""


# ---------------------------------------------------------------------------
# IndexBuilder -- foundation class
# ---------------------------------------------------------------------------


class IndexBuilder:
    """Populates the link graph SQLite index from parsed artifact families.

    The builder is instantiated with an open ``sqlite3.Connection`` (which
    should already have the schema ensured) and the ``project_root`` path.
    It provides ``full_build()`` and ``incremental_update()`` entry points.

    Parameters
    ----------
    conn:
        An open SQLite connection.  ``set_pragmas()`` is called as a safety
        measure during construction.
    project_root:
        Absolute path to the repository root.
    """

    def __init__(self, conn: sqlite3.Connection, project_root: Path) -> None:
        set_pragmas(conn)
        self.conn = conn
        self.project_root = project_root

    # -- housekeeping -------------------------------------------------------

    def _clean_stale_build_log(self) -> None:
        """Delete ``build_log`` rows older than :data:`_STALE_LOG_DAYS` days."""
        # Compute the cutoff as an ISO 8601 string 30 days in the past.
        # ISO 8601 strings sort lexicographically the same as chronologically,
        # so a simple string comparison works for the DELETE WHERE clause.
        cutoff = (datetime.now(UTC) - timedelta(days=_STALE_LOG_DAYS)).isoformat()
        self.conn.execute(
            "DELETE FROM build_log WHERE build_started < ?",
            (cutoff,),
        )
        self.conn.commit()

    def _clear_all_data(self) -> None:
        """Delete all rows from data tables, preserving schema and ``meta``.

        Tables cleared: ``artifacts``, ``links``, ``tags``, ``aliases``,
        ``conventions``, ``artifacts_fts``.  The ``build_log`` and ``meta``
        tables are intentionally preserved.
        """
        # Order matters: child tables first to respect FK constraints if
        # foreign_keys pragma is ON.  However DELETE does not enforce FK
        # ordering in SQLite when cascading, so we disable FK checks
        # temporarily to be safe.
        tables = [
            "links",
            "tags",
            "aliases",
            "conventions",
            "artifacts_fts",
            "artifacts",
        ]
        for table in tables:
            self.conn.execute(f"DELETE FROM {table}")

    def _update_meta(self, build_started: str) -> None:
        """Update ``meta`` table with build summary counts and timestamp.

        Parameters
        ----------
        build_started:
            ISO 8601 timestamp of when the build started.
        """
        artifact_count = self.conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        link_count = self.conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]

        updates = {
            "built_at": build_started,
            "builder": _BUILDER_ID,
            "artifact_count": str(artifact_count),
            "link_count": str(link_count),
        }
        for key, value in updates.items():
            self.conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (key, value),
            )

    # -- artifact CRUD helpers ----------------------------------------------

    def _insert_artifact(
        self,
        path: str,
        kind: str,
        title: str | None,
        status: str | None,
        last_hash: str | None,
        created_at: str | None,
    ) -> int:
        """Insert a row into ``artifacts`` and return the new row id.

        Parameters
        ----------
        path:
            Project-relative path (or synthetic path for conventions).
        kind:
            One of ``'source'``, ``'design'``, ``'concept'``, ``'stack'``,
            ``'convention'``.
        title:
            Human-readable title (may be ``None``).
        status:
            Artifact status (may be ``None``).
        last_hash:
            SHA-256 hash of the source file (may be ``None``).
        created_at:
            ISO 8601 creation timestamp (may be ``None``).

        Returns
        -------
        int
            The ``id`` of the newly inserted artifact row.
        """
        cursor = self.conn.execute(
            "INSERT INTO artifacts (path, kind, title, status, last_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (path, kind, title, status, last_hash, created_at),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def _get_artifact_id(self, path: str) -> int | None:
        """Look up an artifact by *path* and return its ``id``, or ``None``.

        Parameters
        ----------
        path:
            The ``artifacts.path`` value to look up.

        Returns
        -------
        int | None
            The artifact ``id`` if found, otherwise ``None``.
        """
        row = self.conn.execute(
            "SELECT id FROM artifacts WHERE path = ?",
            (path,),
        ).fetchone()
        return row[0] if row is not None else None

    def _get_or_create_artifact(
        self,
        path: str,
        kind: str,
        title: str | None = None,
    ) -> int:
        """Return an existing artifact ``id`` or insert a stub and return it.

        This is used during link creation when the target artifact may not
        have been explicitly inserted yet (e.g., a concept referenced by a
        wikilink that has no concept file on disk).

        Parameters
        ----------
        path:
            Project-relative path of the artifact.
        kind:
            Artifact kind (used only when inserting a new stub).
        title:
            Optional title for the stub artifact.

        Returns
        -------
        int
            The artifact ``id``.
        """
        existing = self._get_artifact_id(path)
        if existing is not None:
            return existing
        return self._insert_artifact(
            path=path,
            kind=kind,
            title=title,
            status=None,
            last_hash=None,
            created_at=None,
        )

    # -- link / tag / FTS insertion helpers ---------------------------------

    def _insert_link(
        self,
        source_id: int,
        target_id: int,
        link_type: str,
        link_context: str | None = None,
    ) -> None:
        """Insert a row into ``links``, ignoring duplicates.

        Uses ``INSERT OR IGNORE`` so that re-processing a file does not
        fail on the ``UNIQUE(source_id, target_id, link_type)`` constraint.
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO links (source_id, target_id, link_type, link_context) "
            "VALUES (?, ?, ?, ?)",
            (source_id, target_id, link_type, link_context),
        )

    def _insert_tag(self, artifact_id: int, tag: str) -> None:
        """Insert a tag row, ignoring duplicates."""
        self.conn.execute(
            "INSERT OR IGNORE INTO tags (artifact_id, tag) VALUES (?, ?)",
            (artifact_id, tag),
        )

    def _insert_fts(self, rowid: int, title: str | None, body: str) -> None:
        """Insert an FTS5 row for an artifact.

        Parameters
        ----------
        rowid:
            Must match the corresponding ``artifacts.id``.
        title:
            Artifact title (may be ``None``).
        body:
            Full-text body content for search.
        """
        self.conn.execute(
            "INSERT INTO artifacts_fts (rowid, title, body) VALUES (?, ?, ?)",
            (rowid, title or "", body),
        )

    def _insert_alias(self, artifact_id: int, alias: str, concept_path: str) -> None:
        """Insert an alias row using first-writer-wins semantics.

        Uses ``INSERT OR IGNORE`` so that the ``UNIQUE(alias)`` constraint
        (with ``COLLATE NOCASE``) silently skips duplicates.  When a duplicate
        is detected, a warning is logged identifying both concepts.

        Parameters
        ----------
        artifact_id:
            The ``artifacts.id`` of the concept that owns this alias.
        alias:
            The alias text (case-insensitive uniqueness enforced by schema).
        concept_path:
            Project-relative path of the concept file, used in warning logs.
        """
        cursor = self.conn.execute(
            "INSERT OR IGNORE INTO aliases (artifact_id, alias) VALUES (?, ?)",
            (artifact_id, alias),
        )
        if cursor.rowcount == 0:
            # Alias already claimed by another concept -- find the owner
            existing = self.conn.execute(
                "SELECT a.path FROM aliases al "
                "JOIN artifacts a ON al.artifact_id = a.id "
                "WHERE al.alias = ? COLLATE NOCASE",
                (alias,),
            ).fetchone()
            existing_path = existing[0] if existing else "<unknown>"
            logger.warning(
                "Alias '%s' already claimed by '%s', skipping for '%s'",
                alias,
                existing_path,
                concept_path,
            )

    # -- concept file processing (task group 4) -----------------------------

    def _scan_concept_files(self) -> list[Path]:
        """Discover all ``.md`` files under ``.lexibrary/concepts/``.

        Returns a sorted list of absolute ``Path`` objects for deterministic
        processing order (sorted by path ensures stable alias winner selection
        per design decision D7).
        """
        concepts_root = self.project_root / LEXIBRARY_DIR / "concepts"
        if not concepts_root.is_dir():
            return []
        return sorted(concepts_root.rglob("*.md"))

    def _process_concept_file(self, concept_path: Path, build_started: str) -> None:
        """Parse a concept file and insert all related artifacts, links, tags, aliases, and FTS.

        This is the main entry point for processing a single concept file during
        a full build.  It handles:

        1. Concept artifact insertion
        2. Alias insertion (first-writer-wins on duplicates)
        3. ``wikilink`` links from concept body to other concepts
        4. ``concept_file_ref`` links from concept to referenced source files
        5. Tags associated with the concept artifact
        6. FTS row for the concept artifact

        Parameters
        ----------
        concept_path:
            Absolute path to the concept file on disk.
        build_started:
            ISO 8601 timestamp of the current build (for ``build_log``).
        """
        start_ns = time.monotonic_ns()

        # Parse the concept file
        concept_file = parse_concept_file(concept_path)
        if concept_file is None:
            error_msg = f"Failed to parse concept file: {concept_path}"
            logger.warning(error_msg)
            concept_rel = str(concept_path.relative_to(self.project_root))
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'full', ?, 'concept', 'failed', ?, ?)",
                (
                    build_started,
                    concept_rel,
                    (time.monotonic_ns() - start_ns) // 1_000_000,
                    error_msg,
                ),
            )
            return

        concept_relpath = str(concept_path.relative_to(self.project_root))

        # 1. Concept artifact -- use _get_or_create_artifact so that stub
        #    artifacts (created by design file wikilinks) are reused rather
        #    than duplicated.
        concept_id = self._get_or_create_artifact(
            concept_relpath, "concept", title=concept_file.frontmatter.title
        )
        # Update the artifact with full details (title, status) in case
        # it was originally inserted as a stub.
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ? WHERE id = ?",
            (concept_file.frontmatter.title, concept_file.frontmatter.status, concept_id),
        )

        # 2. Aliases
        for alias in concept_file.frontmatter.aliases:
            self._insert_alias(concept_id, alias, concept_relpath)

        # 3. Wikilinks from concept body -> other concepts
        wikilink_names = _extract_wikilinks(concept_file.body)
        for wikilink_name in wikilink_names:
            target_concept_path = f".lexibrary/concepts/{wikilink_name}.md"
            target_id = self._get_or_create_artifact(
                target_concept_path, "concept", title=wikilink_name
            )
            self._insert_link(concept_id, target_id, "wikilink")

        # 4. concept_file_ref links from concept to referenced source files
        for file_ref in concept_file.linked_files:
            target_id = self._get_or_create_artifact(file_ref, "source")
            self._insert_link(concept_id, target_id, "concept_file_ref")

        # 5. Tags
        for tag in concept_file.frontmatter.tags:
            self._insert_tag(concept_id, tag)

        # 6. FTS row -- body = summary + "\n" + body
        fts_body_parts = []
        if concept_file.summary:
            fts_body_parts.append(concept_file.summary)
        if concept_file.body:
            fts_body_parts.append(concept_file.body)
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(concept_id, concept_file.frontmatter.title, fts_body)

        # Log success
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) VALUES (?, 'full', ?, 'concept', 'created', ?)",
            (build_started, concept_relpath, duration_ms),
        )

    # -- design file processing (task group 3) ------------------------------

    def _scan_design_files(self) -> list[Path]:
        """Discover all ``.md`` files under ``.lexibrary/src/`` (the design file mirror tree).

        Returns a sorted list of absolute ``Path`` objects for deterministic
        processing order.
        """
        design_root = self.project_root / LEXIBRARY_DIR / "src"
        if not design_root.is_dir():
            return []
        return sorted(design_root.rglob("*.md"))

    def _design_path_to_source_relpath(self, design_path: Path) -> str:
        """Convert an absolute design file path to the project-relative source path.

        ``.lexibrary/src/auth/login.py.md`` -> ``src/auth/login.py``

        The design mirror tree stores ``<source_path>.md`` under
        ``.lexibrary/``, so we strip the ``.lexibrary/`` prefix and the
        trailing ``.md`` extension.
        """
        # Make the design path relative to project_root
        rel = design_path.relative_to(self.project_root)
        # Strip leading ".lexibrary/" prefix
        # rel looks like: .lexibrary/src/auth/login.py.md
        parts = rel.parts
        if parts[0] == LEXIBRARY_DIR:
            parts = parts[1:]
        # Reconstruct without the .lexibrary prefix
        inner = Path(*parts) if parts else rel
        # Strip trailing .md to get the source path
        source_relpath = str(inner)[: -len(".md")] if str(inner).endswith(".md") else str(inner)
        return source_relpath

    def _compute_source_hash(self, source_relpath: str) -> str | None:
        """Compute SHA-256 hash of the source file, or ``None`` if it does not exist.

        Parameters
        ----------
        source_relpath:
            Project-relative path to the source file (e.g. ``src/auth/login.py``).

        Returns
        -------
        str | None
            Hex digest string, or ``None`` when the file is missing.
        """
        source_abs = self.project_root / source_relpath
        if not source_abs.is_file():
            return None
        try:
            return hash_file(source_abs)
        except OSError:
            logger.warning("Cannot hash source file: %s", source_abs)
            return None

    def _extract_ast_imports(
        self,
        source_relpath: str,
        source_artifact_id: int,
    ) -> None:
        """Extract AST imports from a source file and insert ``ast_import`` links.

        Calls :func:`extract_dependencies` on the source file, filters to
        project-internal paths (the extractor already does this), creates
        stub artifacts for import targets that lack existing artifact rows,
        and inserts ``ast_import`` links.

        Parameters
        ----------
        source_relpath:
            Project-relative path to the source file.
        source_artifact_id:
            The ``artifacts.id`` of the source artifact (link source).
        """
        source_abs = self.project_root / source_relpath
        if not source_abs.is_file():
            return

        try:
            deps = extract_dependencies(source_abs, self.project_root)
        except Exception:
            logger.warning("Failed to extract dependencies from %s", source_relpath, exc_info=True)
            return

        for dep_path in deps:
            target_id = self._get_or_create_artifact(dep_path, "source")
            self._insert_link(source_artifact_id, target_id, "ast_import")

    def _process_design_wikilinks(
        self,
        design_file: DesignFile,
        design_artifact_id: int,
    ) -> None:
        """Insert ``wikilink`` links for each wikilink in the design file.

        For each wikilink name, resolves to a concept path under
        ``.lexibrary/concepts/<Name>.md``, gets or creates the concept
        artifact, and inserts a ``wikilink`` link from the design artifact.

        Parameters
        ----------
        design_file:
            The parsed ``DesignFile`` model.
        design_artifact_id:
            The ``artifacts.id`` of the design artifact (link source).
        """
        for wikilink_name in design_file.wikilinks:
            concept_path = f".lexibrary/concepts/{wikilink_name}.md"
            concept_id = self._get_or_create_artifact(concept_path, "concept", title=wikilink_name)
            self._insert_link(design_artifact_id, concept_id, "wikilink")

    def _process_design_stack_refs(
        self,
        design_file: DesignFile,
        design_artifact_id: int,
    ) -> None:
        """Insert ``design_stack_ref`` links for each Stack reference in the design file.

        For each Stack ref ID (e.g. ``ST-001``), resolves to the Stack post
        path under ``.lexibrary/stack/``, gets or creates the Stack artifact,
        and inserts a ``design_stack_ref`` link.

        Parameters
        ----------
        design_file:
            The parsed ``DesignFile`` model.
        design_artifact_id:
            The ``artifacts.id`` of the design artifact (link source).
        """
        for stack_ref in design_file.stack_refs:
            # Stack posts are stored as .lexibrary/stack/<ref>.md
            # The ref might be just "ST-001" or a full filename stem
            stack_path = f".lexibrary/stack/{stack_ref}.md"
            stack_id = self._get_or_create_artifact(stack_path, "stack", title=stack_ref)
            self._insert_link(design_artifact_id, stack_id, "design_stack_ref")

    def _process_design_file(self, design_path: Path, build_started: str) -> None:
        """Parse a design file and insert all related artifacts, links, tags, and FTS.

        This is the main entry point for processing a single design file during
        a full build.  It handles:

        1. Source artifact insertion (with hash if the source file exists)
        2. Design artifact insertion
        3. ``design_source`` link from design to source
        4. ``ast_import`` links from source to its import targets
        5. ``wikilink`` links from design to referenced concepts
        6. ``design_stack_ref`` links from design to referenced Stack posts
        7. Tags associated with the design artifact
        8. FTS row for the design artifact

        Parameters
        ----------
        design_path:
            Absolute path to the design file on disk.
        build_started:
            ISO 8601 timestamp of the current build (for ``build_log``).
        """
        start_ns = time.monotonic_ns()

        # Parse the design file
        design_file = parse_design_file(design_path)
        if design_file is None:
            error_msg = f"Failed to parse design file: {design_path}"
            logger.warning(error_msg)
            # Log the failure
            design_rel = str(design_path.relative_to(self.project_root))
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'full', ?, 'design', 'failed', ?, ?)",
                (
                    build_started,
                    design_rel,
                    (time.monotonic_ns() - start_ns) // 1_000_000,
                    error_msg,
                ),
            )
            return

        # Derive the source relative path from the design file path
        source_relpath = self._design_path_to_source_relpath(design_path)
        design_relpath = str(design_path.relative_to(self.project_root))

        # 1. Source artifact: hash the source file if it exists
        source_hash = self._compute_source_hash(source_relpath)

        # Get creation timestamp from source file if it exists
        source_abs = self.project_root / source_relpath
        created_at: str | None = None
        if source_abs.is_file():
            try:
                stat = source_abs.stat()
                created_at = datetime.fromtimestamp(stat.st_ctime, tz=UTC).isoformat()
            except OSError:
                pass

        source_id = self._get_or_create_artifact(source_relpath, "source")
        # Update source artifact with hash and title if we just created a stub
        self.conn.execute(
            "UPDATE artifacts SET title = ?, last_hash = ?, created_at = COALESCE(created_at, ?) "
            "WHERE id = ? AND (last_hash IS NULL OR title IS NULL)",
            (design_file.frontmatter.description, source_hash, created_at, source_id),
        )

        # 2. Design artifact
        design_id = self._insert_artifact(
            path=design_relpath,
            kind="design",
            title=design_file.frontmatter.description,
            status=None,
            last_hash=None,
            created_at=None,
        )

        # 3. design_source link
        self._insert_link(design_id, source_id, "design_source")

        # 4. AST import links
        self._extract_ast_imports(source_relpath, source_id)

        # 5. Wikilink links
        self._process_design_wikilinks(design_file, design_id)

        # 6. Stack ref links
        self._process_design_stack_refs(design_file, design_id)

        # 7. Tags
        for tag in design_file.tags:
            self._insert_tag(design_id, tag)

        # 8. FTS row -- body = summary + "\n" + interface_contract
        fts_body_parts = []
        if design_file.summary:
            fts_body_parts.append(design_file.summary)
        if design_file.interface_contract:
            fts_body_parts.append(design_file.interface_contract)
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(design_id, design_file.frontmatter.description, fts_body)

        # Log success
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) VALUES (?, 'full', ?, 'design', 'created', ?)",
            (build_started, design_relpath, duration_ms),
        )

    # -- Stack post processing (task group 5) ------------------------------

    def _scan_stack_posts(self) -> list[Path]:
        """Discover all ``ST-*.md`` files under ``.lexibrary/stack/``.

        Returns a sorted list of absolute ``Path`` objects for deterministic
        processing order.
        """
        stack_root = self.project_root / LEXIBRARY_DIR / "stack"
        if not stack_root.is_dir():
            return []
        return sorted(stack_root.glob("ST-*.md"))

    def _process_stack_post(self, stack_path: Path, build_started: str) -> None:
        """Parse a Stack post and insert all related artifacts, links, tags, and FTS.

        This is the main entry point for processing a single Stack post during
        a full build.  It handles:

        1. Stack artifact insertion
        2. ``stack_file_ref`` links from the Stack post to referenced source files
        3. ``stack_concept_ref`` links from the Stack post to referenced concepts
        4. Tags associated with the Stack artifact
        5. FTS row for the Stack artifact (body = problem + all answer bodies)

        Parameters
        ----------
        stack_path:
            Absolute path to the Stack post file on disk.
        build_started:
            ISO 8601 timestamp of the current build (for ``build_log``).
        """
        start_ns = time.monotonic_ns()

        # Parse the Stack post
        stack_post = parse_stack_post(stack_path)
        if stack_post is None:
            error_msg = f"Failed to parse Stack post: {stack_path}"
            logger.warning(error_msg)
            stack_rel = str(stack_path.relative_to(self.project_root))
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'full', ?, 'stack', 'failed', ?, ?)",
                (
                    build_started,
                    stack_rel,
                    (time.monotonic_ns() - start_ns) // 1_000_000,
                    error_msg,
                ),
            )
            return

        stack_relpath = str(stack_path.relative_to(self.project_root))

        # 1. Stack artifact -- use _get_or_create_artifact so that stub
        #    artifacts (created by design file stack refs) are reused rather
        #    than duplicated.
        stack_id = self._get_or_create_artifact(
            stack_relpath, "stack", title=stack_post.frontmatter.title
        )
        # Update the artifact with full details (title, status) in case
        # it was originally inserted as a stub.
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ? WHERE id = ?",
            (stack_post.frontmatter.title, stack_post.frontmatter.status, stack_id),
        )

        # 2. stack_file_ref links from Stack post to referenced source files
        for file_ref in stack_post.frontmatter.refs.files:
            target_id = self._get_or_create_artifact(file_ref, "source")
            self._insert_link(stack_id, target_id, "stack_file_ref")

        # 3. stack_concept_ref links from Stack post to referenced concepts
        for concept_ref in stack_post.frontmatter.refs.concepts:
            concept_path = f".lexibrary/concepts/{concept_ref}.md"
            target_id = self._get_or_create_artifact(concept_path, "concept", title=concept_ref)
            self._insert_link(stack_id, target_id, "stack_concept_ref")

        # 4. Tags
        for tag in stack_post.frontmatter.tags:
            self._insert_tag(stack_id, tag)

        # 5. FTS row -- body = problem + "\n" + " ".join(answer.body for answer in answers)
        fts_body_parts: list[str] = []
        if stack_post.problem:
            fts_body_parts.append(stack_post.problem)
        answer_bodies = " ".join(answer.body for answer in stack_post.answers if answer.body)
        if answer_bodies:
            fts_body_parts.append(answer_bodies)
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(stack_id, stack_post.frontmatter.title, fts_body)

        # Log success
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) VALUES (?, 'full', ?, 'stack', 'created', ?)",
            (build_started, stack_relpath, duration_ms),
        )

    # -- .aindex convention processing (task group 6) ----------------------

    def _scan_aindex_files(self) -> list[Path]:
        """Discover all ``.aindex`` files under ``.lexibrary/``.

        Returns a sorted list of absolute ``Path`` objects for deterministic
        processing order.
        """
        lex_root = self.project_root / LEXIBRARY_DIR
        if not lex_root.is_dir():
            return []
        return sorted(lex_root.rglob(".aindex"))

    def _process_aindex_conventions(self, aindex_path: Path, build_started: str) -> None:
        """Parse an ``.aindex`` file and insert convention artifacts and metadata.

        For each entry in ``AIndexFile.local_conventions``, this method:

        1. Inserts a ``kind='convention'`` artifact with a synthetic path
           using the ``{directory_path}::convention::{ordinal}`` format
        2. Inserts a row in the ``conventions`` table with ``directory_path``,
           ``ordinal``, and ``body``
        3. Extracts ``[[wikilinks]]`` from the convention text and inserts
           ``convention_concept_ref`` links
        4. Inserts an FTS row with body = full convention text

        Parameters
        ----------
        aindex_path:
            Absolute path to the ``.aindex`` file on disk.
        build_started:
            ISO 8601 timestamp of the current build (for ``build_log``).
        """
        start_ns = time.monotonic_ns()

        # Parse the .aindex file
        aindex_file = parse_aindex(aindex_path)
        if aindex_file is None:
            error_msg = f"Failed to parse .aindex file: {aindex_path}"
            logger.warning(error_msg)
            aindex_rel = str(aindex_path.relative_to(self.project_root))
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'full', ?, 'convention', 'failed', ?, ?)",
                (
                    build_started,
                    aindex_rel,
                    (time.monotonic_ns() - start_ns) // 1_000_000,
                    error_msg,
                ),
            )
            return

        if not aindex_file.local_conventions:
            return

        directory_path = aindex_file.directory_path

        for ordinal, convention_text in enumerate(aindex_file.local_conventions):
            conv_start_ns = time.monotonic_ns()

            # 1. Synthetic path for the convention artifact
            synthetic_path = f"{directory_path}::convention::{ordinal}"

            # Title: first 120 characters of the convention text
            title = convention_text[:120] if len(convention_text) > 120 else convention_text

            # Insert convention artifact
            conv_id = self._insert_artifact(
                path=synthetic_path,
                kind="convention",
                title=title,
                status=None,
                last_hash=None,
                created_at=None,
            )

            # 2. Insert conventions table row
            self.conn.execute(
                "INSERT INTO conventions (artifact_id, directory_path, ordinal, body) "
                "VALUES (?, ?, ?, ?)",
                (conv_id, directory_path, ordinal, convention_text),
            )

            # 3. Extract wikilinks and insert convention_concept_ref links
            wikilink_names = _extract_wikilinks(convention_text)
            for wikilink_name in wikilink_names:
                concept_path = f".lexibrary/concepts/{wikilink_name}.md"
                concept_id = self._get_or_create_artifact(
                    concept_path, "concept", title=wikilink_name
                )
                self._insert_link(conv_id, concept_id, "convention_concept_ref")

            # 4. FTS row -- body = full convention text
            self._insert_fts(conv_id, title, convention_text)

            # Log success for each convention
            conv_duration_ms = (time.monotonic_ns() - conv_start_ns) // 1_000_000
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms) "
                "VALUES (?, 'full', ?, 'convention', 'created', ?)",
                (build_started, synthetic_path, conv_duration_ms),
            )

    # -- full build orchestration (task group 7) ----------------------------

    def full_build(self) -> BuildResult:
        """Orchestrate a complete index build from all artifact families.

        The full build pipeline:

        1. Clean stale build log entries (>30 days old)
        2. Ensure schema (create or recreate if version mismatched)
        3. Clear all existing data rows
        4. Process all artifact types (design files, concepts, Stack posts,
           ``.aindex`` conventions).  The ``_get_or_create_artifact`` helper
           handles forward references, so artifacts are created on first
           encounter and reused thereafter -- functionally equivalent to
           the two-pass design (D3).
        5. Update ``meta`` table with build summary
        6. Return :class:`BuildResult` with timing and error information

        The main build (steps 3-5) is wrapped in a single transaction.
        On any unrecoverable failure the transaction is rolled back, leaving
        the database empty rather than partially populated.

        Per-artifact parse errors are caught, logged, and collected in the
        :attr:`BuildResult.errors` list without aborting the build.

        Returns
        -------
        BuildResult
            Summary of the build including artifact/link counts, duration,
            and any per-artifact errors encountered.
        """
        start_ns = time.monotonic_ns()
        build_started = datetime.now(UTC).isoformat()
        errors: list[str] = []

        # Step 1: Ensure schema is up-to-date (must precede build_log cleanup
        # because the table may not exist yet on a fresh database)
        ensure_schema(self.conn)

        # Step 2: Clean stale build log entries (outside main transaction)
        self._clean_stale_build_log()

        # Step 3-5: Main build wrapped in a transaction.
        # After ensure_schema commits, the first DML statement
        # (_clear_all_data) begins a new implicit transaction which stays
        # open until we explicitly commit or rollback -- giving us full
        # atomicity across the entire build.
        try:
            # Step 3: Clear all existing data (starts implicit transaction)
            self._clear_all_data()

            # Step 4: Process all artifact types.
            # The _get_or_create_artifact helper handles forward references,
            # so artifacts are created on first encounter and reused
            # thereafter -- functionally equivalent to the two-pass
            # design (D3).

            # 4a. Design files (creates source + design artifacts, links, tags, FTS)
            for design_path in self._scan_design_files():
                try:
                    self._process_design_file(design_path, build_started)
                except Exception as exc:
                    error_msg = f"Error processing design file {design_path}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

            # 4b. Concept files (creates concept artifacts, aliases, links, tags, FTS)
            for concept_path in self._scan_concept_files():
                try:
                    self._process_concept_file(concept_path, build_started)
                except Exception as exc:
                    error_msg = f"Error processing concept file {concept_path}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

            # 4c. Stack posts (creates stack artifacts, links, tags, FTS)
            for stack_path in self._scan_stack_posts():
                try:
                    self._process_stack_post(stack_path, build_started)
                except Exception as exc:
                    error_msg = f"Error processing Stack post {stack_path}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

            # 4d. .aindex conventions (creates convention artifacts, links, FTS)
            for aindex_path in self._scan_aindex_files():
                try:
                    self._process_aindex_conventions(aindex_path, build_started)
                except Exception as exc:
                    error_msg = f"Error processing .aindex file {aindex_path}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)

            # Step 5: Update meta table with build summary
            self._update_meta(build_started)

            # Commit the transaction
            self.conn.commit()

        except Exception as exc:
            # Unrecoverable failure -- roll back the entire build
            try:
                self.conn.rollback()
            except Exception:
                logger.error("Failed to rollback after build error", exc_info=True)
            error_msg = f"Full build failed, transaction rolled back: {exc}"
            logger.error(error_msg, exc_info=True)
            errors.append(error_msg)

            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            return BuildResult(
                artifact_count=0,
                link_count=0,
                duration_ms=duration_ms,
                errors=errors,
                build_type="full",
            )

        # Compute final counts and timing
        artifact_count = self.conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        link_count = self.conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        return BuildResult(
            artifact_count=artifact_count,
            link_count=link_count,
            duration_ms=duration_ms,
            errors=errors,
            build_type="full",
        )

    # -- incremental update (task group 8) ----------------------------------

    def _classify_path(self, file_path: Path) -> str:
        """Classify a file path into its artifact kind.

        Determines the artifact type from the file path:

        - Paths under ``.lexibrary/concepts/`` are concept files
        - Paths under ``.lexibrary/stack/`` are Stack posts
        - Paths ending in ``.aindex`` under ``.lexibrary/`` are aindex files
        - Paths ending in ``.md`` under ``.lexibrary/src/`` are design files
        - All other paths are treated as source files

        Parameters
        ----------
        file_path:
            The file path to classify.  May be absolute or project-relative.

        Returns
        -------
        str
            One of ``'concept'``, ``'stack'``, ``'aindex'``, ``'design'``,
            or ``'source'``.
        """
        # Normalise to a project-relative string for prefix matching
        try:
            rel = file_path.relative_to(self.project_root)
        except ValueError:
            rel = file_path

        rel_str = str(rel)
        lex_prefix = f"{LEXIBRARY_DIR}/"

        if rel_str.startswith(f"{lex_prefix}concepts/"):
            return "concept"
        if rel_str.startswith(f"{lex_prefix}stack/"):
            return "stack"
        if rel_str.startswith(lex_prefix) and rel.name == ".aindex":
            return "aindex"
        if rel_str.startswith(f"{lex_prefix}src/") and rel_str.endswith(".md"):
            return "design"
        return "source"

    def _delete_artifact_outbound(self, artifact_id: int) -> None:
        """Delete all outbound links, tags, aliases, and FTS row for an artifact.

        The artifact row itself is preserved.  This is used during incremental
        updates to clear stale data before reinserting from current file content.

        Parameters
        ----------
        artifact_id:
            The ``artifacts.id`` whose outbound data should be deleted.
        """
        # Delete outbound links (where this artifact is the source)
        self.conn.execute(
            "DELETE FROM links WHERE source_id = ?",
            (artifact_id,),
        )
        # Delete tags
        self.conn.execute(
            "DELETE FROM tags WHERE artifact_id = ?",
            (artifact_id,),
        )
        # Delete aliases
        self.conn.execute(
            "DELETE FROM aliases WHERE artifact_id = ?",
            (artifact_id,),
        )
        # Delete FTS row
        self.conn.execute(
            "DELETE FROM artifacts_fts WHERE rowid = ?",
            (artifact_id,),
        )

    def _handle_deleted_file(self, file_path: Path, build_started: str) -> None:
        """Handle a file that has been deleted from disk.

        Deletes the corresponding artifact row.  SQLite ``ON DELETE CASCADE``
        automatically cleans up all related links, tags, aliases, conventions,
        and the FTS row.

        Parameters
        ----------
        file_path:
            The (now-deleted) file path.  May be absolute or project-relative.
        build_started:
            ISO 8601 timestamp of the current incremental build.
        """
        start_ns = time.monotonic_ns()

        try:
            rel = file_path.relative_to(self.project_root)
        except ValueError:
            rel = file_path

        rel_str = str(rel)
        kind = self._classify_path(file_path)

        # Look up the artifact
        artifact_id = self._get_artifact_id(rel_str)
        if artifact_id is not None:
            # Delete the FTS row explicitly (FTS5 standalone tables are not
            # covered by CASCADE from the artifacts table)
            self.conn.execute(
                "DELETE FROM artifacts_fts WHERE rowid = ?",
                (artifact_id,),
            )
            # Delete the artifact row -- CASCADE handles links, tags, aliases, conventions
            self.conn.execute(
                "DELETE FROM artifacts WHERE id = ?",
                (artifact_id,),
            )

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) "
            "VALUES (?, 'incremental', ?, ?, 'deleted', ?)",
            (build_started, rel_str, kind, duration_ms),
        )

    def _handle_changed_source(self, file_path: Path, build_started: str) -> None:
        """Handle a changed source file during incremental update.

        Re-reads the source file and its design file (if one exists), deletes
        outbound data, and reinserts links/tags/FTS.

        Parameters
        ----------
        file_path:
            Absolute path to the changed source file.
        build_started:
            ISO 8601 timestamp of the current incremental build.
        """
        start_ns = time.monotonic_ns()

        try:
            rel = file_path.relative_to(self.project_root)
        except ValueError:
            rel = file_path

        source_relpath = str(rel)

        # Get or create the source artifact
        source_id = self._get_or_create_artifact(source_relpath, "source")

        # Delete outbound data for the source artifact
        self._delete_artifact_outbound(source_id)

        # Re-compute hash
        source_hash = self._compute_source_hash(source_relpath)
        self.conn.execute(
            "UPDATE artifacts SET last_hash = ? WHERE id = ?",
            (source_hash, source_id),
        )

        # Re-extract AST imports
        self._extract_ast_imports(source_relpath, source_id)

        # If a design file exists for this source, re-process it to pick up
        # wikilinks, tags, stack refs, and FTS from the design perspective.
        # The design file path follows the mirror convention.
        design_abs = self.project_root / LEXIBRARY_DIR / f"{source_relpath}.md"
        if design_abs.is_file():
            design_relpath = str(design_abs.relative_to(self.project_root))
            design_id = self._get_artifact_id(design_relpath)

            if design_id is not None:
                self._delete_artifact_outbound(design_id)

                design_file = parse_design_file(design_abs)
                if design_file is not None:
                    # Re-insert design_source link
                    self._insert_link(design_id, source_id, "design_source")

                    # Re-insert wikilinks
                    self._process_design_wikilinks(design_file, design_id)

                    # Re-insert stack refs
                    self._process_design_stack_refs(design_file, design_id)

                    # Re-insert tags
                    for tag in design_file.tags:
                        self._insert_tag(design_id, tag)

                    # Re-insert FTS
                    fts_body_parts = []
                    if design_file.summary:
                        fts_body_parts.append(design_file.summary)
                    if design_file.interface_contract:
                        fts_body_parts.append(design_file.interface_contract)
                    fts_body = "\n".join(fts_body_parts)
                    self._insert_fts(design_id, design_file.frontmatter.description, fts_body)

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) "
            "VALUES (?, 'incremental', ?, 'source', 'updated', ?)",
            (build_started, source_relpath, duration_ms),
        )

    def _handle_changed_concept(self, file_path: Path, build_started: str) -> None:
        """Handle a changed concept file during incremental update.

        Re-parses the concept file, deletes outbound data, and reinserts
        aliases, links, tags, and FTS.

        Parameters
        ----------
        file_path:
            Absolute path to the changed concept file.
        build_started:
            ISO 8601 timestamp of the current incremental build.
        """
        start_ns = time.monotonic_ns()

        try:
            rel = file_path.relative_to(self.project_root)
        except ValueError:
            rel = file_path

        concept_relpath = str(rel)

        # Parse the concept file
        concept_file = parse_concept_file(file_path)
        if concept_file is None:
            error_msg = f"Failed to parse concept file: {file_path}"
            logger.warning(error_msg)
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'incremental', ?, 'concept', 'failed', ?, ?)",
                (build_started, concept_relpath, duration_ms, error_msg),
            )
            raise ValueError(error_msg)

        # Get or create the concept artifact
        concept_id = self._get_or_create_artifact(
            concept_relpath, "concept", title=concept_file.frontmatter.title
        )

        # Delete outbound data
        self._delete_artifact_outbound(concept_id)

        # Update artifact with full details
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ? WHERE id = ?",
            (concept_file.frontmatter.title, concept_file.frontmatter.status, concept_id),
        )

        # Re-insert aliases
        for alias in concept_file.frontmatter.aliases:
            self._insert_alias(concept_id, alias, concept_relpath)

        # Re-insert wikilinks from concept body
        wikilink_names = _extract_wikilinks(concept_file.body)
        for wikilink_name in wikilink_names:
            target_concept_path = f".lexibrary/concepts/{wikilink_name}.md"
            target_id = self._get_or_create_artifact(
                target_concept_path, "concept", title=wikilink_name
            )
            self._insert_link(concept_id, target_id, "wikilink")

        # Re-insert concept_file_ref links
        for file_ref in concept_file.linked_files:
            target_id = self._get_or_create_artifact(file_ref, "source")
            self._insert_link(concept_id, target_id, "concept_file_ref")

        # Re-insert tags
        for tag in concept_file.frontmatter.tags:
            self._insert_tag(concept_id, tag)

        # Re-insert FTS row
        fts_body_parts = []
        if concept_file.summary:
            fts_body_parts.append(concept_file.summary)
        if concept_file.body:
            fts_body_parts.append(concept_file.body)
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(concept_id, concept_file.frontmatter.title, fts_body)

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) "
            "VALUES (?, 'incremental', ?, 'concept', 'updated', ?)",
            (build_started, concept_relpath, duration_ms),
        )

    def _handle_changed_stack(self, file_path: Path, build_started: str) -> None:
        """Handle a changed Stack post during incremental update.

        Re-parses the Stack post, deletes outbound data, and reinserts
        links, tags, and FTS.

        Parameters
        ----------
        file_path:
            Absolute path to the changed Stack post file.
        build_started:
            ISO 8601 timestamp of the current incremental build.
        """
        start_ns = time.monotonic_ns()

        try:
            rel = file_path.relative_to(self.project_root)
        except ValueError:
            rel = file_path

        stack_relpath = str(rel)

        # Parse the Stack post
        stack_post = parse_stack_post(file_path)
        if stack_post is None:
            error_msg = f"Failed to parse Stack post: {file_path}"
            logger.warning(error_msg)
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'incremental', ?, 'stack', 'failed', ?, ?)",
                (build_started, stack_relpath, duration_ms, error_msg),
            )
            raise ValueError(error_msg)

        # Get or create the Stack artifact
        stack_id = self._get_or_create_artifact(
            stack_relpath, "stack", title=stack_post.frontmatter.title
        )

        # Delete outbound data
        self._delete_artifact_outbound(stack_id)

        # Update artifact with full details
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ? WHERE id = ?",
            (stack_post.frontmatter.title, stack_post.frontmatter.status, stack_id),
        )

        # Re-insert stack_file_ref links
        for file_ref in stack_post.frontmatter.refs.files:
            target_id = self._get_or_create_artifact(file_ref, "source")
            self._insert_link(stack_id, target_id, "stack_file_ref")

        # Re-insert stack_concept_ref links
        for concept_ref in stack_post.frontmatter.refs.concepts:
            concept_path = f".lexibrary/concepts/{concept_ref}.md"
            target_id = self._get_or_create_artifact(concept_path, "concept", title=concept_ref)
            self._insert_link(stack_id, target_id, "stack_concept_ref")

        # Re-insert tags
        for tag in stack_post.frontmatter.tags:
            self._insert_tag(stack_id, tag)

        # Re-insert FTS row
        fts_body_parts: list[str] = []
        if stack_post.problem:
            fts_body_parts.append(stack_post.problem)
        answer_bodies = " ".join(answer.body for answer in stack_post.answers if answer.body)
        if answer_bodies:
            fts_body_parts.append(answer_bodies)
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(stack_id, stack_post.frontmatter.title, fts_body)

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) "
            "VALUES (?, 'incremental', ?, 'stack', 'updated', ?)",
            (build_started, stack_relpath, duration_ms),
        )

    def _handle_changed_design(self, file_path: Path, build_started: str) -> None:
        """Handle a changed design file during incremental update.

        Re-parses the design file, deletes outbound data, reinserts links,
        tags, FTS, and re-extracts AST imports for the associated source file.

        Parameters
        ----------
        file_path:
            Absolute path to the changed design file.
        build_started:
            ISO 8601 timestamp of the current incremental build.
        """
        start_ns = time.monotonic_ns()

        try:
            rel = file_path.relative_to(self.project_root)
        except ValueError:
            rel = file_path

        design_relpath = str(rel)

        # Parse the design file
        design_file = parse_design_file(file_path)
        if design_file is None:
            error_msg = f"Failed to parse design file: {file_path}"
            logger.warning(error_msg)
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'incremental', ?, 'design', 'failed', ?, ?)",
                (build_started, design_relpath, duration_ms, error_msg),
            )
            raise ValueError(error_msg)

        # Derive the source relative path from the design file path
        source_relpath = self._design_path_to_source_relpath(file_path)

        # Get or create the design artifact
        design_id = self._get_or_create_artifact(design_relpath, "design")

        # Delete outbound data for the design artifact
        self._delete_artifact_outbound(design_id)

        # Update design artifact title
        self.conn.execute(
            "UPDATE artifacts SET title = ? WHERE id = ?",
            (design_file.frontmatter.description, design_id),
        )

        # Get or create the source artifact and update its hash
        source_id = self._get_or_create_artifact(source_relpath, "source")
        source_hash = self._compute_source_hash(source_relpath)
        self.conn.execute(
            "UPDATE artifacts SET title = ?, last_hash = ? WHERE id = ?",
            (design_file.frontmatter.description, source_hash, source_id),
        )

        # Re-insert design_source link
        self._insert_link(design_id, source_id, "design_source")

        # Re-insert wikilinks
        self._process_design_wikilinks(design_file, design_id)

        # Re-insert stack refs
        self._process_design_stack_refs(design_file, design_id)

        # Re-insert tags
        for tag in design_file.tags:
            self._insert_tag(design_id, tag)

        # Re-insert FTS
        fts_body_parts = []
        if design_file.summary:
            fts_body_parts.append(design_file.summary)
        if design_file.interface_contract:
            fts_body_parts.append(design_file.interface_contract)
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(design_id, design_file.frontmatter.description, fts_body)

        # Re-extract AST imports for the associated source file
        # First delete the source's outbound links (ast_import links)
        self.conn.execute(
            "DELETE FROM links WHERE source_id = ? AND link_type = 'ast_import'",
            (source_id,),
        )
        self._extract_ast_imports(source_relpath, source_id)

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) "
            "VALUES (?, 'incremental', ?, 'design', 'updated', ?)",
            (build_started, design_relpath, duration_ms),
        )

    def _handle_changed_aindex(self, file_path: Path, build_started: str) -> None:
        """Handle a changed ``.aindex`` file during incremental update.

        Deletes all convention artifacts for the directory, re-parses the
        ``.aindex`` file, and reinserts convention artifacts, convention rows,
        links, and FTS rows.

        Parameters
        ----------
        file_path:
            Absolute path to the changed ``.aindex`` file.
        build_started:
            ISO 8601 timestamp of the current incremental build.
        """
        start_ns = time.monotonic_ns()

        try:
            rel = file_path.relative_to(self.project_root)
        except ValueError:
            rel = file_path

        aindex_relpath = str(rel)

        # Determine the directory path from the .aindex file.
        # The .aindex file is at .lexibrary/src/<dir>/.aindex
        # The directory_path in the conventions table is the source dir,
        # e.g. "src/auth".
        # We parse the aindex file to get the correct directory_path.

        # First, delete ALL convention artifacts for this directory.
        # We need to find existing convention artifacts that match the
        # directory prefix used in synthetic paths.
        # Parse the current or previous .aindex to find the directory_path.
        # If the file still exists, parse it to get directory_path.
        # If deleted, we need to derive it from the path.

        # Try to parse the .aindex file to get the directory_path
        aindex_file = None
        if file_path.is_file():
            aindex_file = parse_aindex(file_path)

        if aindex_file is not None:
            directory_path = aindex_file.directory_path
        else:
            # File was deleted or unparseable -- derive directory_path from the
            # .aindex path.  E.g. .lexibrary/src/auth/.aindex -> src/auth
            parts = rel.parts
            if parts[0] == LEXIBRARY_DIR:
                parts = parts[1:]
            # Remove the .aindex filename
            directory_path = (str(Path(*parts[:-1])) if len(parts) > 1 else "") if parts else ""

        # Delete all convention artifacts for this directory (they use synthetic
        # paths with the format "{directory_path}::convention::{ordinal}")
        existing_conv_rows = self.conn.execute(
            "SELECT a.id FROM artifacts a "
            "JOIN conventions c ON a.id = c.artifact_id "
            "WHERE c.directory_path = ?",
            (directory_path,),
        ).fetchall()

        for (conv_id,) in existing_conv_rows:
            # Delete FTS row (not covered by CASCADE from artifacts)
            self.conn.execute(
                "DELETE FROM artifacts_fts WHERE rowid = ?",
                (conv_id,),
            )
            # Delete the artifact row -- CASCADE handles conventions, links, tags
            self.conn.execute(
                "DELETE FROM artifacts WHERE id = ?",
                (conv_id,),
            )

        # If the file still exists and was parsed successfully, reinsert
        if aindex_file is not None and aindex_file.local_conventions:
            for ordinal, convention_text in enumerate(aindex_file.local_conventions):
                synthetic_path = f"{directory_path}::convention::{ordinal}"
                title = convention_text[:120] if len(convention_text) > 120 else convention_text

                conv_id = self._insert_artifact(
                    path=synthetic_path,
                    kind="convention",
                    title=title,
                    status=None,
                    last_hash=None,
                    created_at=None,
                )

                self.conn.execute(
                    "INSERT INTO conventions (artifact_id, directory_path, ordinal, body) "
                    "VALUES (?, ?, ?, ?)",
                    (conv_id, directory_path, ordinal, convention_text),
                )

                wikilink_names = _extract_wikilinks(convention_text)
                for wikilink_name in wikilink_names:
                    concept_path = f".lexibrary/concepts/{wikilink_name}.md"
                    concept_id = self._get_or_create_artifact(
                        concept_path, "concept", title=wikilink_name
                    )
                    self._insert_link(conv_id, concept_id, "convention_concept_ref")

                self._insert_fts(conv_id, title, convention_text)

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        action = "updated" if aindex_file is not None else "deleted"
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) "
            "VALUES (?, 'incremental', ?, 'convention', ?, ?)",
            (build_started, aindex_relpath, action, duration_ms),
        )

    def incremental_update(self, changed_paths: list[Path]) -> BuildResult:
        """Process only the changed files, updating the index incrementally.

        For each path in *changed_paths*, the builder:

        1. Classifies the path into an artifact kind
        2. Checks whether the file still exists on disk
        3. If deleted: removes the artifact row (CASCADE handles cleanup)
        4. If modified: deletes outbound data and reinserts from current content
        5. Updates ``meta`` table with current counts
        6. Returns a :class:`BuildResult` with ``build_type='incremental'``

        Per-file errors are caught, logged, and collected in the returned
        :attr:`BuildResult.errors` list without aborting the update.

        Parameters
        ----------
        changed_paths:
            List of file paths that have been modified or deleted since the
            last build.  Paths may be absolute or project-relative.

        Returns
        -------
        BuildResult
            Summary of the incremental update including counts, duration,
            and any per-file errors encountered.
        """
        start_ns = time.monotonic_ns()
        build_started = datetime.now(UTC).isoformat()
        errors: list[str] = []

        # Ensure schema is in place
        ensure_schema(self.conn)

        # Clean stale build log entries
        self._clean_stale_build_log()

        for file_path in changed_paths:
            # Normalise to absolute path for file existence checks
            abs_path = self.project_root / file_path if not file_path.is_absolute() else file_path

            try:
                kind = self._classify_path(file_path)

                if not abs_path.exists():
                    # File has been deleted
                    self._handle_deleted_file(file_path, build_started)
                else:
                    # File has been modified -- dispatch to the appropriate handler
                    if kind == "concept":
                        self._handle_changed_concept(abs_path, build_started)
                    elif kind == "stack":
                        self._handle_changed_stack(abs_path, build_started)
                    elif kind == "aindex":
                        self._handle_changed_aindex(abs_path, build_started)
                    elif kind == "design":
                        self._handle_changed_design(abs_path, build_started)
                    else:
                        self._handle_changed_source(abs_path, build_started)

            except Exception as exc:
                try:
                    rel = file_path.relative_to(self.project_root)
                except ValueError:
                    rel = file_path
                error_msg = f"Error processing {rel}: {exc}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        # Update meta with current counts
        self._update_meta(build_started)
        self.conn.commit()

        # Compute final counts and timing
        artifact_count = self.conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        link_count = self.conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000

        return BuildResult(
            artifact_count=artifact_count,
            link_count=link_count,
            duration_ms=duration_ms,
            errors=errors,
            build_type="incremental",
        )


# ---------------------------------------------------------------------------
# Module-level public API (task group 9)
# ---------------------------------------------------------------------------

_INDEX_DB_NAME = "index.db"
"""Filename of the SQLite index database within ``.lexibrary/``."""


def open_index(project_root: Path) -> sqlite3.Connection | None:
    """Open the link graph SQLite database with pragmas, or return ``None``.

    Opens ``.lexibrary/index.db`` under *project_root*, sets WAL mode and
    other pragmas, and returns the connection.  Returns ``None`` if the
    database file does not exist or if opening/reading it fails (e.g.,
    corruption, permission error).

    Parameters
    ----------
    project_root:
        Absolute path to the repository root.

    Returns
    -------
    sqlite3.Connection | None
        An open connection with pragmas set, or ``None`` when the database
        is missing or corrupt.
    """
    db_path = project_root / LEXIBRARY_DIR / _INDEX_DB_NAME
    if not db_path.is_file():
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        set_pragmas(conn)
        # Quick integrity check: ensure the meta table is readable
        conn.execute("SELECT 1 FROM meta LIMIT 1")
    except (sqlite3.Error, OSError) as exc:
        logger.warning("Cannot open index database %s: %s", db_path, exc)
        with contextlib.suppress(Exception):
            conn.close()
        return None

    return conn


def build_index(
    project_root: Path,
    changed_paths: list[Path] | None = None,
) -> BuildResult:
    """Build or incrementally update the link graph index.

    This is the main entry point for callers who want to build the index
    without managing the database connection themselves.

    Behaviour:

    * If *changed_paths* is ``None`` (or not provided), a **full build** is
      performed: the database is created (or opened), the schema is ensured,
      all existing data is cleared, and the entire project is re-indexed.
    * If *changed_paths* is a non-empty list, an **incremental update** is
      performed: only the specified files are reprocessed.
    * If *changed_paths* is an empty list, an incremental update is still
      called (which effectively becomes a no-op that updates meta counts).

    The database file is created at ``.lexibrary/index.db`` if it does not
    already exist.  The ``.lexibrary/`` directory must already exist.

    Parameters
    ----------
    project_root:
        Absolute path to the repository root.
    changed_paths:
        List of changed file paths for incremental update, or ``None``
        for a full build.

    Returns
    -------
    BuildResult
        Summary of the build including artifact/link counts, duration,
        and any errors encountered.
    """
    db_path = project_root / LEXIBRARY_DIR / _INDEX_DB_NAME

    # Ensure the .lexibrary directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        set_pragmas(conn)
        ensure_schema(conn)

        builder = IndexBuilder(conn, project_root)

        if changed_paths is None:
            result = builder.full_build()
        else:
            result = builder.incremental_update(changed_paths)
    except Exception as exc:
        # Ensure we close the connection on unexpected errors
        conn.close()
        raise RuntimeError(f"build_index failed: {exc}") from exc
    else:
        conn.close()

    return result
