"""Individual validation check functions for library health.

Each check function follows the signature:
    check_*(project_root: Path, lexibrary_dir: Path) -> list[ValidationIssue]

Checks are grouped by severity:
- Error-severity: wikilink_resolution, file_existence, concept_frontmatter
- Warning-severity: hash_freshness, token_budgets, orphan_concepts,
    deprecated_concept_usage, orphaned_designs, convention_orphaned_scope
- Info-severity: forward_dependencies, stack_staleness,
    resolved_post_staleness, aindex_coverage,
    bidirectional_deps, dangling_links, orphan_artifacts, orphaned_iwh,
    comment_accumulation, deprecated_ttl, stale_concept,
    supersession_candidate, convention_stale, convention_gap,
    convention_consistent_violation, lookup_token_budget_exceeded,
    orphaned_iwh_signals
"""

from __future__ import annotations

import contextlib
import logging
import re
import sqlite3
from datetime import UTC
from pathlib import Path

import yaml

from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_frontmatter,
    parse_design_file_metadata,
)
from lexibrary.config.loader import load_config
from lexibrary.conventions.index import ConventionIndex
from lexibrary.conventions.parser import parse_convention_file
from lexibrary.lifecycle.comments import comment_count
from lexibrary.lifecycle.convention_comments import convention_comment_count
from lexibrary.lifecycle.deprecation import _count_commits_since, check_ttl_expiry
from lexibrary.lifecycle.design_comments import design_comment_path
from lexibrary.linkgraph.schema import SCHEMA_VERSION, check_schema_version, set_pragmas
from lexibrary.stack.parser import parse_stack_post
from lexibrary.tokenizer.approximate import ApproximateCounter
from lexibrary.utils.hashing import hash_file
from lexibrary.utils.paths import DESIGNS_DIR, aindex_path
from lexibrary.validator.report import ValidationIssue
from lexibrary.wiki.index import ConceptIndex
from lexibrary.wiki.parser import parse_concept_file
from lexibrary.wiki.resolver import UnresolvedLink, WikilinkResolver

logger = logging.getLogger(__name__)

# Regex to extract wikilinks from markdown content
_WIKILINK_RE = re.compile(r"\[\[(.+?)\]\]")

# Regex to match YAML frontmatter block
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)

_INDEX_DB_NAME = "index.db"
"""Filename of the SQLite index database within ``.lexibrary/``."""


# ---------------------------------------------------------------------------
# Error-severity checks
# ---------------------------------------------------------------------------


def check_wikilink_resolution(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Parse design files and Stack posts for wikilinks, verify each resolves.

    Uses WikilinkResolver to check every ``[[link]]`` found in design file
    wikilink sections and Stack post bodies.  Unresolved links produce
    error-severity issues with suggestions from fuzzy matching.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for unresolved wikilinks.
    """
    issues: list[ValidationIssue] = []

    # Build concept index and resolver
    concepts_dir = lexibrary_dir / "concepts"
    index = ConceptIndex.load(concepts_dir)
    stack_dir = lexibrary_dir / "stack"
    convention_dir = lexibrary_dir / "conventions"
    resolver = WikilinkResolver(
        index, stack_dir=stack_dir, convention_dir=convention_dir
    )

    # Collect wikilinks from design files
    for design_path in _iter_design_files(lexibrary_dir):
        design = parse_design_file(design_path)
        if design is None:
            continue

        # Design files store wikilinks in the wikilinks field (already bracket-stripped)
        for link_text in design.wikilinks:
            result = resolver.resolve(link_text)
            if isinstance(result, UnresolvedLink):
                suggestion = ""
                if result.suggestions:
                    suggestion = f"Did you mean [[{result.suggestions[0]}]]?"
                rel_path = _rel(design_path, project_root)
                issues.append(
                    ValidationIssue(
                        severity="error",
                        check="wikilink_resolution",
                        message=f"[[{link_text}]] does not resolve",
                        artifact=rel_path,
                        suggestion=suggestion,
                    )
                )

    # Collect wikilinks from Stack posts
    if stack_dir.is_dir():
        for md_path in sorted(stack_dir.glob("ST-*-*.md")):
            post = parse_stack_post(md_path)
            if post is None:
                continue

            # Extract wikilinks from body text
            body_links = _WIKILINK_RE.findall(post.raw_body)
            # Also include concept refs from frontmatter
            all_links_set: set[str] = set(body_links) | set(post.frontmatter.refs.concepts)

            for link_text in sorted(all_links_set):
                result = resolver.resolve(link_text)
                if isinstance(result, UnresolvedLink):
                    suggestion = ""
                    if result.suggestions:
                        suggestion = f"Did you mean [[{result.suggestions[0]}]]?"
                    rel_path = _rel(md_path, project_root)
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            check="wikilink_resolution",
                            message=f"[[{link_text}]] does not resolve",
                            artifact=rel_path,
                            suggestion=suggestion,
                        )
                    )

    return issues


def check_file_existence(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Verify source_path in design files and refs in Stack posts exist.

    Checks:
    - Design file ``source_path`` field resolves to an existing file
    - Stack post ``refs.files`` entries exist on disk
    - Stack post ``refs.designs`` entries exist on disk

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for missing files.
    """
    issues: list[ValidationIssue] = []
    stack_dir = lexibrary_dir / "stack"

    # Check design files' source_path
    for design_path in _iter_design_files(lexibrary_dir):
        design = parse_design_file(design_path)
        if design is None:
            continue

        source = project_root / design.source_path
        if not source.exists():
            rel_path = _rel(design_path, project_root)
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="file_existence",
                    message=f"Source file {design.source_path} does not exist",
                    artifact=rel_path,
                    suggestion="Remove the design file or restore the source file.",
                )
            )

    # Check Stack post refs
    if stack_dir.is_dir():
        for md_path in sorted(stack_dir.glob("ST-*-*.md")):
            post = parse_stack_post(md_path)
            if post is None:
                continue
            rel_path = _rel(md_path, project_root)

            for file_ref in post.frontmatter.refs.files:
                target = project_root / file_ref
                if not target.exists():
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            check="file_existence",
                            message=f"Referenced file {file_ref} does not exist",
                            artifact=rel_path,
                            suggestion="Update or remove the file reference.",
                        )
                    )

            for design_ref in post.frontmatter.refs.designs:
                target = project_root / design_ref
                if not target.exists():
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            check="file_existence",
                            message=(f"Referenced design file {design_ref} does not exist"),
                            artifact=rel_path,
                            suggestion="Update or remove the design reference.",
                        )
                    )

    return issues


