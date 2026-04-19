"""LinkGraph index builder -- populates the SQLite index from parsed artifacts.

Reads six artifact families (design files, concept files, Stack posts,
convention files, playbook files, and ``.aindex`` files), resolves
cross-references, and writes rows into the link graph schema created by
:mod:`lexibrary.linkgraph.schema`.

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
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from lexibrary.artifacts.aindex import AIndexFile  # noqa: F401
from lexibrary.artifacts.concept import ConceptFile  # noqa: F401
from lexibrary.artifacts.convention import ConventionFile  # noqa: F401
from lexibrary.artifacts.design_file import DesignFile  # noqa: F401
from lexibrary.artifacts.design_file_parser import parse_design_file
from lexibrary.artifacts.playbook import PlaybookFile  # noqa: F401
from lexibrary.conventions.index import ConventionIndex
from lexibrary.conventions.parser import parse_convention_file
from lexibrary.errors import ErrorSummary
from lexibrary.linkgraph.schema import (
    ensure_schema,
    set_pragmas,
)
from lexibrary.playbooks.index import PlaybookIndex
from lexibrary.playbooks.parser import parse_playbook_file
from lexibrary.stack.models import StackPost  # noqa: F401
from lexibrary.stack.parser import parse_stack_post  # noqa: F401
from lexibrary.utils.hashing import hash_file
from lexibrary.utils.paths import DESIGNS_DIR, LEXIBRARY_DIR
from lexibrary.wiki.parser import parse_concept_file  # noqa: F401
from lexibrary.wiki.patterns import extract_wikilinks as _extract_wikilinks_impl

if TYPE_CHECKING:
    from lexibrary.wiki.index import ConceptIndex

logger = logging.getLogger(__name__)

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
    error_summary: ErrorSummary = field(default_factory=ErrorSummary)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Builder version identifier
# ---------------------------------------------------------------------------

_BUILDER_ID = "lexibrary-v2"
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
        self._convention_index: ConventionIndex | None = None
        self._concept_index: ConceptIndex | None = None
        self._playbook_index: PlaybookIndex | None = None

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
        artifact_code: str | None = None,
    ) -> int:
        """Insert a row into ``artifacts`` and return the new row id.

        Parameters
        ----------
        path:
            Project-relative path (or synthetic path for conventions).
        kind:
            One of ``'source'``, ``'design'``, ``'concept'``, ``'stack'``,
            ``'convention'``, ``'playbook'``.
        title:
            Human-readable title (may be ``None``).
        status:
            Artifact status (may be ``None``).
        last_hash:
            SHA-256 hash of the source file (may be ``None``).
        created_at:
            ISO 8601 creation timestamp (may be ``None``).
        artifact_code:
            Unique artifact ID code (e.g. ``'CN-001'``, ``'ST-042'``).
            May be ``None`` for artifacts that lack an ID (source files,
            stubs, or pre-migration artifacts).

        Returns
        -------
        int
            The ``id`` of the newly inserted artifact row.
        """
        cursor = self.conn.execute(
            "INSERT INTO artifacts "
            "(path, kind, title, status, last_hash, created_at, artifact_code) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (path, kind, title, status, last_hash, created_at, artifact_code),
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
        artifact_code: str | None = None,
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
        artifact_code:
            Optional artifact ID code (e.g. ``'CN-001'``).

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
            artifact_code=artifact_code,
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
            concept_relpath,
            "concept",
            title=concept_file.frontmatter.title,
            artifact_code=concept_file.frontmatter.id,
        )
        # Update the artifact with full details (title, status, artifact_code)
        # in case it was originally inserted as a stub.
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ?, artifact_code = ? WHERE id = ?",
            (
                concept_file.frontmatter.title,
                concept_file.frontmatter.status,
                concept_file.frontmatter.id,
                concept_id,
            ),
        )

        # 2. Aliases
        for alias in concept_file.frontmatter.aliases:
            self._insert_alias(concept_id, alias, concept_relpath)

        # 3. Wikilinks from concept body -> other concepts/conventions
        wikilink_names = _extract_wikilinks_impl(concept_file.body)
        for wikilink_name in wikilink_names:
            target_path, target_kind = self._resolve_wikilink_target(wikilink_name)
            target_id = self._get_or_create_artifact(target_path, target_kind, title=wikilink_name)
            self._insert_link(concept_id, target_id, "wikilink")

        # 4. concept_file_ref links from concept to referenced source files.
        # The concept parser extracts any backticked path-like token from the
        # body via regex, which picks up prose shorthand such as
        # `archivist/dependency_extractor.py` inside a sentence. Only insert
        # a source artifact when the referenced file actually exists on disk,
        # otherwise we leak phantom source rows that the curator then flags
        # as orphaned.
        for file_ref in concept_file.linked_files:
            if not (self.project_root / file_ref).is_file():
                continue
            target_id = self._get_or_create_artifact(file_ref, "source")
            self._insert_link(concept_id, target_id, "concept_file_ref")

        # 5. Tags
        for tag in concept_file.frontmatter.tags:
            self._insert_tag(concept_id, tag)

        # 6. FTS row -- body = summary + "\n" + body + aliases + tags
        fts_body_parts = []
        if concept_file.summary:
            fts_body_parts.append(concept_file.summary)
        if concept_file.body:
            fts_body_parts.append(concept_file.body)
        if concept_file.frontmatter.aliases:
            fts_body_parts.append(" ".join(concept_file.frontmatter.aliases))
        if concept_file.frontmatter.tags:
            fts_body_parts.append(" ".join(concept_file.frontmatter.tags))
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(concept_id, concept_file.frontmatter.title, fts_body)

        # Log success
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) VALUES (?, 'full', ?, 'concept', 'created', ?)",
            (build_started, concept_relpath, duration_ms),
        )

    # -- convention-aware wikilink resolution (task group 6) -----------------

    def _resolve_concept_ref(self, name: str) -> str:
        """Resolve a named concept reference to its project-relative file path.

        Used by stack post ``concepts`` refs and convention wikilinks, where
        the artifact is explicitly expected to be a concept. Resolution tries
        title/alias via ``find()`` first, then artifact ID (e.g. ``CN-020``)
        via ``find_by_id()``; a synthetic stub path is returned only if
        neither matches, so the curator still surfaces a dangling reference.
        """
        if self._concept_index is not None:
            concept = self._concept_index.find(name)
            if concept is None:
                concept = self._concept_index.find_by_id(name)
            if concept is not None and concept.file_path is not None:
                try:
                    return str(concept.file_path.relative_to(self.project_root))
                except ValueError:
                    return str(concept.file_path)
        return f".lexibrary/concepts/{name}.md"

    def _resolve_wikilink_target(self, wikilink_name: str) -> tuple[str, str]:
        """Resolve a wikilink name to an artifact path and kind.

        Checks convention titles and aliases (via ``_convention_index``)
        before falling back to concept stub creation.  This prevents
        spurious concept stubs when a wikilink actually targets a
        convention.

        Parameters
        ----------
        wikilink_name:
            The raw wikilink text (e.g. ``"Authentication"`` or ``"type-hints"``).

        Returns
        -------
        tuple[str, str]
            ``(artifact_path, artifact_kind)`` -- either a convention
            path under ``.lexibrary/conventions/`` or a concept path
            under ``.lexibrary/concepts/``.
        """
        if self._convention_index is not None:
            needle = wikilink_name.strip().lower()
            # Check convention title (exact, case-insensitive)
            for conv in self._convention_index.conventions:
                if conv.frontmatter.title.strip().lower() == needle:
                    # Use the convention's file_path if available, otherwise
                    # derive from slug
                    if conv.file_path is not None:
                        try:
                            conv_relpath = str(conv.file_path.relative_to(self.project_root))
                        except ValueError:
                            conv_relpath = str(conv.file_path)
                    else:
                        from lexibrary.artifacts.convention import convention_slug

                        slug = convention_slug(conv.frontmatter.title)
                        conv_relpath = f".lexibrary/conventions/{slug}.md"
                    return conv_relpath, "convention"

            # Check convention alias (exact, case-insensitive)
            for conv in self._convention_index.conventions:
                for alias in conv.frontmatter.aliases:
                    if alias.strip().lower() == needle:
                        if conv.file_path is not None:
                            try:
                                conv_relpath = str(conv.file_path.relative_to(self.project_root))
                            except ValueError:
                                conv_relpath = str(conv.file_path)
                        else:
                            from lexibrary.artifacts.convention import convention_slug

                            slug = convention_slug(conv.frontmatter.title)
                            conv_relpath = f".lexibrary/conventions/{slug}.md"
                        return conv_relpath, "convention"

        # Check concept titles/aliases before creating a stub path.
        # Without this, wikilinks produce phantom paths like
        # `.lexibrary/concepts/Design File.md` instead of resolving to the
        # actual file (e.g. `CN-004-design-file.md`).
        if self._concept_index is not None:
            concept = self._concept_index.find(wikilink_name)
            if concept is not None and concept.file_path is not None:
                try:
                    concept_relpath = str(concept.file_path.relative_to(self.project_root))
                except ValueError:
                    concept_relpath = str(concept.file_path)
                return concept_relpath, "concept"

        # Check playbook titles/aliases. Without this, wikilinks targeting a
        # playbook (e.g. `[[Adding a new CLI command]]`) fall through to a
        # phantom concept stub even when the playbook exists on disk.
        if self._playbook_index is not None:
            needle = wikilink_name.strip().lower()
            for pb in self._playbook_index.playbooks:
                title_match = pb.frontmatter.title.strip().lower() == needle
                alias_match = any(
                    alias.strip().lower() == needle for alias in pb.frontmatter.aliases
                )
                if (title_match or alias_match) and pb.file_path is not None:
                    try:
                        pb_relpath = str(pb.file_path.relative_to(self.project_root))
                    except ValueError:
                        pb_relpath = str(pb.file_path)
                    return pb_relpath, "playbook"

        # Fallback: treat as concept stub (no matching file on disk)
        concept_path = f".lexibrary/concepts/{wikilink_name}.md"
        return concept_path, "concept"

    # -- design file processing (task group 3) ------------------------------

    def _scan_design_files(self) -> list[Path]:
        """Discover all ``.md`` files under ``.lexibrary/designs/`` (the design file mirror tree).

        Returns a sorted list of absolute ``Path`` objects for deterministic
        processing order.
        """
        design_root = self.project_root / LEXIBRARY_DIR / DESIGNS_DIR
        if not design_root.is_dir():
            return []
        return sorted(design_root.rglob("*.md"))

    def _design_path_to_source_relpath(self, design_path: Path) -> str:
        """Convert an absolute design file path to the project-relative source path.

        ``.lexibrary/designs/src/auth/login.py.md`` -> ``src/auth/login.py``

        The design mirror tree stores ``<source_path>.md`` under
        ``.lexibrary/designs/``, so we strip the ``.lexibrary/designs/``
        prefix and the trailing ``.md`` extension.
        """
        # Make the design path relative to project_root
        rel = design_path.relative_to(self.project_root)
        # Strip leading ".lexibrary/" prefix
        # rel looks like: .lexibrary/designs/src/auth/login.py.md
        parts = rel.parts
        if parts[0] == LEXIBRARY_DIR:
            parts = parts[1:]
        # Strip leading "designs/" segment
        if parts and parts[0] == DESIGNS_DIR:
            parts = parts[1:]
        # Reconstruct without the .lexibrary/designs prefix
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

        # Lazy import to break circular dependency:
        # builder -> archivist.dependency_extractor -> archivist -> pipeline -> builder
        from lexibrary.archivist.dependency_extractor import extract_dependencies

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

        For each wikilink name, resolves via ``_resolve_wikilink_target()``
        which checks convention titles/aliases before falling back to
        concept stub creation, then inserts a ``wikilink`` link from the
        design artifact to the resolved target.

        Parameters
        ----------
        design_file:
            The parsed ``DesignFile`` model.
        design_artifact_id:
            The ``artifacts.id`` of the design artifact (link source).
        """
        for wikilink_name in design_file.wikilinks:
            target_path, target_kind = self._resolve_wikilink_target(wikilink_name)
            target_id = self._get_or_create_artifact(target_path, target_kind, title=wikilink_name)
            self._insert_link(design_artifact_id, target_id, "wikilink")

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
            artifact_code=design_file.frontmatter.id,
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

        # 8. FTS row -- body = summary + "\n" + interface_contract + tags
        fts_body_parts = []
        if design_file.summary:
            fts_body_parts.append(design_file.summary)
        if design_file.interface_contract:
            fts_body_parts.append(design_file.interface_contract)
        if design_file.tags:
            fts_body_parts.append(" ".join(design_file.tags))
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
        5. FTS row for the Stack artifact (body = problem + all finding bodies)

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
            stack_relpath,
            "stack",
            title=stack_post.frontmatter.title,
            artifact_code=stack_post.frontmatter.id,
        )
        # Update the artifact with full details (title, status, artifact_code)
        # in case it was originally inserted as a stub.
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ?, artifact_code = ? WHERE id = ?",
            (
                stack_post.frontmatter.title,
                stack_post.frontmatter.status,
                stack_post.frontmatter.id,
                stack_id,
            ),
        )

        # 2. stack_file_ref links from Stack post to referenced source files
        for file_ref in stack_post.frontmatter.refs.files:
            target_id = self._get_or_create_artifact(file_ref, "source")
            self._insert_link(stack_id, target_id, "stack_file_ref")

        # 3. stack_concept_ref links from Stack post to referenced concepts.
        # Resolve via ConceptIndex so that names like "Deprecation Lifecycle"
        # point at CN-015-deprecation-lifecycle.md rather than a stub path
        # that the curator then flags as an orphan.
        for concept_ref in stack_post.frontmatter.refs.concepts:
            concept_path = self._resolve_concept_ref(concept_ref)
            target_id = self._get_or_create_artifact(concept_path, "concept", title=concept_ref)
            self._insert_link(stack_id, target_id, "stack_concept_ref")

        # 4. Tags
        for tag in stack_post.frontmatter.tags:
            self._insert_tag(stack_id, tag)

        # 5. FTS row -- body = problem + context + attempts + findings + tags
        fts_body_parts: list[str] = []
        if stack_post.problem:
            fts_body_parts.append(stack_post.problem)
        if stack_post.context:
            fts_body_parts.append(stack_post.context)
        if stack_post.attempts:
            fts_body_parts.append(" ".join(stack_post.attempts))
        finding_bodies = " ".join(finding.body for finding in stack_post.findings if finding.body)
        if finding_bodies:
            fts_body_parts.append(finding_bodies)
        if stack_post.frontmatter.tags:
            fts_body_parts.append(" ".join(stack_post.frontmatter.tags))
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(stack_id, stack_post.frontmatter.title, fts_body)

        # Log success
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) VALUES (?, 'full', ?, 'stack', 'created', ?)",
            (build_started, stack_relpath, duration_ms),
        )

    # -- convention file processing -------------------------------------------

    def _scan_convention_files(self) -> list[Path]:
        """Discover all ``.md`` files under ``.lexibrary/conventions/``.

        Returns a sorted list of absolute ``Path`` objects for deterministic
        processing order (sorted by path ensures stable ordinal assignment
        within each scope).
        """
        conventions_root = self.project_root / LEXIBRARY_DIR / "conventions"
        if not conventions_root.is_dir():
            return []
        return sorted(conventions_root.glob("*.md"))

    def _process_convention_file(self, conv_path: Path, build_started: str) -> None:
        """Parse a convention file and insert all related artifacts, links, tags, and FTS.

        For each convention file in ``.lexibrary/conventions/``, this method:

        1. Parses the convention file via ``parse_convention_file()``
        2. Inserts a ``kind='convention'`` artifact with the convention file path
           and title from frontmatter
        3. Inserts a row in the ``conventions`` table with ``directory_path``
           (derived from scope), ``ordinal``, ``body``, ``source``, ``status``,
           and ``priority``
        4. Extracts ``[[wikilinks]]`` from the convention body and inserts
           ``convention_concept_ref`` links
        5. Inserts an FTS row with body = rule + body text
        6. Inserts tags from ``ConventionFileFrontmatter.tags``

        Parameters
        ----------
        conv_path:
            Absolute path to the convention file on disk.
        build_started:
            ISO 8601 timestamp of the current build (for ``build_log``).
        """
        start_ns = time.monotonic_ns()

        # Parse the convention file
        conv_file = parse_convention_file(conv_path)
        if conv_file is None:
            error_msg = f"Failed to parse convention file: {conv_path}"
            logger.warning(error_msg)
            conv_rel = str(conv_path.relative_to(self.project_root))
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'full', ?, 'convention', 'failed', ?, ?)",
                (
                    build_started,
                    conv_rel,
                    (time.monotonic_ns() - start_ns) // 1_000_000,
                    error_msg,
                ),
            )
            return

        conv_relpath = str(conv_path.relative_to(self.project_root))

        # Derive directory_path from scope: "project" -> ".", otherwise use
        # scope value directly (e.g. "src/auth")
        scope = conv_file.frontmatter.scope
        directory_path = "." if scope == "project" else scope

        # Compute ordinal: count existing conventions for this directory_path
        row = self.conn.execute(
            "SELECT COALESCE(MAX(ordinal), -1) FROM conventions WHERE directory_path = ?",
            (directory_path,),
        ).fetchone()
        ordinal = row[0] + 1

        # 1. Convention artifact -- use _get_or_create_artifact so that stub
        #    artifacts (created by design file wikilinks that resolved to
        #    conventions) are reused rather than duplicated.
        conv_id = self._get_or_create_artifact(
            conv_relpath,
            "convention",
            title=conv_file.frontmatter.title,
            artifact_code=conv_file.frontmatter.id,
        )
        # Update the artifact with full details (title, status, artifact_code)
        # in case it was originally inserted as a stub.
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ?, artifact_code = ? WHERE id = ?",
            (
                conv_file.frontmatter.title,
                conv_file.frontmatter.status,
                conv_file.frontmatter.id,
                conv_id,
            ),
        )

        # 2. Conventions table row with extended metadata
        self.conn.execute(
            "INSERT INTO conventions "
            "(artifact_id, directory_path, ordinal, body, source, status, priority) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                conv_id,
                directory_path,
                ordinal,
                conv_file.body,
                conv_file.frontmatter.source,
                conv_file.frontmatter.status,
                conv_file.frontmatter.priority,
            ),
        )

        # 3. Extract wikilinks and insert convention_concept_ref links.
        # Resolve through the shared wikilink resolver so the target lands on
        # the real artifact (concept, convention, or playbook) rather than a
        # synthetic concept stub that the curator then flags.
        wikilink_names = _extract_wikilinks_impl(conv_file.body)
        for wikilink_name in wikilink_names:
            target_path, target_kind = self._resolve_wikilink_target(wikilink_name)
            target_id = self._get_or_create_artifact(target_path, target_kind, title=wikilink_name)
            self._insert_link(conv_id, target_id, "convention_concept_ref")

        # 4. FTS row -- body = rule + "\n" + body + aliases + tags
        fts_body_parts = []
        if conv_file.rule:
            fts_body_parts.append(conv_file.rule)
        if conv_file.body:
            fts_body_parts.append(conv_file.body)
        if conv_file.frontmatter.aliases:
            fts_body_parts.append(" ".join(conv_file.frontmatter.aliases))
        if conv_file.frontmatter.tags:
            fts_body_parts.append(" ".join(conv_file.frontmatter.tags))
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(conv_id, conv_file.frontmatter.title, fts_body)

        # 5. Tags
        for tag in conv_file.frontmatter.tags:
            self._insert_tag(conv_id, tag)

        # 6. Aliases
        for alias in conv_file.frontmatter.aliases:
            self._insert_alias(conv_id, alias, conv_relpath)

        # Log success
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) VALUES (?, 'full', ?, 'convention', 'created', ?)",
            (build_started, conv_relpath, duration_ms),
        )

    # -- playbook file processing -----------------------------------------------

    def _scan_playbook_files(self) -> list[Path]:
        """Discover all ``.md`` files under ``.lexibrary/playbooks/``.

        Returns a sorted list of absolute ``Path`` objects for deterministic
        processing order.
        """
        playbooks_root = self.project_root / LEXIBRARY_DIR / "playbooks"
        if not playbooks_root.is_dir():
            return []
        return sorted(playbooks_root.rglob("*.md"))

    def _process_playbook_file(self, playbook_path: Path, build_started: str) -> None:
        """Parse a playbook file and insert artifact, tags, aliases, and FTS.

        This is the main entry point for processing a single playbook file
        during a full build.  It handles:

        1. Playbook artifact insertion
        2. Alias insertion (first-writer-wins on duplicates)
        3. Tags associated with the playbook artifact
        4. FTS row for the playbook artifact (includes aliases and tags)

        Parameters
        ----------
        playbook_path:
            Absolute path to the playbook file on disk.
        build_started:
            ISO 8601 timestamp of the current build (for ``build_log``).
        """
        start_ns = time.monotonic_ns()

        # Parse the playbook file
        playbook_file = parse_playbook_file(playbook_path)
        if playbook_file is None:
            error_msg = f"Failed to parse playbook file: {playbook_path}"
            logger.warning(error_msg)
            playbook_rel = str(playbook_path.relative_to(self.project_root))
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'full', ?, 'playbook', 'failed', ?, ?)",
                (
                    build_started,
                    playbook_rel,
                    (time.monotonic_ns() - start_ns) // 1_000_000,
                    error_msg,
                ),
            )
            return

        playbook_relpath = str(playbook_path.relative_to(self.project_root))

        # 1. Playbook artifact
        playbook_id = self._get_or_create_artifact(
            playbook_relpath,
            "playbook",
            title=playbook_file.frontmatter.title,
            artifact_code=playbook_file.frontmatter.id,
        )
        # Update the artifact with full details
        self.conn.execute(
            "UPDATE artifacts SET title = ?, artifact_code = ? WHERE id = ?",
            (playbook_file.frontmatter.title, playbook_file.frontmatter.id, playbook_id),
        )

        # 2. Aliases
        for alias in playbook_file.frontmatter.aliases:
            self._insert_alias(playbook_id, alias, playbook_relpath)

        # 3. Tags
        for tag in playbook_file.frontmatter.tags:
            self._insert_tag(playbook_id, tag)

        # 4. FTS row -- body = overview + body + aliases + tags
        fts_body_parts = []
        if playbook_file.overview:
            fts_body_parts.append(playbook_file.overview)
        if playbook_file.body:
            fts_body_parts.append(playbook_file.body)
        if playbook_file.frontmatter.aliases:
            fts_body_parts.append(" ".join(playbook_file.frontmatter.aliases))
        if playbook_file.frontmatter.tags:
            fts_body_parts.append(" ".join(playbook_file.frontmatter.tags))
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(playbook_id, playbook_file.frontmatter.title, fts_body)

        # Log success
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) VALUES (?, 'full', ?, 'playbook', 'created', ?)",
            (build_started, playbook_relpath, duration_ms),
        )

    # -- full build orchestration (task group 7) ----------------------------

    def full_build(self) -> BuildResult:
        """Orchestrate a complete index build from all artifact families.

        The full build pipeline:

        1. Clean stale build log entries (>30 days old)
        2. Ensure schema (create or recreate if version mismatched)
        3. Clear all existing data rows
        4. Process all artifact types (design files, concepts, Stack posts,
           convention files).  The ``_get_or_create_artifact`` helper
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
        error_summary = ErrorSummary()

        # Step 1: Ensure schema is up-to-date (must precede build_log cleanup
        # because the table may not exist yet on a fresh database)
        ensure_schema(self.conn)

        # Step 2: Clean stale build log entries (outside main transaction)
        self._clean_stale_build_log()

        # Step 2b: Load ConventionIndex for convention-aware wikilink resolution.
        # Loaded once per build so that _resolve_wikilink_target() can check
        # convention titles/aliases before falling back to concept stub creation.
        conventions_dir = self.project_root / LEXIBRARY_DIR / "conventions"
        if conventions_dir.is_dir():
            self._convention_index = ConventionIndex(conventions_dir)
            self._convention_index.load()
        else:
            self._convention_index = None

        # Step 2c: Load ConceptIndex for concept-aware wikilink resolution.
        # Without this, wikilinks like [[Design File]] create phantom stubs at
        # `.lexibrary/concepts/Design File.md` instead of resolving to the
        # actual concept file (e.g. `CN-004-design-file.md`).
        from lexibrary.wiki.index import ConceptIndex as _ConceptIndex  # noqa: PLC0415

        concepts_dir = self.project_root / LEXIBRARY_DIR / "concepts"
        if concepts_dir.is_dir():
            self._concept_index = _ConceptIndex.load(concepts_dir)
        else:
            self._concept_index = None

        # Step 2d: Load PlaybookIndex so wikilinks naming a playbook resolve to
        # the actual playbook file instead of falling through to a phantom
        # concept stub (e.g. `[[Adding a new CLI command]]` → the playbook,
        # not `.lexibrary/concepts/Adding a new CLI command.md`).
        playbooks_dir = self.project_root / LEXIBRARY_DIR / "playbooks"
        if playbooks_dir.is_dir():
            self._playbook_index = PlaybookIndex(playbooks_dir)
            self._playbook_index.load()
        else:
            self._playbook_index = None

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
                    error_summary.add("linkgraph", exc, path=str(design_path))

            # 4b. Concept files (creates concept artifacts, aliases, links, tags, FTS)
            for concept_path in self._scan_concept_files():
                try:
                    self._process_concept_file(concept_path, build_started)
                except Exception as exc:
                    error_msg = f"Error processing concept file {concept_path}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    error_summary.add("linkgraph", exc, path=str(concept_path))

            # 4c. Stack posts (creates stack artifacts, links, tags, FTS)
            for stack_path in self._scan_stack_posts():
                try:
                    self._process_stack_post(stack_path, build_started)
                except Exception as exc:
                    error_msg = f"Error processing Stack post {stack_path}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    error_summary.add("linkgraph", exc, path=str(stack_path))

            # 4d. Convention files (creates convention artifacts, links, tags, FTS)
            for conv_path in self._scan_convention_files():
                try:
                    self._process_convention_file(conv_path, build_started)
                except Exception as exc:
                    error_msg = f"Error processing convention file {conv_path}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    error_summary.add("linkgraph", exc, path=str(conv_path))

            # 4e. Playbook files (creates playbook artifacts, aliases, tags, FTS)
            for playbook_path in self._scan_playbook_files():
                try:
                    self._process_playbook_file(playbook_path, build_started)
                except Exception as exc:
                    error_msg = f"Error processing playbook file {playbook_path}: {exc}"
                    logger.error(error_msg, exc_info=True)
                    errors.append(error_msg)
                    error_summary.add("linkgraph", exc, path=str(playbook_path))

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
            error_summary.add("linkgraph", exc)

            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            return BuildResult(
                artifact_count=0,
                link_count=0,
                duration_ms=duration_ms,
                errors=errors,
                build_type="full",
                error_summary=error_summary,
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
            error_summary=error_summary,
        )

    # -- incremental update (task group 8) ----------------------------------

    def _classify_path(self, file_path: Path) -> str:
        """Classify a file path into its artifact kind.

        Determines the artifact type from the file path:

        - Paths under ``.lexibrary/concepts/`` are concept files
        - Paths under ``.lexibrary/stack/`` are Stack posts
        - Paths under ``.lexibrary/conventions/`` are convention files
        - Paths under ``.lexibrary/playbooks/`` are playbook files
        - Paths ending in ``.aindex`` under ``.lexibrary/`` are aindex files
        - Paths ending in ``.md`` under ``.lexibrary/designs/`` are design files
        - All other paths are treated as source files

        Parameters
        ----------
        file_path:
            The file path to classify.  May be absolute or project-relative.

        Returns
        -------
        str
            One of ``'concept'``, ``'stack'``, ``'convention'``, ``'playbook'``,
            ``'aindex'``, ``'design'``, or ``'source'``.
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
        if rel_str.startswith(f"{lex_prefix}conventions/"):
            return "convention"
        if rel_str.startswith(f"{lex_prefix}playbooks/"):
            return "playbook"
        if rel_str.startswith(lex_prefix) and rel.name == ".aindex":
            return "aindex"
        if rel_str.startswith(f"{lex_prefix}{DESIGNS_DIR}/") and rel_str.endswith(".md"):
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

                    # Re-insert FTS (includes tags)
                    fts_body_parts = []
                    if design_file.summary:
                        fts_body_parts.append(design_file.summary)
                    if design_file.interface_contract:
                        fts_body_parts.append(design_file.interface_contract)
                    if design_file.tags:
                        fts_body_parts.append(" ".join(design_file.tags))
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
            concept_relpath,
            "concept",
            title=concept_file.frontmatter.title,
            artifact_code=concept_file.frontmatter.id,
        )

        # Delete outbound data
        self._delete_artifact_outbound(concept_id)

        # Update artifact with full details
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ?, artifact_code = ? WHERE id = ?",
            (
                concept_file.frontmatter.title,
                concept_file.frontmatter.status,
                concept_file.frontmatter.id,
                concept_id,
            ),
        )

        # Re-insert aliases
        for alias in concept_file.frontmatter.aliases:
            self._insert_alias(concept_id, alias, concept_relpath)

        # Re-insert wikilinks from concept body
        wikilink_names = _extract_wikilinks_impl(concept_file.body)
        for wikilink_name in wikilink_names:
            target_path, target_kind = self._resolve_wikilink_target(wikilink_name)
            target_id = self._get_or_create_artifact(target_path, target_kind, title=wikilink_name)
            self._insert_link(concept_id, target_id, "wikilink")

        # Re-insert concept_file_ref links. See _process_concept_file for
        # why we gate on real files — the parser's regex picks up prose
        # shorthand that would otherwise leak phantom source rows.
        for file_ref in concept_file.linked_files:
            if not (self.project_root / file_ref).is_file():
                continue
            target_id = self._get_or_create_artifact(file_ref, "source")
            self._insert_link(concept_id, target_id, "concept_file_ref")

        # Re-insert tags
        for tag in concept_file.frontmatter.tags:
            self._insert_tag(concept_id, tag)

        # Re-insert FTS row (includes aliases and tags)
        fts_body_parts = []
        if concept_file.summary:
            fts_body_parts.append(concept_file.summary)
        if concept_file.body:
            fts_body_parts.append(concept_file.body)
        if concept_file.frontmatter.aliases:
            fts_body_parts.append(" ".join(concept_file.frontmatter.aliases))
        if concept_file.frontmatter.tags:
            fts_body_parts.append(" ".join(concept_file.frontmatter.tags))
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
            stack_relpath,
            "stack",
            title=stack_post.frontmatter.title,
            artifact_code=stack_post.frontmatter.id,
        )

        # Delete outbound data
        self._delete_artifact_outbound(stack_id)

        # Update artifact with full details
        self.conn.execute(
            "UPDATE artifacts SET title = ?, status = ?, artifact_code = ? WHERE id = ?",
            (
                stack_post.frontmatter.title,
                stack_post.frontmatter.status,
                stack_post.frontmatter.id,
                stack_id,
            ),
        )

        # Re-insert stack_file_ref links
        for file_ref in stack_post.frontmatter.refs.files:
            target_id = self._get_or_create_artifact(file_ref, "source")
            self._insert_link(stack_id, target_id, "stack_file_ref")

        # Re-insert stack_concept_ref links. See _process_stack_post for
        # why we resolve through ConceptIndex.
        for concept_ref in stack_post.frontmatter.refs.concepts:
            concept_path = self._resolve_concept_ref(concept_ref)
            target_id = self._get_or_create_artifact(concept_path, "concept", title=concept_ref)
            self._insert_link(stack_id, target_id, "stack_concept_ref")

        # Re-insert tags
        for tag in stack_post.frontmatter.tags:
            self._insert_tag(stack_id, tag)

        # Re-insert FTS row (includes tags)
        fts_body_parts: list[str] = []
        if stack_post.problem:
            fts_body_parts.append(stack_post.problem)
        if stack_post.context:
            fts_body_parts.append(stack_post.context)
        if stack_post.attempts:
            fts_body_parts.append(" ".join(stack_post.attempts))
        finding_bodies = " ".join(finding.body for finding in stack_post.findings if finding.body)
        if finding_bodies:
            fts_body_parts.append(finding_bodies)
        if stack_post.frontmatter.tags:
            fts_body_parts.append(" ".join(stack_post.frontmatter.tags))
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
        design_id = self._get_or_create_artifact(
            design_relpath,
            "design",
            artifact_code=design_file.frontmatter.id,
        )

        # Delete outbound data for the design artifact
        self._delete_artifact_outbound(design_id)

        # Update design artifact title and artifact_code
        self.conn.execute(
            "UPDATE artifacts SET title = ?, artifact_code = ? WHERE id = ?",
            (design_file.frontmatter.description, design_file.frontmatter.id, design_id),
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

        # Re-insert FTS (includes tags)
        fts_body_parts = []
        if design_file.summary:
            fts_body_parts.append(design_file.summary)
        if design_file.interface_contract:
            fts_body_parts.append(design_file.interface_contract)
        if design_file.tags:
            fts_body_parts.append(" ".join(design_file.tags))
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

    def _handle_changed_convention(self, file_path: Path, build_started: str) -> None:
        """Handle a changed convention file during incremental update.

        Re-parses the convention file, deletes the existing convention artifact
        and its outbound data, and reinserts the artifact, convention row,
        links, tags, and FTS.

        Parameters
        ----------
        file_path:
            Absolute path to the changed convention file.
        build_started:
            ISO 8601 timestamp of the current incremental build.
        """
        start_ns = time.monotonic_ns()

        try:
            rel = file_path.relative_to(self.project_root)
        except ValueError:
            rel = file_path

        conv_relpath = str(rel)

        # Parse the convention file
        conv_file = parse_convention_file(file_path)
        if conv_file is None:
            error_msg = f"Failed to parse convention file: {file_path}"
            logger.warning(error_msg)
            duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
            self.conn.execute(
                "INSERT INTO build_log (build_started, build_type, artifact_path, "
                "artifact_kind, action, duration_ms, error_message) "
                "VALUES (?, 'incremental', ?, 'convention', 'failed', ?, ?)",
                (build_started, conv_relpath, duration_ms, error_msg),
            )
            raise ValueError(error_msg)

        # Derive directory_path from scope
        scope = conv_file.frontmatter.scope
        directory_path = "." if scope == "project" else scope

        # Delete existing convention artifact if it exists
        existing_id = self._get_artifact_id(conv_relpath)
        if existing_id is not None:
            # Delete the convention row for this artifact
            self.conn.execute(
                "DELETE FROM conventions WHERE artifact_id = ?",
                (existing_id,),
            )
            # Delete outbound data (links, tags, aliases, FTS)
            self._delete_artifact_outbound(existing_id)
            # Update the existing artifact row
            self.conn.execute(
                "UPDATE artifacts SET title = ?, status = ?, artifact_code = ? WHERE id = ?",
                (
                    conv_file.frontmatter.title,
                    conv_file.frontmatter.status,
                    conv_file.frontmatter.id,
                    existing_id,
                ),
            )
            conv_id = existing_id
        else:
            # Insert new convention artifact
            conv_id = self._insert_artifact(
                path=conv_relpath,
                kind="convention",
                title=conv_file.frontmatter.title,
                status=conv_file.frontmatter.status,
                last_hash=None,
                created_at=None,
                artifact_code=conv_file.frontmatter.id,
            )

        # Compute ordinal: count existing conventions for this directory_path
        # (excluding the one we just deleted/updated)
        row = self.conn.execute(
            "SELECT COALESCE(MAX(ordinal), -1) FROM conventions WHERE directory_path = ?",
            (directory_path,),
        ).fetchone()
        ordinal = row[0] + 1

        # Insert conventions table row with extended metadata
        self.conn.execute(
            "INSERT INTO conventions "
            "(artifact_id, directory_path, ordinal, body, source, status, priority) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                conv_id,
                directory_path,
                ordinal,
                conv_file.body,
                conv_file.frontmatter.source,
                conv_file.frontmatter.status,
                conv_file.frontmatter.priority,
            ),
        )

        # Extract wikilinks and insert convention_concept_ref links.
        # See _process_convention_file for why we use the shared resolver.
        wikilink_names = _extract_wikilinks_impl(conv_file.body)
        for wikilink_name in wikilink_names:
            target_path, target_kind = self._resolve_wikilink_target(wikilink_name)
            target_id = self._get_or_create_artifact(target_path, target_kind, title=wikilink_name)
            self._insert_link(conv_id, target_id, "convention_concept_ref")

        # FTS row (includes aliases and tags)
        fts_body_parts = []
        if conv_file.rule:
            fts_body_parts.append(conv_file.rule)
        if conv_file.body:
            fts_body_parts.append(conv_file.body)
        if conv_file.frontmatter.aliases:
            fts_body_parts.append(" ".join(conv_file.frontmatter.aliases))
        if conv_file.frontmatter.tags:
            fts_body_parts.append(" ".join(conv_file.frontmatter.tags))
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(conv_id, conv_file.frontmatter.title, fts_body)

        # Tags
        for tag in conv_file.frontmatter.tags:
            self._insert_tag(conv_id, tag)

        # Re-insert aliases
        for alias in conv_file.frontmatter.aliases:
            self._insert_alias(conv_id, alias, conv_relpath)

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) "
            "VALUES (?, 'incremental', ?, 'convention', 'updated', ?)",
            (build_started, conv_relpath, duration_ms),
        )

    def _handle_changed_playbook(self, file_path: Path, build_started: str) -> None:
        """Handle a changed playbook file during incremental update.

        Re-parses the playbook file, deletes outbound data, and reinserts
        aliases, tags, and FTS.

        Parameters
        ----------
        file_path:
            Absolute path to the playbook file.
        build_started:
            ISO 8601 timestamp of the current build (for ``build_log``).
        """
        start_ns = time.monotonic_ns()

        playbook_file = parse_playbook_file(file_path)
        if playbook_file is None:
            error_msg = f"Failed to parse playbook file: {file_path}"
            logger.warning(error_msg)
            return

        playbook_relpath = str(file_path.relative_to(self.project_root))

        # Get or create the artifact (may already exist from a prior build)
        playbook_id = self._get_or_create_artifact(
            playbook_relpath,
            "playbook",
            title=playbook_file.frontmatter.title,
            artifact_code=playbook_file.frontmatter.id,
        )
        # Update the artifact with current details
        self.conn.execute(
            "UPDATE artifacts SET title = ?, artifact_code = ? WHERE id = ?",
            (playbook_file.frontmatter.title, playbook_file.frontmatter.id, playbook_id),
        )

        # Delete existing outbound data and reinsert from current content
        self._delete_artifact_outbound(playbook_id)

        # Re-insert aliases
        for alias in playbook_file.frontmatter.aliases:
            self._insert_alias(playbook_id, alias, playbook_relpath)

        # Re-insert tags
        for tag in playbook_file.frontmatter.tags:
            self._insert_tag(playbook_id, tag)

        # Re-insert FTS row (includes aliases and tags)
        fts_body_parts: list[str] = []
        if playbook_file.overview:
            fts_body_parts.append(playbook_file.overview)
        if playbook_file.body:
            fts_body_parts.append(playbook_file.body)
        if playbook_file.frontmatter.aliases:
            fts_body_parts.append(" ".join(playbook_file.frontmatter.aliases))
        if playbook_file.frontmatter.tags:
            fts_body_parts.append(" ".join(playbook_file.frontmatter.tags))
        fts_body = "\n".join(fts_body_parts)
        self._insert_fts(playbook_id, playbook_file.frontmatter.title, fts_body)

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        self.conn.execute(
            "INSERT INTO build_log (build_started, build_type, artifact_path, "
            "artifact_kind, action, duration_ms) "
            "VALUES (?, 'incremental', ?, 'playbook', 'updated', ?)",
            (build_started, playbook_relpath, duration_ms),
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
        error_summary = ErrorSummary()

        # Ensure schema is in place
        ensure_schema(self.conn)

        # Clean stale build log entries
        self._clean_stale_build_log()

        # Load ConventionIndex for convention-aware wikilink resolution
        conventions_dir = self.project_root / LEXIBRARY_DIR / "conventions"
        if conventions_dir.is_dir():
            self._convention_index = ConventionIndex(conventions_dir)
            self._convention_index.load()
        else:
            self._convention_index = None

        # Load ConceptIndex for concept-aware wikilink resolution
        from lexibrary.wiki.index import ConceptIndex as _ConceptIndex  # noqa: PLC0415

        concepts_dir = self.project_root / LEXIBRARY_DIR / "concepts"
        if concepts_dir.is_dir():
            self._concept_index = _ConceptIndex.load(concepts_dir)
        else:
            self._concept_index = None

        # Load PlaybookIndex so wikilinks naming a playbook resolve to the
        # actual playbook file instead of falling through to a phantom
        # concept stub.
        playbooks_dir = self.project_root / LEXIBRARY_DIR / "playbooks"
        if playbooks_dir.is_dir():
            self._playbook_index = PlaybookIndex(playbooks_dir)
            self._playbook_index.load()
        else:
            self._playbook_index = None

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
                    elif kind == "convention":
                        self._handle_changed_convention(abs_path, build_started)
                    elif kind == "playbook":
                        self._handle_changed_playbook(abs_path, build_started)
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
                error_summary.add("linkgraph", exc, path=str(rel))

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
            error_summary=error_summary,
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
