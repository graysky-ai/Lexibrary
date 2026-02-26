"""Individual validation check functions for library health.

Each check function follows the signature:
    check_*(project_root: Path, lexibrary_dir: Path) -> list[ValidationIssue]

Checks are grouped by severity:
- Error-severity: wikilink_resolution, file_existence, concept_frontmatter
- Warning-severity: hash_freshness, token_budgets, orphan_concepts, deprecated_concept_usage
- Info-severity: forward_dependencies, stack_staleness, aindex_coverage,
    bidirectional_deps, dangling_links, orphan_artifacts
"""

from __future__ import annotations

import contextlib
import logging
import re
import sqlite3
from pathlib import Path

import yaml

from lexibrary.artifacts.design_file_parser import (
    parse_design_file,
    parse_design_file_metadata,
)
from lexibrary.config.loader import load_config
from lexibrary.linkgraph.schema import SCHEMA_VERSION, check_schema_version, set_pragmas
from lexibrary.stack.parser import parse_stack_post
from lexibrary.tokenizer.approximate import ApproximateCounter
from lexibrary.utils.hashing import hash_file
from lexibrary.utils.paths import aindex_path
from lexibrary.validator.report import ValidationIssue
from lexibrary.wiki.index import ConceptIndex
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
    resolver = WikilinkResolver(index, stack_dir=stack_dir)

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

    # Design files live under lexibrary_dir/src/ mirroring the project structure
    src_dir = lexibrary_dir / "src"
    if not src_dir.is_dir():
        return issues

    for design_path in sorted(src_dir.rglob("*.md")):
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
    src_dir = lexibrary_dir / "src"
    if src_dir.is_dir():
        for file_path in sorted(src_dir.rglob("*.md")):
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
    src_dir = lexibrary_dir / "src"
    if src_dir.is_dir():
        for md_path in src_dir.rglob("*.md"):
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

    src_dir = lexibrary_dir / "src"
    if src_dir.is_dir():
        artifact_dirs.append((src_dir, "design"))

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
            design_file_path = lexibrary_dir / f"{ref_path}.md"

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
                    suggestion="Run 'lexi index' to generate .aindex files",
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
# Internal helpers
# ---------------------------------------------------------------------------


def _rel(path: Path, root: Path) -> str:
    """Return a relative path string, falling back to the full path."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _iter_design_files(lexibrary_dir: Path) -> list[Path]:
    """Iterate over design file paths in .lexibrary/, excluding special files."""
    if not lexibrary_dir.is_dir():
        return []

    results: list[Path] = []
    special_names = {"START_HERE.md"}

    for md_path in sorted(lexibrary_dir.rglob("*.md")):
        # Skip special files
        if md_path.name in special_names:
            continue
        # Skip stack posts
        if "stack" in md_path.relative_to(lexibrary_dir).parts:
            continue
        # Skip concepts
        if "concepts" in md_path.relative_to(lexibrary_dir).parts:
            continue
        results.append(md_path)

    return results


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