def check_concept_frontmatter(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Validate all concept files have mandatory frontmatter fields.

    Checks that every ``.md`` file in the concepts directory has valid YAML
    frontmatter with ``title``, ``aliases``, ``tags``, and ``status`` fields.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for invalid frontmatter.
    """
    issues: list[ValidationIssue] = []
    concepts_dir = lexibrary_dir / "concepts"
    if not concepts_dir.is_dir():
        return issues

    for md_path in sorted(concepts_dir.glob("*.md")):
        rel_path = _rel(md_path, project_root)

        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="concept_frontmatter",
                    message="Could not read concept file",
                    artifact=rel_path,
                )
            )
            continue

        # Parse frontmatter
        fm_match = _FRONTMATTER_RE.match(text)
        if not fm_match:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="concept_frontmatter",
                    message="Missing YAML frontmatter",
                    artifact=rel_path,
                    suggestion=(
                        "Add --- delimited YAML frontmatter with title, aliases, tags, status."
                    ),
                )
            )
            continue

        try:
            data = yaml.safe_load(fm_match.group(1))
        except yaml.YAMLError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="concept_frontmatter",
                    message="Invalid YAML in frontmatter",
                    artifact=rel_path,
                    suggestion="Fix YAML syntax in frontmatter block.",
                )
            )
            continue

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="concept_frontmatter",
                    message="Frontmatter is not a YAML mapping",
                    artifact=rel_path,
                    suggestion="Frontmatter must be a YAML key-value mapping.",
                )
            )
            continue

        # Check mandatory fields
        mandatory_fields = ["title", "aliases", "tags", "status"]
        for field_name in mandatory_fields:
            if field_name not in data:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        check="concept_frontmatter",
                        message=f"Missing mandatory field: {field_name}",
                        artifact=rel_path,
                        suggestion=f"Add '{field_name}' to the concept frontmatter.",
                    )
                )

        # Validate status value if present
        if "status" in data:
            valid_statuses = {"draft", "active", "deprecated"}
            if data["status"] not in valid_statuses:
                issues.append(
                    ValidationIssue(
                        severity="error",
                        check="concept_frontmatter",
                        message=f"Invalid status: {data['status']}",
                        artifact=rel_path,
                        suggestion=(f"Status must be one of: {', '.join(sorted(valid_statuses))}."),
                    )
                )

    return issues


# ---------------------------------------------------------------------------
# Warning-severity checks
# ---------------------------------------------------------------------------


def check_hash_freshness(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Check that design file source_hash values match current file SHA-256.

    Parses design file metadata (footer-only) and compares the stored
    source_hash against the current SHA-256 hash of the source file.
    Returns warnings for mismatches.
    """
    issues: list[ValidationIssue] = []

    # Design files live under lexibrary_dir/designs/ mirroring the project structure
    designs_dir = lexibrary_dir / DESIGNS_DIR
    if not designs_dir.is_dir():
        return issues

    for design_path in sorted(designs_dir.rglob("*.md")):
        metadata = parse_design_file_metadata(design_path)
        if metadata is None:
            continue

        source_path = project_root / metadata.source
        if not source_path.is_file():
            # Missing source file is an error-severity issue (TG2),
            # not a hash freshness concern.
            continue

        current_hash = hash_file(source_path)
        if current_hash != metadata.source_hash:
            rel_design = str(design_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="hash_freshness",
                    message=(
                        f"Design file is stale: source_hash mismatch "
                        f"(stored {metadata.source_hash[:12]}... "
                        f"vs current {current_hash[:12]}...)"
                    ),
                    artifact=rel_design,
                    suggestion="Run `lexictl update` to regenerate the design file.",
                )
            )

    return issues


def check_token_budgets(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Check that artifacts stay within configured token budgets.

    Uses the approximate tokenizer (chars/4) for fast, dependency-free
    counting. Compares against TokenBudgetConfig values from the project
    configuration.
    """
    issues: list[ValidationIssue] = []

    config = load_config(project_root)
    budgets = config.token_budgets
    counter = ApproximateCounter()

    # Check design files
    designs_dir = lexibrary_dir / DESIGNS_DIR
    if designs_dir.is_dir():
        for file_path in sorted(designs_dir.rglob("*.md")):
            if not file_path.is_file():
                continue
            tokens = counter.count(file_path.read_text(encoding="utf-8", errors="replace"))
            if tokens > budgets.design_file_tokens:
                rel_path = str(file_path.relative_to(lexibrary_dir))
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        check="token_budgets",
                        message=(
                            f"Over budget: {tokens} tokens (limit {budgets.design_file_tokens})"
                        ),
                        artifact=rel_path,
                        suggestion="Trim content to stay within the token budget.",
                    )
                )

    # Check concept files
    concepts_dir = lexibrary_dir / "concepts"
    if concepts_dir.is_dir():
        for file_path in sorted(concepts_dir.glob("*.md")):
            if not file_path.is_file():
                continue
            tokens = counter.count(file_path.read_text(encoding="utf-8", errors="replace"))
            if tokens > budgets.concept_file_tokens:
                rel_path = str(file_path.relative_to(lexibrary_dir))
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        check="token_budgets",
                        message=(
                            f"Over budget: {tokens} tokens (limit {budgets.concept_file_tokens})"
                        ),
                        artifact=rel_path,
                        suggestion="Trim content to stay within the token budget.",
                    )
                )

    # Check .aindex files
    for aindex_file in sorted(lexibrary_dir.rglob(".aindex")):
        if not aindex_file.is_file():
            continue
        tokens = counter.count(aindex_file.read_text(encoding="utf-8", errors="replace"))
        if tokens > budgets.aindex_tokens:
            rel_path = str(aindex_file.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="token_budgets",
                    message=(f"Over budget: {tokens} tokens (limit {budgets.aindex_tokens})"),
                    artifact=rel_path,
                    suggestion="Trim content to stay within the token budget.",
                )
            )

    return issues


def check_orphan_concepts(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Identify concepts with zero inbound wikilink references.

    Scans all design files and Stack posts for [[wikilink]] references,
    then checks which concepts in the concepts directory have no inbound
    references at all.
    """
    issues: list[ValidationIssue] = []

    concepts_dir = lexibrary_dir / "concepts"
    if not concepts_dir.is_dir():
        return issues

    # Build the concept index
    concept_index = ConceptIndex.load(concepts_dir)
    concept_names = concept_index.names()
    if not concept_names:
        return issues

    # Collect all wikilink targets from design files and stack posts
    referenced: set[str] = set()

    # Scan design files
    designs_dir = lexibrary_dir / DESIGNS_DIR
    if designs_dir.is_dir():
        for md_path in designs_dir.rglob("*.md"):
            try:
                text = md_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in _WIKILINK_RE.findall(text):
                referenced.add(match.strip().lower())

    # Scan Stack posts
    stack_dir = lexibrary_dir / "stack"
    if stack_dir.is_dir():
        for md_path in stack_dir.rglob("*.md"):
            try:
                text = md_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in _WIKILINK_RE.findall(text):
                referenced.add(match.strip().lower())

    # Scan concept files themselves for cross-references
    for md_path in concepts_dir.glob("*.md"):
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _WIKILINK_RE.findall(text):
            referenced.add(match.strip().lower())

    # Check each concept for inbound references
    for name in concept_names:
        concept = concept_index.find(name)
        if concept is None:
            continue

        # Check if the concept title or any alias is referenced
        searchable = [concept.frontmatter.title.lower()]
        searchable.extend(a.lower() for a in concept.frontmatter.aliases)

        is_referenced = any(s in referenced for s in searchable)
        if not is_referenced:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="orphan_concepts",
                    message="Concept has no inbound wikilink references.",
                    artifact=f"concepts/{concept.frontmatter.title}",
                    suggestion=(
                        "Add [[" + concept.frontmatter.title + "]] references "
                        "in relevant design files or remove the concept."
                    ),
                )
            )

    return issues


