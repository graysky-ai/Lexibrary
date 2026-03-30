"""Status service — library health data gathering.

Extracts the business logic from ``_shared._run_status()`` into a
pure-data service.  The :func:`collect_status` function gathers all
status dashboard data and returns a :class:`StatusResult` dataclass
without producing any terminal output.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from lexibrary.artifacts.design_file_parser import parse_design_file_metadata
from lexibrary.linkgraph.health import IndexHealth, read_index_health
from lexibrary.stack.parser import parse_stack_post
from lexibrary.validator import validate_library
from lexibrary.wiki.parser import parse_concept_file


@dataclass
class StatusResult:
    """Pure-data container for library status information.

    All fields needed to render either a full dashboard or a quiet-mode
    single-line summary.  Importable without any CLI dependencies.
    """

    total_designs: int = 0
    stale_count: int = 0
    concept_counts: dict[str, int] = field(
        default_factory=lambda: {"active": 0, "deprecated": 0, "draft": 0},
    )
    stack_counts: dict[str, int] = field(
        default_factory=lambda: {"open": 0, "resolved": 0},
    )
    index_health: IndexHealth = field(
        default_factory=lambda: IndexHealth(
            artifact_count=None,
            link_count=None,
            built_at=None,
        ),
    )
    error_count: int = 0
    warning_count: int = 0
    latest_generated: datetime | None = None
    exit_code: int = 0

    @property
    def total_stack(self) -> int:
        """Total number of stack posts across all statuses."""
        return sum(self.stack_counts.values())


def collect_status(project_root: Path) -> StatusResult:
    """Gather library health data and return a :class:`StatusResult`.

    Scans design files, concepts, stack posts, runs lightweight
    validation, and reads link graph health.  Does **not** produce
    any terminal output.

    Parameters
    ----------
    project_root:
        Resolved project root directory containing ``.lexibrary/``.

    Returns
    -------
    StatusResult
        Fully populated status data ready for rendering.
    """
    lexibrary_dir = project_root / ".lexibrary"

    # --- Artifact counts ---
    # Design files: count .md files in the mirror tree (exclude concepts/ and stack/)
    design_files: list[Path] = []
    stale_count = 0
    latest_generated: datetime | None = None

    for md_path in sorted(lexibrary_dir.rglob("*.md")):
        # Skip non-design-file directories
        rel = md_path.relative_to(lexibrary_dir)
        rel_parts = rel.parts
        if rel_parts[0] in ("concepts", "stack"):
            continue
        # Skip known non-design files
        if md_path.name == "HANDOFF.md":
            continue
        meta = parse_design_file_metadata(md_path)
        if meta is not None:
            design_files.append(md_path)
            # Check staleness via source hash
            source_path = project_root / meta.source
            if source_path.exists():
                current_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
                if current_hash != meta.source_hash:
                    stale_count += 1
            # Track latest generated timestamp
            if latest_generated is None or meta.generated > latest_generated:
                latest_generated = meta.generated

    total_designs = len(design_files)

    # Concepts: count by status
    concepts_dir = lexibrary_dir / "concepts"
    concept_counts: dict[str, int] = {"active": 0, "deprecated": 0, "draft": 0}
    if concepts_dir.is_dir():
        for md_path in sorted(concepts_dir.glob("*.md")):
            concept = parse_concept_file(md_path)
            if concept is not None:
                s = concept.frontmatter.status
                if s in concept_counts:
                    concept_counts[s] += 1

    # Stack posts: count by status
    stack_dir = lexibrary_dir / "stack"
    stack_counts: dict[str, int] = {"open": 0, "resolved": 0}
    if stack_dir.is_dir():
        for md_path in sorted(stack_dir.glob("ST-*-*.md")):
            post = parse_stack_post(md_path)
            if post is not None:
                st = post.frontmatter.status
                if st in stack_counts:
                    stack_counts[st] += 1
                else:
                    stack_counts[st] = 1

    # --- Lightweight validation (errors + warnings only) ---
    report = validate_library(
        project_root,
        lexibrary_dir,
        severity_filter="warning",
    )
    error_count = report.summary.error_count
    warning_count = report.summary.warning_count

    # --- Link graph health ---
    index_health = read_index_health(project_root)

    return StatusResult(
        total_designs=total_designs,
        stale_count=stale_count,
        concept_counts=concept_counts,
        stack_counts=stack_counts,
        index_health=index_health,
        error_count=error_count,
        warning_count=warning_count,
        latest_generated=latest_generated,
        exit_code=report.exit_code(),
    )
