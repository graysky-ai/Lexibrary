"""Consistency Checker sub-agent for the curator pipeline.

Performs read-only analysis on design files and library artifacts,
returning structured fix instructions for the coordinator to execute.
Uses WikilinkResolver for wikilink validation and the link graph
for dependency and orphan detection.

All mutations (file writes, deletes) are handled by the coordinator
based on the instructions returned here -- this module never writes
to disk.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
)
from lexibrary.wiki.patterns import extract_wikilinks
from lexibrary.wiki.resolver import UnresolvedLink, WikilinkResolver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fix instruction types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FixInstruction:
    """A single structured fix instruction returned by the checker."""

    action: str
    target_path: Path
    detail: str
    risk: Literal["low", "medium"] = "low"


@dataclass
class ConsistencyReport:
    """Aggregated output from a consistency check pass."""

    instructions: list[FixInstruction] = field(default_factory=list)
    suggestions: list[FixInstruction] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Consistency Checker
# ---------------------------------------------------------------------------


class ConsistencyChecker:
    """Read-only analyzer that returns structured fix instructions.

    The checker uses :class:`WikilinkResolver` for wikilink validation
    and the link graph (when available) for dependency and orphan queries.
    It never writes to disk -- all mutations are expressed as
    :class:`FixInstruction` objects for the coordinator to execute.
    """

    def __init__(
        self,
        project_root: Path,
        lexibrary_dir: Path,
        resolver: WikilinkResolver | None = None,
    ) -> None:
        self.project_root = project_root
        self.lexibrary_dir = lexibrary_dir
        self.designs_dir = lexibrary_dir / "designs"
        self._resolver = resolver

    # -- Wikilink hygiene ---------------------------------------------------

    def check_wikilinks(self, design_path: Path) -> list[FixInstruction]:
        """Analyze wikilinks in a design file and return fix instructions.

        - Broken wikilinks (no resolution) -> strip instruction
        - Fuzzy matches -> fix instruction with suggestion
        - Valid wikilinks -> no instruction (untouched)
        """
        if self._resolver is None:
            return []

        design = parse_design_file(design_path)
        if design is None:
            return []

        instructions: list[FixInstruction] = []

        for wikilink in design.wikilinks:
            result = self._resolver.resolve(f"[[{wikilink}]]")
            if isinstance(result, UnresolvedLink):
                if result.suggestions:
                    # Fuzzy match -- suggest fix
                    instructions.append(
                        FixInstruction(
                            action="fix_broken_wikilink_fuzzy",
                            target_path=design_path,
                            detail=(
                                f"Wikilink [[{wikilink}]] unresolved; "
                                f"suggestions: {', '.join(result.suggestions)}"
                            ),
                            risk="low",
                        )
                    )
                else:
                    # No match at all -- strip
                    instructions.append(
                        FixInstruction(
                            action="strip_unresolved_wikilink",
                            target_path=design_path,
                            detail=f"Wikilink [[{wikilink}]] cannot be resolved; strip it",
                            risk="low",
                        )
                    )
            # ResolvedLink -> valid, no instruction needed

        return instructions

    def detect_domain_terms(
        self,
        design_files: list[Path],
        threshold: int = 3,
    ) -> list[FixInstruction]:
        """Detect domain terms appearing in multiple design files without concepts.

        Scans all design files for terms that appear as potential wikilinks
        in the body text (inside ``[[...]]``) but are unresolved, counting
        occurrences across files.  Terms appearing in *threshold* or more
        files are surfaced as Medium-risk suggestions.
        """
        if self._resolver is None:
            return []

        term_counts: dict[str, set[Path]] = {}

        for path in design_files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue

            wikilinks = extract_wikilinks(text)
            for wl in wikilinks:
                result = self._resolver.resolve(f"[[{wl}]]")
                if isinstance(result, UnresolvedLink):
                    key = wl.lower().strip()
                    if key not in term_counts:
                        term_counts[key] = set()
                    term_counts[key].add(path)

        suggestions: list[FixInstruction] = []
        for term, paths in sorted(term_counts.items()):
            if len(paths) >= threshold:
                suggestions.append(
                    FixInstruction(
                        action="suggest_new_concept",
                        target_path=next(iter(paths)),
                        detail=(
                            f"Domain term '{term}' appears in {len(paths)} design files "
                            f"without a matching concept; consider creating one"
                        ),
                        risk="medium",
                    )
                )

        return suggestions

    # -- Identifier normalisation -------------------------------------------

    def detect_slug_collisions(
        self,
        artifact_paths: list[Path],
    ) -> list[FixInstruction]:
        """Detect artifacts that produce the same filesystem slug.

        Scans frontmatter for titles, computes slugs, and flags
        collisions for deterministic suffix resolution.
        """
        from lexibrary.artifacts.slugs import slugify  # noqa: PLC0415

        slug_map: dict[str, list[tuple[str, Path]]] = {}
        for path in artifact_paths:
            fm = parse_design_file_frontmatter(path)
            if fm is None:
                continue
            slug = slugify(fm.description[:60])
            if slug not in slug_map:
                slug_map[slug] = []
            slug_map[slug].append((fm.id, path))

        instructions: list[FixInstruction] = []
        for slug, entries in slug_map.items():
            if len(entries) > 1:
                ids = [e[0] for e in entries]
                for _, path in entries:
                    instructions.append(
                        FixInstruction(
                            action="resolve_slug_collision",
                            target_path=path,
                            detail=f"Slug '{slug}' collides with artifacts: {', '.join(ids)}",
                            risk="low",
                        )
                    )

        return instructions

    def detect_alias_collisions(
        self,
        concepts_dir: Path,
        conventions_dir: Path,
    ) -> list[FixInstruction]:
        """Detect alias collisions across concepts and conventions.

        Two artifacts sharing an alias (case-insensitive) receive a
        deduplication instruction.
        """
        alias_map: dict[str, list[tuple[str, Path]]] = {}

        # Concepts
        if concepts_dir.is_dir():
            for path in sorted(concepts_dir.glob("*.md")):
                self._collect_aliases(path, alias_map, kind="concept")

        # Conventions
        if conventions_dir.is_dir():
            for path in sorted(conventions_dir.glob("*.md")):
                self._collect_aliases(path, alias_map, kind="convention")

        instructions: list[FixInstruction] = []
        for alias_lower, entries in alias_map.items():
            if len(entries) > 1:
                ids = [e[0] for e in entries]
                for _, path in entries:
                    instructions.append(
                        FixInstruction(
                            action="resolve_alias_collision",
                            target_path=path,
                            detail=(
                                f"Alias '{alias_lower}' shared by: {', '.join(ids)}; "
                                f"apply deterministic deduplication"
                            ),
                            risk="low",
                        )
                    )

        return instructions

    def _collect_aliases(
        self,
        path: Path,
        alias_map: dict[str, list[tuple[str, Path]]],
        kind: str,
    ) -> None:
        """Parse frontmatter aliases from a concept or convention file."""
        import yaml  # noqa: PLC0415

        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return
        # Quick frontmatter extraction
        if not text.startswith("---\n"):
            return
        end = text.find("\n---\n", 4)
        if end < 0:
            return
        try:
            data = yaml.safe_load(text[4:end])
        except Exception:
            return
        if not isinstance(data, dict):
            return

        artifact_id = data.get("id", path.stem)
        aliases = data.get("aliases", [])
        if not isinstance(aliases, list):
            return

        for alias in aliases:
            if isinstance(alias, str) and alias.strip():
                key = alias.strip().lower()
                if key not in alias_map:
                    alias_map[key] = []
                alias_map[key].append((f"{kind}:{artifact_id}", path))

    # -- Orphaned .aindex cleanup ------------------------------------------

    def detect_orphaned_aindex(self) -> list[FixInstruction]:
        """Detect .aindex files whose source directory no longer exists.

        Walks ``.lexibrary/designs/`` looking for ``.aindex`` files and
        checks whether the corresponding source directory exists under
        project_root.
        """
        if not self.designs_dir.is_dir():
            return []

        instructions: list[FixInstruction] = []
        for aindex_path in sorted(self.designs_dir.rglob(".aindex")):
            # The .aindex file's parent directory mirrors the source directory
            try:
                rel = aindex_path.parent.relative_to(self.designs_dir)
            except ValueError:
                continue

            source_dir = self.project_root / rel
            if not source_dir.is_dir():
                instructions.append(
                    FixInstruction(
                        action="remove_orphaned_aindex",
                        target_path=aindex_path,
                        detail=(
                            f"Orphaned .aindex at {aindex_path.relative_to(self.lexibrary_dir)}: "
                            f"source directory {rel} no longer exists"
                        ),
                        risk="low",
                    )
                )

        return instructions

    def detect_orphaned_comments(self) -> list[FixInstruction]:
        """Detect orphaned .comments.yaml sidecars whose parent design file is missing."""
        if not self.designs_dir.is_dir():
            return []

        instructions: list[FixInstruction] = []
        for comments_path in sorted(self.designs_dir.rglob(".comments.yaml")):
            # A .comments.yaml file is expected to have a sibling design .md file
            # named after the source file (e.g. foo.py.md alongside .comments.yaml)
            parent_dir = comments_path.parent
            design_siblings = list(parent_dir.glob("*.md"))
            if not design_siblings:
                instructions.append(
                    FixInstruction(
                        action="delete_orphaned_comments",
                        target_path=comments_path,
                        detail=(
                            f"Orphaned .comments.yaml at "
                            f"{comments_path.relative_to(self.lexibrary_dir)}: "
                            f"no sibling design file exists"
                        ),
                        risk="low",
                    )
                )

        return instructions

    # -- Orphan concept detection ------------------------------------------

    def detect_orphan_concepts(
        self,
        concepts_dir: Path,
        link_graph_available: bool = False,
    ) -> list[FixInstruction]:
        """Detect concepts with zero inbound links.

        When the link graph is available, queries for inbound references.
        Zero-inbound concepts with no dependents are flagged as Low risk
        (auto-removable under auto_low). Others are flagged as Medium
        risk (proposed for human review).
        """
        if not concepts_dir.is_dir():
            return []

        if not link_graph_available:
            logger.info("Link graph unavailable -- skipping orphan concept detection")
            return []

        from lexibrary.linkgraph.query import LinkGraph  # noqa: PLC0415

        db_path = self.lexibrary_dir / "index.db"
        graph = LinkGraph.open(db_path)
        if graph is None:
            return []

        instructions: list[FixInstruction] = []
        try:
            for concept_path in sorted(concepts_dir.glob("*.md")):
                try:
                    rel = str(concept_path.relative_to(self.project_root))
                except ValueError:
                    rel = str(concept_path)

                reverse = graph.reverse_deps(rel)
                if len(reverse) == 0:
                    instructions.append(
                        FixInstruction(
                            action="remove_orphan_zero_deps",
                            target_path=concept_path,
                            detail=f"Concept {concept_path.name} has zero inbound links",
                            risk="low",
                        )
                    )
        finally:
            graph.close()

        return instructions

    # -- Convention/playbook staleness detection ----------------------------

    def detect_stale_conventions(
        self,
        conventions_dir: Path,
    ) -> list[FixInstruction]:
        """Check conventions for references to file paths that no longer exist.

        Scans the body and scope fields of each convention for path-like
        references and checks whether they exist on disk.
        """
        if not conventions_dir.is_dir():
            return []

        instructions: list[FixInstruction] = []
        for conv_path in sorted(conventions_dir.glob("*.md")):
            stale_paths = self._check_artifact_path_refs(conv_path)
            for stale in stale_paths:
                instructions.append(
                    FixInstruction(
                        action="flag_stale_convention",
                        target_path=conv_path,
                        detail=f"Convention references path '{stale}' which no longer exists",
                        risk="low",
                    )
                )

        return instructions

    def detect_stale_playbooks(
        self,
        playbooks_dir: Path,
    ) -> list[FixInstruction]:
        """Check playbooks for references to file paths that no longer exist."""
        if not playbooks_dir.is_dir():
            return []

        instructions: list[FixInstruction] = []
        for pb_path in sorted(playbooks_dir.glob("*.md")):
            stale_paths = self._check_artifact_path_refs(pb_path)
            for stale in stale_paths:
                instructions.append(
                    FixInstruction(
                        action="flag_stale_playbook",
                        target_path=pb_path,
                        detail=f"Playbook references path '{stale}' which no longer exists",
                        risk="low",
                    )
                )

        return instructions

    # Path reference extraction pattern: matches src/... or tests/... paths
    _PATH_REF_RE = re.compile(r"(?:^|\s|`)((?:src|tests)/[a-zA-Z0-9_/.-]+)")

    def _check_artifact_path_refs(self, artifact_path: Path) -> list[str]:
        """Extract path-like references from an artifact and check existence."""
        try:
            text = artifact_path.read_text(encoding="utf-8")
        except OSError:
            return []

        stale: list[str] = []
        seen: set[str] = set()
        for match in self._PATH_REF_RE.finditer(text):
            ref = match.group(1).rstrip(".,;:)")
            if ref in seen:
                continue
            seen.add(ref)
            candidate = self.project_root / ref
            if not candidate.exists():
                stale.append(ref)

        return stale

    # -- Design-file bidirectional dep cross-reference -----------------------

    def detect_design_dep_mismatch(
        self,
        design_files: list[Path],
    ) -> list[FixInstruction]:
        """Detect missing reverse-dep entries by cross-referencing design files.

        When design file A lists B in its dependencies, design file B should
        list A in its dependents.  This is a pure design-file consistency
        check — it does NOT require the link graph.  (The link-graph-based
        validator check ``check_bidirectional_deps`` detects drift between
        design files and actual imports; this check detects drift between
        design files themselves.)
        """
        source_to_design: dict[str, Path] = {}
        source_to_deps: dict[str, list[str]] = {}
        source_to_dependents: dict[str, set[str]] = {}

        for design_path in design_files:
            design = parse_design_file(design_path)
            if design is None:
                continue
            src = design.source_path
            source_to_design[src] = design_path
            source_to_deps[src] = [
                d.strip() for d in design.dependencies
                if d.strip() and d.strip() != "(none)"
            ]
            source_to_dependents[src] = {
                d.strip() for d in design.dependents
                if d.strip() and d.strip() != "(none)"
            }

        instructions: list[FixInstruction] = []
        for src, deps in source_to_deps.items():
            for dep in deps:
                if dep not in source_to_design:
                    continue
                if src not in source_to_dependents.get(dep, set()):
                    instructions.append(
                        FixInstruction(
                            action="add_missing_reverse_dep",
                            target_path=source_to_design[dep],
                            detail=(
                                f"{src} lists {dep} as a dependency but "
                                f"{dep} does not list {src} as a dependent"
                            ),
                            risk="low",
                        )
                    )

        return instructions

    # -- Blocked IWH promotion ---------------------------------------------

    def detect_promotable_iwh(
        self,
        ttl_hours: int = 72,
    ) -> list[FixInstruction]:
        """Detect blocked IWH signals older than the threshold for Stack promotion.

        Scans all IWH signals and returns promotion instructions for
        ``blocked`` signals older than *ttl_hours*.  ``find_all_iwh``
        returns source-relative paths, so the mirror ``.iwh`` location is
        computed via :func:`lexibrary.utils.paths.iwh_path` to ensure the
        ``apply_promote_blocked_iwh`` handler can find the file on disk.
        """
        from datetime import UTC, datetime, timedelta  # noqa: PLC0415

        from lexibrary.iwh.reader import find_all_iwh  # noqa: PLC0415
        from lexibrary.utils.paths import iwh_path as _iwh_path  # noqa: PLC0415

        try:
            signals = find_all_iwh(self.project_root)
        except Exception:
            logger.exception("Failed to scan IWH signals for promotion")
            return []

        now = datetime.now(UTC)
        instructions: list[FixInstruction] = []

        for rel_dir, iwh in signals:
            if iwh.scope != "blocked":
                continue
            age = now - iwh.created
            if age >= timedelta(hours=ttl_hours):
                # rel_dir is source-relative (e.g. "src/auth"); resolve to
                # the mirror ``.iwh`` path under ``.lexibrary/designs/``.
                source_dir = self.project_root / rel_dir
                iwh_file_path = _iwh_path(self.project_root, source_dir)
                instructions.append(
                    FixInstruction(
                        action="promote_blocked_iwh",
                        target_path=iwh_file_path,
                        detail=(
                            f"Blocked IWH signal in {rel_dir} is {age.days}d old; "
                            f"promote to Stack post and consume"
                        ),
                        risk="medium",
                    )
                )

        return instructions