def check_deprecated_concept_usage(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Find deprecated concepts that are still referenced by active artifacts.

    Scans design files and Stack posts for wikilinks pointing to concepts
    with status ``deprecated``. Includes ``superseded_by`` in the suggestion
    when available.
    """
    issues: list[ValidationIssue] = []

    concepts_dir = lexibrary_dir / "concepts"
    if not concepts_dir.is_dir():
        return issues

    # Build the concept index and identify deprecated concepts
    concept_index = ConceptIndex.load(concepts_dir)
    deprecated: dict[str, str | None] = {}  # lowercase name -> superseded_by

    for name in concept_index.names():
        concept = concept_index.find(name)
        if concept is None:
            continue
        if concept.frontmatter.status == "deprecated":
            deprecated[concept.frontmatter.title.lower()] = concept.frontmatter.superseded_by
            for alias in concept.frontmatter.aliases:
                deprecated[alias.lower()] = concept.frontmatter.superseded_by

    if not deprecated:
        return issues

    # Scan artifacts for references to deprecated concepts
    artifact_dirs: list[tuple[Path, str]] = []

    designs_dir = lexibrary_dir / DESIGNS_DIR
    if designs_dir.is_dir():
        artifact_dirs.append((designs_dir, "design"))

    stack_dir = lexibrary_dir / "stack"
    if stack_dir.is_dir():
        artifact_dirs.append((stack_dir, "stack"))

    for scan_dir, _artifact_type in artifact_dirs:
        for md_path in sorted(scan_dir.rglob("*.md")):
            try:
                text = md_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            rel_path = str(md_path.relative_to(lexibrary_dir))

            for match in _WIKILINK_RE.findall(text):
                link_target = match.strip().lower()
                if link_target in deprecated:
                    superseded_by = deprecated[link_target]
                    suggestion = (
                        f"Replace with [[{superseded_by}]]"
                        if superseded_by
                        else "Remove reference or update the concept status."
                    )
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            check="deprecated_concept_usage",
                            message=(f"References deprecated concept [[{match.strip()}]]."),
                            artifact=rel_path,
                            suggestion=suggestion,
                        )
                    )

    return issues


# ---------------------------------------------------------------------------
# Info-severity checks
# ---------------------------------------------------------------------------


def check_forward_dependencies(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Verify that dependency targets listed in design files exist on disk.

    Parses each design file's ``## Dependencies`` section and checks that every
    listed path resolves to an existing file. Missing targets produce
    info-severity issues.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for missing dependency targets.
    """
    issues: list[ValidationIssue] = []

    # Walk .lexibrary for design files (*.md, excluding .aindex and special files)
    for design_path in _iter_design_files(lexibrary_dir):
        design = parse_design_file(design_path)
        if design is None:
            continue

        for dep in design.dependencies:
            # Skip placeholder entries like "(none)"
            dep_stripped = dep.strip()
            if not dep_stripped or dep_stripped == "(none)":
                continue

            # Dependencies are project-relative paths
            dep_target = project_root / dep_stripped
            if not dep_target.exists():
                issues.append(
                    ValidationIssue(
                        severity="info",
                        check="forward_dependencies",
                        message=f"Dependency target does not exist: {dep_stripped}",
                        artifact=str(design_path.relative_to(project_root)),
                        suggestion=f"Remove or update the dependency on '{dep_stripped}'",
                    )
                )

    return issues


def check_stack_staleness(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Flag Stack posts that reference files with stale design files.

    For each Stack post with ``refs.files`` entries, looks up whether any
    referenced file's design file has a stale ``source_hash``. This is a
    heuristic -- the file change may not affect the post's relevance, but
    it is the best signal available.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for potentially outdated posts.
    """
    issues: list[ValidationIssue] = []

    stack_dir = lexibrary_dir / "stack"
    if not stack_dir.is_dir():
        return issues

    for post_path in sorted(stack_dir.glob("*.md")):
        post = parse_stack_post(post_path)
        if post is None:
            continue

        refs_files = post.frontmatter.refs.files
        if not refs_files:
            continue

        stale_files: list[str] = []
        for ref_file in refs_files:
            # Build the design file path for the referenced source file
            ref_path = Path(ref_file)
            design_file_path = lexibrary_dir / DESIGNS_DIR / f"{ref_path}.md"

            metadata = parse_design_file_metadata(design_file_path)
            if metadata is None:
                # No design file or no metadata -- cannot determine staleness
                continue

            # Check if source file exists and compare hashes
            source_path = project_root / ref_file
            if not source_path.exists():
                # Source missing -- file_existence check handles this
                continue

            try:
                current_hash = hash_file(source_path)
            except OSError:
                continue

            if current_hash != metadata.source_hash:
                stale_files.append(ref_file)

        if stale_files:
            post_rel = str(post_path.relative_to(project_root))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="stack_staleness",
                    message=(
                        f"Stack post '{post.frontmatter.title}' references files "
                        f"with stale design files: {', '.join(stale_files)}"
                    ),
                    artifact=post_rel,
                    suggestion="Verify the solution still applies after recent source changes",
                )
            )

    return issues


# Resolution types that use the shorter TTL
_SHORT_TTL_RESOLUTION_TYPES = frozenset({"wontfix", "by_design", "cannot_reproduce"})


def check_resolved_post_staleness(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Check resolved Stack posts for staleness signals.

    Examines all Stack posts with ``status="resolved"`` and produces
    info-severity issues when staleness signals are detected:

    - **Age threshold**: Post age exceeds ``stack.staleness_ttl_commits``
      (or ``staleness_ttl_short_commits`` for ``wontfix``/``by_design``/
      ``cannot_reproduce`` resolution types).
    - **Referenced files deleted**: Files listed in ``refs.files`` no
      longer exist in the source tree.

    Only resolved posts are checked.  Open, stale, outdated, and duplicate
    posts are skipped.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for potentially stale
        resolved posts.
    """
    issues: list[ValidationIssue] = []

    stack_dir = lexibrary_dir / "stack"
    if not stack_dir.is_dir():
        return issues

    # Load config for TTL values
    try:
        config = load_config(project_root)
    except Exception:
        config = None

    staleness_ttl = 200  # default
    staleness_ttl_short = 100  # default
    if config is not None:
        staleness_ttl = config.stack.staleness_ttl_commits
        staleness_ttl_short = config.stack.staleness_ttl_short_commits

    # Check whether git is available for commit-based TTL checks
    git_available = _git_is_available(project_root)

    for post_path in sorted(stack_dir.glob("*.md")):
        post = parse_stack_post(post_path)
        if post is None:
            continue

        # Only check resolved posts
        if post.frontmatter.status != "resolved":
            continue

        post_rel = str(post_path.relative_to(project_root))

        # --- Age threshold check (commit-based) ---
        if git_available:
            created_iso = post.frontmatter.created.isoformat()
            commits_since = _count_commits_since(project_root, created_iso)

            # Pick the appropriate TTL based on resolution type
            if post.frontmatter.resolution_type in _SHORT_TTL_RESOLUTION_TYPES:
                ttl = staleness_ttl_short
            else:
                ttl = staleness_ttl

            if commits_since > ttl:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        check="resolved_post_staleness",
                        message=(
                            f"Resolved post '{post.frontmatter.title}' may be stale: "
                            f"{commits_since} commits since creation (TTL: {ttl})"
                        ),
                        artifact=post_rel,
                        suggestion=(
                            "Review the post and either mark it stale with "
                            "`lexi stack stale <slug>` or confirm it is still relevant"
                        ),
                    )
                )

        # --- Referenced files deleted check ---
        refs_files = post.frontmatter.refs.files
        if refs_files:
            deleted_refs: list[str] = []
            for ref_file in refs_files:
                source_path = project_root / ref_file
                if not source_path.exists():
                    deleted_refs.append(ref_file)

            if deleted_refs:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        check="resolved_post_staleness",
                        message=(
                            f"Resolved post '{post.frontmatter.title}' references "
                            f"deleted files: {', '.join(deleted_refs)}"
                        ),
                        artifact=post_rel,
                        suggestion=(
                            "Review the post and either mark it stale with "
                            "`lexi stack stale <slug>` or update file references"
                        ),
                    )
                )

    return issues


def _git_is_available(project_root: Path) -> bool:
    """Return True if git is available and the project is a git repo."""
    import subprocess  # noqa: PLC0415

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_aindex_coverage(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Find directories within scope_root that lack .aindex files.

    Walks the ``scope_root`` directory tree (defaulting to ``project_root``)
    and checks that each directory has a corresponding ``.aindex`` file in
    ``.lexibrary/``.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for unindexed directories.
    """
    issues: list[ValidationIssue] = []

    # Load config to get scope_root
    try:
        config = load_config(project_root)
    except Exception:
        # If config is broken, use project_root as scope_root
        config = None

    if config is not None and config.scope_root != ".":
        scope_root = project_root / config.scope_root
    else:
        scope_root = project_root

    if not scope_root.is_dir():
        return issues

    # Walk directories, skipping hidden dirs and .lexibrary itself
    for dirpath in _iter_directories(scope_root, project_root, lexibrary_dir):
        expected_aindex = aindex_path(project_root, dirpath)
        if not expected_aindex.exists():
            dir_rel = str(dirpath.relative_to(project_root))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="aindex_coverage",
                    message=f"Directory not indexed: {dir_rel}",
                    artifact=dir_rel,
                    suggestion="Run 'lexictl index' to generate .aindex files",
                )
            )

    return issues


def check_bidirectional_deps(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Compare design file dependency lists against ``ast_import`` links in the graph.

    For each design file, parses the ``## Dependencies`` section to get
    listed dependencies, then queries the link graph for actual
    ``ast_import`` outbound links from the corresponding source file.
    Mismatches in either direction produce info-severity issues.

    Returns an empty list when the index is absent, corrupt, or has a
    schema version mismatch -- graceful degradation per D2.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for dependency mismatches.
    """
    issues: list[ValidationIssue] = []

    db_path = lexibrary_dir / _INDEX_DB_NAME
    if not db_path.is_file():
        return issues

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
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
            return issues

        # Build a lookup: source artifact path -> set of ast_import target paths
        graph_imports: dict[str, set[str]] = {}
        rows = conn.execute(
            "SELECT a_src.path, a_tgt.path "
            "FROM links AS l "
            "JOIN artifacts AS a_src ON l.source_id = a_src.id "
            "JOIN artifacts AS a_tgt ON l.target_id = a_tgt.id "
            "WHERE l.link_type = 'ast_import'"
        ).fetchall()
        for src_path, tgt_path in rows:
            graph_imports.setdefault(src_path, set()).add(tgt_path)

    except (sqlite3.Error, OSError) as exc:
        logger.warning("Cannot read index for bidirectional check from %s: %s", db_path, exc)
        return issues

    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    # Walk design files and compare
    for design_path in _iter_design_files(lexibrary_dir):
        design = parse_design_file(design_path)
        if design is None:
            continue

        source_path = design.source_path
        rel_design = _rel(design_path, project_root)

        # Gather design-listed deps (project-relative paths), skip placeholders
        design_deps: set[str] = set()
        for dep in design.dependencies:
            dep_stripped = dep.strip()
            if dep_stripped and dep_stripped != "(none)":
                design_deps.add(dep_stripped)

        # Gather graph-listed ast_import targets for this source file
        graph_deps = graph_imports.get(source_path, set())

        # Direction 1: dep listed in design file but not found in graph
        for dep in sorted(design_deps - graph_deps):
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="bidirectional_deps",
                    message=(
                        f"Dependency {dep} is listed in the design file "
                        f"but not found as an ast_import link in the graph"
                    ),
                    artifact=rel_design,
                    suggestion=(
                        "The link graph index may be stale; run `lexictl update` to rebuild."
                    ),
                )
            )

        # Direction 2: graph link exists but not listed in design file
        for dep in sorted(graph_deps - design_deps):
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="bidirectional_deps",
                    message=(
                        f"Import {dep} exists in the link graph "
                        f"but is not listed in the design file dependencies"
                    ),
                    artifact=rel_design,
                    suggestion="Update the design file or rebuild the index.",
                )
            )

    return issues


def check_dangling_links(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect link graph artifacts whose backing files no longer exist on disk.

    Opens ``index.db`` and queries all artifacts with ``kind`` in
    (``source``, ``design``, ``concept``, ``stack``).  For each artifact,
    verifies the file at ``artifact.path`` (resolved relative to
    *project_root*) exists.  Convention artifacts are skipped because
    they use synthetic paths with no backing file.

    Returns an empty list when the index is absent, corrupt, or has a
    schema version mismatch -- graceful degradation per D2.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for dangling links.
    """
    issues: list[ValidationIssue] = []

    db_path = lexibrary_dir / _INDEX_DB_NAME
    if not db_path.is_file():
        return issues

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
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
            return issues

        # Query all non-convention artifacts
        rows = conn.execute(
            "SELECT path, kind FROM artifacts "
            "WHERE kind IN ('source', 'design', 'concept', 'stack')"
        ).fetchall()

    except (sqlite3.Error, OSError) as exc:
        logger.warning("Cannot read index for dangling links check from %s: %s", db_path, exc)
        return issues

    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    # Check each artifact's backing file
    for artifact_path, kind in rows:
        full_path = project_root / artifact_path
        if not full_path.exists():
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="dangling_links",
                    message=(
                        f"Link graph references {kind} file that no longer exists: {artifact_path}"
                    ),
                    artifact=artifact_path,
                    suggestion="Rebuild the index with `lexictl update` to remove stale entries.",
                )
            )

    return issues


def find_orphaned_aindex(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Find ``.aindex`` files under ``.lexibrary/designs/`` with no corresponding source directory.

    Walks the designs directory tree for ``.aindex`` files and checks whether
    the source directory they represent still exists on disk.  An ``.aindex``
    file at ``.lexibrary/designs/src/auth/.aindex`` is orphaned when
    ``<project_root>/src/auth/`` does not exist.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for orphaned ``.aindex`` files.
    """
    issues: list[ValidationIssue] = []

    designs_dir = lexibrary_dir / DESIGNS_DIR
    if not designs_dir.is_dir():
        return issues

    for aindex_file in sorted(designs_dir.rglob(".aindex")):
        # The source directory is the aindex parent path relative to designs_dir,
        # mapped back to project_root.
        aindex_parent = aindex_file.parent
        try:
            relative_dir = aindex_parent.relative_to(designs_dir)
        except ValueError:
            continue

        source_dir = project_root / relative_dir
        if not source_dir.is_dir():
            rel_aindex = str(aindex_file.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="orphaned_aindex",
                    message=(
                        f"Orphaned .aindex file: source directory "
                        f"{relative_dir} no longer exists"
                    ),
                    artifact=rel_aindex,
                    suggestion=(
                        "Run `lexictl validate --fix` to remove orphaned .aindex files, "
                        "or delete manually."
                    ),
                )
            )

    return issues


def find_orphaned_iwh(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Find ``.iwh`` files under ``.lexibrary/designs/`` with no corresponding source directory.

    Walks the designs directory tree for ``.iwh`` files and checks whether
    the source directory they represent still exists on disk.  An ``.iwh``
    file at ``.lexibrary/designs/src/auth/.iwh`` is orphaned when
    ``<project_root>/src/auth/`` does not exist.

    Detection is path-based, not content-based: even unparseable ``.iwh``
    files are flagged if their source directory is missing.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for orphaned ``.iwh`` files.
    """
    issues: list[ValidationIssue] = []

    designs_dir = lexibrary_dir / DESIGNS_DIR
    if not designs_dir.is_dir():
        return issues

    for iwh_file in sorted(designs_dir.rglob(".iwh")):
        # The source directory is the iwh parent path relative to designs_dir,
        # mapped back to project_root.
        iwh_parent = iwh_file.parent
        try:
            relative_dir = iwh_parent.relative_to(designs_dir)
        except ValueError:
            continue

        source_dir = project_root / relative_dir
        if not source_dir.is_dir():
            rel_iwh = str(iwh_file.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="orphaned_iwh",
                    message=(
                        f"Orphaned .iwh file: source directory "
                        f"{relative_dir} no longer exists"
                    ),
                    artifact=rel_iwh,
                    suggestion=(
                        "Run `lexictl update` or `lexictl iwh clean` to remove "
                        "orphaned .iwh files."
                    ),
                )
            )

    return issues


def check_orphan_artifacts(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect link graph index entries whose backing files have been deleted.

    Opens ``index.db`` and queries all non-convention artifacts (source,
    design, concept, stack).  For each artifact, verifies the file at
    ``artifact.path`` (resolved relative to *project_root*) exists on
    disk.  Missing files produce info-severity issues with a suggestion
    to rebuild the index.

    Returns an empty list when the index is absent, corrupt, or has a
    schema version mismatch -- graceful degradation per D2.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for orphan artifacts.
    """
    issues: list[ValidationIssue] = []

    db_path = lexibrary_dir / _INDEX_DB_NAME
    if not db_path.is_file():
        return issues

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(str(db_path))
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
            return issues

        # Query all non-convention artifacts
        rows = conn.execute(
            "SELECT path, kind FROM artifacts WHERE kind != 'convention'"
        ).fetchall()

    except (sqlite3.Error, OSError) as exc:
        logger.warning("Cannot read index for orphan check from %s: %s", db_path, exc)
        return issues

    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()

    # Check each artifact's backing file
    for artifact_path, kind in rows:
        full_path = project_root / artifact_path
        if not full_path.exists():
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="orphan_artifacts",
                    message=(f"Index contains {kind} artifact for deleted file: {artifact_path}"),
                    artifact=artifact_path,
                    suggestion="Run `lexictl update` to rebuild the index.",
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Lifecycle checks (design-update change)
# ---------------------------------------------------------------------------


def check_orphaned_designs(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect design files whose source files no longer exist on disk.

    Scans all design files in ``.lexibrary/designs/`` and verifies that each
    has a corresponding source file.  Design files with ``status: deprecated``
    are excluded (they are already known to be orphaned).

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for orphaned design files.
    """
    issues: list[ValidationIssue] = []

    for design_path in _iter_design_files(lexibrary_dir):
        parsed = parse_design_file(design_path)
        if parsed is None:
            continue

        # Skip already-deprecated files -- they are handled by deprecated_ttl
        if parsed.frontmatter.status == "deprecated":
            continue

        source_rel = parsed.source_path
        source_abs = project_root / source_rel

        if not source_abs.exists():
            rel_design = str(design_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="orphaned_designs",
                    message=(
                        f"Design file references missing source: {source_rel}"
                    ),
                    artifact=rel_design,
                    suggestion=(
                        "Run `lexictl update` to trigger deprecation workflow, "
                        "or `lexictl validate --fix` to apply deprecation."
                    ),
                )
            )

    return issues


def check_comment_accumulation(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Warn when design files accumulate too many comments.

    Counts comments in each design file's sibling ``.comments.yaml`` and
    produces info-severity issues when the count exceeds the configured
    ``deprecation.comment_warning_threshold`` (default 10).

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for excessive comments.
    """
    issues: list[ValidationIssue] = []

    # Load config to get the threshold
    try:
        config = load_config(project_root)
    except Exception:
        config = None

    threshold = 10  # default
    if config is not None:
        threshold = config.deprecation.comment_warning_threshold

    for design_path in _iter_design_files(lexibrary_dir):
        comment_file = design_comment_path(design_path)
        count = comment_count(comment_file)
        if count > threshold:
            rel_design = str(design_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="comment_accumulation",
                    message=(
                        f"Design file has {count} comments "
                        f"(threshold: {threshold})"
                    ),
                    artifact=rel_design,
                    suggestion=(
                        "Run the maintainer-agent to incorporate or prune "
                        "accumulated comments, or manually review."
                    ),
                )
            )

    return issues


def check_deprecated_ttl(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect deprecated design files whose TTL has expired.

    Checks all design files with ``status: deprecated`` and reports those
    whose commit-based TTL has been exceeded based on
    ``deprecation.ttl_commits`` config.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for expired deprecated files.
    """
    issues: list[ValidationIssue] = []

    # Load config to get TTL
    try:
        config = load_config(project_root)
    except Exception:
        config = None

    ttl_commits = 50  # default
    if config is not None:
        ttl_commits = config.deprecation.ttl_commits

    for design_path in _iter_design_files(lexibrary_dir):
        frontmatter = parse_design_file_frontmatter(design_path)
        if frontmatter is None:
            continue
        if frontmatter.status != "deprecated":
            continue

        if check_ttl_expiry(design_path, project_root, ttl_commits):
            rel_design = str(design_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="deprecated_ttl",
                    message=(
                        f"Deprecated design file has exceeded TTL "
                        f"({ttl_commits} commits)"
                    ),
                    artifact=rel_design,
                    suggestion=(
                        "Run `lexictl update` to hard-delete expired files, "
                        "or `lexictl validate --fix` to remove."
                    ),
                )
            )

    return issues


def check_stale_concepts(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect active concepts whose linked files no longer exist on disk.

    Parses all concept files and checks their ``linked_files`` entries
    (backtick-delimited paths extracted from the concept body). Active
    concepts with at least one missing linked file produce an info-severity
    issue. Deprecated concepts and concepts with no linked files are skipped.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for stale concepts.
    """
    issues: list[ValidationIssue] = []

    concepts_dir = lexibrary_dir / "concepts"
    if not concepts_dir.is_dir():
        return issues

    concept_index = ConceptIndex.load(concepts_dir)
    for name in concept_index.names():
        concept = concept_index.find(name)
        if concept is None:
            continue

        # Only check active concepts (skip deprecated, draft, etc.)
        if concept.frontmatter.status != "active":
            continue

        # Skip concepts with no linked files
        if not concept.linked_files:
            continue

        # Check each linked file for existence
        missing_files: list[str] = []
        for file_ref in concept.linked_files:
            resolved = project_root / file_ref
            if not resolved.exists():
                missing_files.append(file_ref)

        if missing_files:
            missing_str = ", ".join(missing_files)
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="stale_concept",
                    message=(
                        f"Active concept references missing file(s): {missing_str}"
                    ),
                    artifact=f"concepts/{concept.frontmatter.title}",
                    suggestion=(
                        "Review the concept and update linked file references, "
                        "or deprecate the concept if it is no longer relevant."
                    ),
                )
            )

    return issues


def check_supersession_candidates(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect active concepts that may be candidates for supersession.

    Compares titles and aliases across all active concepts to find overlaps
    that suggest two concepts describe the same thing.  Three kinds of
    overlap are detected:

    * **title overlap** -- two active concepts share the same title
      (case-insensitive).
    * **alias overlap** -- two active concepts share the same alias.
    * **title-alias cross-match** -- one concept's title matches another
      concept's alias (or vice versa).

    Deprecated concepts are excluded from the comparison.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for supersession candidates.
    """
    issues: list[ValidationIssue] = []

    concepts_dir = lexibrary_dir / "concepts"
    if not concepts_dir.is_dir():
        return issues

    # Parse concept files directly to get every concept exactly once,
    # avoiding ConceptIndex.find() whose alias-based lookup can return
    # the wrong concept when titles and aliases cross-reference each other.
    active_concepts: list[tuple[str, list[str]]] = []
    for md_path in sorted(concepts_dir.glob("*.md")):
        concept = parse_concept_file(md_path)
        if concept is None:
            continue
        if concept.frontmatter.status != "active":
            continue
        active_concepts.append(
            (concept.frontmatter.title, list(concept.frontmatter.aliases))
        )

    # Build maps: normalized name -> list of concept titles that claim it
    name_owners: dict[str, list[str]] = {}

    for title, aliases in active_concepts:
        norm_title = title.strip().lower()
        name_owners.setdefault(norm_title, []).append(title)
        for alias in aliases:
            norm_alias = alias.strip().lower()
            name_owners.setdefault(norm_alias, []).append(title)

    # Any normalised name owned by more than one concept is an overlap
    seen_pairs: set[tuple[str, str]] = set()
    for norm_name, owners in name_owners.items():
        if len(owners) < 2:
            continue
        # Deduplicate owners (a concept can't overlap with itself)
        unique_owners = sorted(set(owners))
        if len(unique_owners) < 2:
            continue
        for i, owner_a in enumerate(unique_owners):
            for owner_b in unique_owners[i + 1 :]:
                pair = (owner_a, owner_b)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                issues.append(
                    ValidationIssue(
                        severity="info",
                        check="supersession_candidate",
                        message=(
                            f"Possible supersession: '{owner_a}' and "
                            f"'{owner_b}' share the name '{norm_name}'"
                        ),
                        artifact=f"concepts/{owner_a}",
                        suggestion=(
                            "Review whether one concept should supersede "
                            "the other.  Use `lexi concept deprecate` to "
                            "mark the redundant concept."
                        ),
                    )
                )

    return issues


# ---------------------------------------------------------------------------
# Convention-specific checks
# ---------------------------------------------------------------------------


def check_convention_orphaned_scope(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect conventions whose scope directory no longer exists.

    Scans all convention files and checks that each convention's ``scope``
    directory exists under the project root. Conventions with
    ``scope == "project"`` are always valid and are skipped. Deprecated
    conventions are also skipped.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for orphaned scopes.
    """
    issues: list[ValidationIssue] = []

    conventions_dir = lexibrary_dir / "conventions"
    if not conventions_dir.is_dir():
        return issues

    for md_path in sorted(conventions_dir.glob("*.md")):
        convention = parse_convention_file(md_path)
        if convention is None:
            continue

        # Skip deprecated conventions
        if convention.frontmatter.status == "deprecated":
            continue

        scope = convention.frontmatter.scope

        # "project" scope always valid
        if scope == "project":
            continue

        # Check if the scope directory exists under project root
        scope_path = project_root / scope
        if not scope_path.is_dir():
            rel_convention = str(md_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="convention_orphaned_scope",
                    message=(
                        f"Convention scope directory '{scope}' does not exist"
                    ),
                    artifact=rel_convention,
                    suggestion=(
                        "Update the convention's scope to a valid directory, "
                        "or deprecate the convention if the scope was removed."
                    ),
                )
            )

    return issues


def check_convention_stale(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect active conventions whose scope directory is empty.

    An active convention whose scope directory exists but contains no source
    files (non-directory entries) may be stale. Conventions with
    ``scope == "project"`` are skipped (project-wide conventions are always
    relevant). Deprecated and draft conventions are also skipped.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for stale conventions.
    """
    issues: list[ValidationIssue] = []

    conventions_dir = lexibrary_dir / "conventions"
    if not conventions_dir.is_dir():
        return issues

    for md_path in sorted(conventions_dir.glob("*.md")):
        convention = parse_convention_file(md_path)
        if convention is None:
            continue

        # Only check active conventions
        if convention.frontmatter.status != "active":
            continue

        scope = convention.frontmatter.scope

        # "project" scope is always relevant
        if scope == "project":
            continue

        scope_path = project_root / scope
        if not scope_path.is_dir():
            # If the directory doesn't exist, orphaned_scope covers it
            continue

        # Check if scope directory has any source files (non-directory entries)
        has_files = False
        try:
            for child in scope_path.iterdir():
                if child.is_file():
                    has_files = True
                    break
        except PermissionError:
            continue

        if not has_files:
            rel_convention = str(md_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="convention_stale",
                    message=(
                        f"Active convention scoped to '{scope}' "
                        f"but directory contains no source files"
                    ),
                    artifact=rel_convention,
                    suggestion=(
                        "Review whether this convention is still relevant, "
                        "or deprecate it if the scope directory is no longer "
                        "in active use."
                    ),
                )
            )

    return issues


def check_convention_gap(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect directories with many source files but no applicable conventions.

    Walks the project source tree and flags directories that contain 5 or
    more source files but have zero conventions applicable to them (via scope
    matching). This is a nudge to consider adding conventions for
    high-traffic directories.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for convention gaps.
    """
    issues: list[ValidationIssue] = []

    conventions_dir = lexibrary_dir / "conventions"

    # Load convention index
    conv_index = ConventionIndex(conventions_dir)
    conv_index.load()

    # Load config for scope_root
    try:
        config = load_config(project_root)
    except Exception:
        config = None

    scope_root_str = "."
    if config is not None:
        scope_root_str = config.scope_root

    scope_root = project_root / scope_root_str
    if not scope_root.is_dir():
        return issues

    file_threshold = 5

    # Walk directories in scope
    for directory in _iter_directories(scope_root, project_root, lexibrary_dir):
        # Count source files (non-directory, non-hidden entries)
        try:
            source_files = [
                child
                for child in directory.iterdir()
                if child.is_file() and not child.name.startswith(".")
            ]
        except PermissionError:
            continue

        if len(source_files) < file_threshold:
            continue

        # Check if any active (non-deprecated) conventions apply to this directory
        rel_dir = str(directory.relative_to(project_root))
        # Use a representative file path for scope matching
        representative = f"{rel_dir}/example.py" if rel_dir != "." else "example.py"
        applicable = conv_index.find_by_scope(representative, scope_root_str)

        # Filter to only active conventions
        active_applicable = [
            c for c in applicable if c.frontmatter.status == "active"
        ]

        if not active_applicable:
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="convention_gap",
                    message=(
                        f"Directory '{rel_dir}' has {len(source_files)} source "
                        f"files but no applicable conventions"
                    ),
                    artifact=rel_dir,
                    suggestion=(
                        "Consider adding a convention for this directory to "
                        "document coding standards and patterns."
                    ),
                )
            )

    return issues


def check_convention_consistent_violation(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect conventions with accumulated unresolved comments.

    Conventions with 3 or more comments in their ``.comments.yaml`` file
    may indicate a pattern of consistent violation that should be
    reviewed. The convention may need to be revised, better communicated,
    or deprecated.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for conventions with many comments.
    """
    issues: list[ValidationIssue] = []

    conventions_dir = lexibrary_dir / "conventions"
    if not conventions_dir.is_dir():
        return issues

    comment_threshold = 3

    for md_path in sorted(conventions_dir.glob("*.md")):
        convention = parse_convention_file(md_path)
        if convention is None:
            continue

        # Skip deprecated conventions
        if convention.frontmatter.status == "deprecated":
            continue

        count = convention_comment_count(md_path)
        if count >= comment_threshold:
            rel_convention = str(md_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="convention_consistent_violation",
                    message=(
                        f"Convention has {count} comments "
                        f"(threshold: {comment_threshold}) -- possible "
                        f"consistent violation"
                    ),
                    artifact=rel_convention,
                    suggestion=(
                        "Review the convention comments to determine if the "
                        "rule needs revision, better communication, or "
                        "deprecation."
                    ),
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _rel(path: Path, root: Path) -> str:
    """Return a relative path string, falling back to the full path."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _iter_design_files(lexibrary_dir: Path) -> list[Path]:
    """Iterate over design file paths in .lexibrary/designs/."""
    designs_dir = lexibrary_dir / DESIGNS_DIR
    if not designs_dir.is_dir():
        return []

    return sorted(designs_dir.rglob("*.md"))


def _iter_directories(
    scope_root: Path,
    project_root: Path,
    lexibrary_dir: Path,
) -> list[Path]:
    """Walk scope_root and yield directories, skipping hidden and .lexibrary."""
    results: list[Path] = []

    def _walk(directory: Path) -> None:
        # Include the directory itself
        results.append(directory)

        try:
            children = sorted(directory.iterdir())
        except PermissionError:
            return

        for child in children:
            if not child.is_dir():
                continue
            # Skip hidden directories
            if child.name.startswith("."):
                continue
            # Skip .lexibrary
            if child.resolve() == lexibrary_dir.resolve():
                continue
            # Skip common non-source directories
            if child.name in {
                "node_modules",
                "__pycache__",
                "venv",
                ".venv",
            }:
                continue
            _walk(child)

    _walk(scope_root)
    return results


# ---------------------------------------------------------------------------
# Info-severity: lookup token budget exceeded
# ---------------------------------------------------------------------------


def check_lookup_token_budget_exceeded(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Find design files that individually exceed the lookup token budget.

    When a single design file consumes the entire ``lookup_total_tokens``
    budget, supplementary lookup sections (known issues, IWH signals,
    links) will always be truncated.  This check flags those files at
    info severity so the user knows truncation is happening.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for oversized design files.
    """
    issues: list[ValidationIssue] = []

    try:
        config = load_config(project_root)
    except Exception:
        return issues

    budget = config.token_budgets.lookup_total_tokens
    counter = ApproximateCounter()

    designs_dir = lexibrary_dir / DESIGNS_DIR
    if not designs_dir.is_dir():
        return issues

    for file_path in sorted(designs_dir.rglob("*.md")):
        if not file_path.is_file():
            continue
        tokens = counter.count(file_path.read_text(encoding="utf-8", errors="replace"))
        if tokens > budget:
            rel_path = str(file_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="lookup_token_budget_exceeded",
                    message=(
                        f"Design file uses {tokens} tokens, exceeding "
                        f"lookup budget of {budget}; supplementary "
                        f"sections will be truncated"
                    ),
                    artifact=rel_path,
                    suggestion=(
                        "Trim the design file or increase "
                        "token_budgets.lookup_total_tokens in config.yaml."
                    ),
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Info-severity: orphaned (expired) IWH signals
# ---------------------------------------------------------------------------


def check_orphaned_iwh_signals(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Find IWH signals that have exceeded their configured TTL.

    Walks all ``.iwh`` files under ``.lexibrary/``, parses their
    ``created`` timestamp, and flags any whose age exceeds the
    ``iwh.ttl_hours`` setting.  Expired signals are stale context that
    should be consumed or cleaned up.

    This check complements ``find_orphaned_iwh`` (which detects signals
    whose source directory no longer exists) by catching signals that are
    still structurally valid but temporally stale.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for expired IWH signals.
    """
    from datetime import datetime  # noqa: PLC0415

    from lexibrary.iwh.parser import parse_iwh  # noqa: PLC0415

    issues: list[ValidationIssue] = []

    try:
        config = load_config(project_root)
    except Exception:
        return issues

    ttl_hours = config.iwh.ttl_hours
    if ttl_hours <= 0:
        # TTL of 0 means expiry is disabled
        return issues

    now = datetime.now(tz=UTC)

    for iwh_file in sorted(lexibrary_dir.rglob(".iwh")):
        if not iwh_file.is_file():
            continue

        parsed = parse_iwh(iwh_file)
        if parsed is None:
            # Unparseable files are handled by find_orphaned_iwh
            continue

        created = parsed.created
        # Ensure timezone-aware comparison
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)

        age_hours = (now - created).total_seconds() / 3600
        if age_hours > ttl_hours:
            try:
                rel_path = str(iwh_file.relative_to(lexibrary_dir))
            except ValueError:
                continue
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="orphaned_iwh_signals",
                    message=(
                        f"IWH signal expired: {int(age_hours)}h old "
                        f"(TTL is {ttl_hours}h)"
                    ),
                    artifact=rel_path,
                    suggestion=(
                        "Consume the signal with `lexi iwh read` or "
                        "clean up with `lexictl iwh clean`."
                    ),
                )
            )

    return issues
