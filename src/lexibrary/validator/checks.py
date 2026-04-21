"""Individual validation check functions for library health.

Each check function follows the signature:
    check_*(project_root: Path, lexibrary_dir: Path) -> list[ValidationIssue]

Checks are grouped by severity:
- Error-severity: wikilink_resolution, file_existence, concept_frontmatter,
    convention_frontmatter, design_frontmatter, stack_frontmatter,
    iwh_frontmatter, duplicate_aliases, duplicate_slugs,
    playbook_frontmatter, playbook_wikilinks
- Warning-severity: hash_freshness, token_budgets, orphan_concepts,
    deprecated_concept_usage, orphaned_designs, convention_orphaned_scope,
    stack_refs_validity, design_deps_existence, aindex_entries,
    bidirectional_deps
- Info-severity: forward_dependencies, stack_staleness,
    resolved_post_staleness, aindex_coverage,
    dangling_links, orphan_artifacts, orphaned_iwh,
    comment_accumulation, deprecated_ttl, stale_concept,
    supersession_candidate, convention_stale, convention_gap,
    convention_consistent_violation, lookup_token_budget_exceeded,
    orphaned_iwh_signals, playbook_staleness, playbook_deprecated_ttl
"""

from __future__ import annotations

import contextlib
import logging
import re
import sqlite3
from datetime import UTC, date
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
from lexibrary.ignore import create_ignore_matcher
from lexibrary.lifecycle.comments import comment_count
from lexibrary.lifecycle.convention_comments import convention_comment_count
from lexibrary.lifecycle.deprecation import _count_commits_since, check_ttl_expiry
from lexibrary.lifecycle.design_comments import design_comment_path
from lexibrary.linkgraph.schema import SCHEMA_VERSION, check_schema_version, set_pragmas
from lexibrary.playbooks.index import PlaybookIndex
from lexibrary.playbooks.parser import parse_playbook_file
from lexibrary.stack.parser import parse_stack_post
from lexibrary.tokenizer.approximate import ApproximateCounter
from lexibrary.utils.hashing import hash_file
from lexibrary.utils.paths import DESIGNS_DIR, aindex_path
from lexibrary.validator.report import ValidationIssue
from lexibrary.wiki.index import ConceptIndex
from lexibrary.wiki.parser import parse_concept_file
from lexibrary.wiki.patterns import HTML_COMMENT_RE as _HTML_COMMENT_RE
from lexibrary.wiki.patterns import WIKILINK_RE as _WIKILINK_RE
from lexibrary.wiki.resolver import UnresolvedLink, WikilinkResolver

logger = logging.getLogger(__name__)

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
    playbook_dir = lexibrary_dir / "playbooks"
    resolver = WikilinkResolver(
        index,
        stack_dir=stack_dir,
        convention_dir=convention_dir,
        playbook_dir=playbook_dir,
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
            try:
                post = parse_stack_post(md_path)
            except Exception:
                logger.warning("Skipping malformed Stack post: %s", md_path)
                continue
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
                    suggestion=(
                        f"Remove the design file manually, or restore the source file at "
                        f"'{design.source_path}'."
                    ),
                )
            )

    # Check Stack post refs
    if stack_dir.is_dir():
        for md_path in sorted(stack_dir.glob("ST-*-*.md")):
            try:
                post = parse_stack_post(md_path)
            except Exception:
                logger.warning("Skipping malformed Stack post: %s", md_path)
                continue
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
                            suggestion=(
                                f"Edit {rel_path} and remove or update the stale "
                                f"refs.files entry '{file_ref}'."
                            ),
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
                            suggestion=(
                                f"Edit {rel_path} and remove or update the stale "
                                f"refs.designs entry '{design_ref}'."
                            ),
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
                        f"Edit {rel_path} and add --- delimited YAML frontmatter "
                        f"with title, aliases, tags, status fields."
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
                    suggestion=f"Edit {rel_path} and fix the YAML syntax in the frontmatter block.",
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
                    suggestion=(
                        f"Edit {rel_path}: frontmatter must be a YAML key-value mapping "
                        f"(e.g. 'title: My Concept')."
                    ),
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
                        suggestion=(
                            f"Edit {rel_path} and add a '{field_name}:' field to the frontmatter."
                        ),
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
                        suggestion=(
                            f"Edit {rel_path} and set status to one of: "
                            f"{', '.join(sorted(valid_statuses))}."
                        ),
                    )
                )

        # id — must be present and match CN-NNN pattern (3+ digits)
        _cn_id_pattern = re.compile(r"^CN-\d{3,}$")
        if "id" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="concept_frontmatter",
                    message="Missing mandatory field: id",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'id:' in CN-NNN format (e.g. 'id: CN-001')."
                    ),
                )
            )
        elif not isinstance(data["id"], str) or not _cn_id_pattern.match(data["id"]):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="concept_frontmatter",
                    message=f"Invalid id format: {data['id']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and correct 'id:' to match CN-NNN format "
                        f"(e.g. 'id: CN-001')."
                    ),
                )
            )

    return issues


def check_convention_frontmatter(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Validate all convention files have mandatory frontmatter fields.

    Checks that every ``.md`` file in the conventions directory has valid YAML
    frontmatter with ``title``, ``status``, ``source``, ``scope``, ``tags``,
    and ``priority`` fields.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for invalid frontmatter.
    """
    issues: list[ValidationIssue] = []
    conventions_dir = lexibrary_dir / "conventions"
    if not conventions_dir.is_dir():
        return issues

    valid_statuses = {"draft", "active", "deprecated"}
    valid_sources = {"user", "agent", "config"}

    for md_path in sorted(conventions_dir.glob("*.md")):
        rel_path = _rel(md_path, project_root)

        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Could not read convention file",
                    artifact=rel_path,
                )
            )
            continue

        fm_match = _FRONTMATTER_RE.match(text)
        if not fm_match:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Missing YAML frontmatter",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add --- delimited YAML frontmatter "
                        f"with title, status, source, scope, tags, priority fields."
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
                    check="convention_frontmatter",
                    message="Invalid YAML in frontmatter",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and fix the YAML syntax in the frontmatter block.",
                )
            )
            continue

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Frontmatter is not a YAML mapping",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path}: frontmatter must be a YAML key-value mapping "
                        f"(e.g. 'title: My Convention')."
                    ),
                )
            )
            continue

        # title — must be present and a non-empty string
        if "title" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Missing mandatory field: title",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and add a 'title:' field to the frontmatter.",
                )
            )
        elif not isinstance(data["title"], str) or not data["title"].strip():
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Field 'title' must be a non-empty string",
                    artifact=rel_path,
                    suggestion=(f"Edit {rel_path} and set 'title:' to a non-empty string value."),
                )
            )

        # status — must be one of valid values
        if "status" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Missing mandatory field: status",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'status:' set to one of: "
                        f"{', '.join(sorted(valid_statuses))}."
                    ),
                )
            )
        elif data["status"] not in valid_statuses:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message=f"Invalid status: {data['status']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set status to one of: "
                        f"{', '.join(sorted(valid_statuses))}."
                    ),
                )
            )

        # source — must be one of valid values
        if "source" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Missing mandatory field: source",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'source:' set to one of: "
                        f"{', '.join(sorted(valid_sources))}."
                    ),
                )
            )
        elif data["source"] not in valid_sources:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message=f"Invalid source: {data['source']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set source to one of: "
                        f"{', '.join(sorted(valid_sources))}."
                    ),
                )
            )

        # scope — must be present and a string
        if "scope" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Missing mandatory field: scope",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'scope:' set to 'project' or a directory path."
                    ),
                )
            )
        elif not isinstance(data["scope"], str):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Field 'scope' must be a string",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set 'scope:' to a string "
                        f"(e.g. 'project' or 'src/lexibrary')."
                    ),
                )
            )

        # tags — must be present and a list
        if "tags" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Missing mandatory field: tags",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add a 'tags:' list field to the frontmatter."
                    ),
                )
            )
        elif not isinstance(data["tags"], list):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Field 'tags' must be a list",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and change 'tags:' to a YAML list (e.g. '- style')."
                    ),
                )
            )

        # priority — must be present and an integer
        if "priority" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Missing mandatory field: priority",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'priority:' set to an integer (e.g. 50)."
                    ),
                )
            )
        elif not isinstance(data["priority"], int):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Field 'priority' must be an integer",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set 'priority:' to an integer value (e.g. 50)."
                    ),
                )
            )

        # id — must be present and match CV-NNN pattern (3+ digits)
        _cv_id_pattern = re.compile(r"^CV-\d{3,}$")
        if "id" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message="Missing mandatory field: id",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'id:' in CV-NNN format (e.g. 'id: CV-001')."
                    ),
                )
            )
        elif not isinstance(data["id"], str) or not _cv_id_pattern.match(data["id"]):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="convention_frontmatter",
                    message=f"Invalid id format: {data['id']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and correct 'id:' to match CV-NNN format "
                        f"(e.g. 'id: CV-001')."
                    ),
                )
            )

    return issues


def check_design_frontmatter(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Validate all design files have mandatory frontmatter fields.

    Checks that every ``.md`` file in the designs directory (recursively) has
    valid YAML frontmatter with ``description``, ``updated_by``, and ``status``
    fields. Skips non-markdown files.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for invalid frontmatter.
    """
    issues: list[ValidationIssue] = []
    designs_dir = lexibrary_dir / DESIGNS_DIR
    if not designs_dir.is_dir():
        return issues

    valid_statuses = {"active", "unlinked", "deprecated"}
    valid_updated_by = {
        "archivist",
        "agent",
        "bootstrap-quick",
        "maintainer",
        "curator",
        "skeleton-fallback",
    }

    for md_path in sorted(designs_dir.rglob("*.md")):
        rel_path = _rel(md_path, project_root)

        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message="Could not read design file",
                    artifact=rel_path,
                )
            )
            continue

        fm_match = _FRONTMATTER_RE.match(text)
        if not fm_match:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message="Missing YAML frontmatter",
                    artifact=rel_path,
                    suggestion=(
                        f"Run: lexi design update <source-file> to regenerate, "
                        f"or edit {rel_path} to add --- delimited YAML frontmatter "
                        f"with description, updated_by, status fields."
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
                    check="design_frontmatter",
                    message="Invalid YAML in frontmatter",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and fix the YAML syntax in the frontmatter block.",
                )
            )
            continue

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message="Frontmatter is not a YAML mapping",
                    artifact=rel_path,
                    suggestion=(f"Edit {rel_path}: frontmatter must be a YAML key-value mapping."),
                )
            )
            continue

        # description — must be present and a non-empty string
        if "description" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message="Missing mandatory field: description",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add a 'description:' field "
                        f"summarising the file's role."
                    ),
                )
            )
        elif not isinstance(data["description"], str) or not data["description"].strip():
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message="Field 'description' must be a non-empty string",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set 'description:' to a non-empty string "
                        f"summarising the file's role."
                    ),
                )
            )

        # updated_by — must be one of valid values
        if "updated_by" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message="Missing mandatory field: updated_by",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'updated_by:' set to one of: "
                        f"{', '.join(sorted(valid_updated_by))}."
                    ),
                )
            )
        elif data["updated_by"] not in valid_updated_by:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message=f"Invalid updated_by: {data['updated_by']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set updated_by to one of: "
                        f"{', '.join(sorted(valid_updated_by))}."
                    ),
                )
            )

        # status — optional; when absent, treat as "active" (serializer omits the
        # default value). When present, validate against the allowed set.
        if "status" in data and data["status"] not in valid_statuses:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message=f"Invalid status: {data['status']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set status to one of: "
                        f"{', '.join(sorted(valid_statuses))}."
                    ),
                )
            )

        # id — must be present and match DS-NNN pattern (3+ digits)
        _ds_id_pattern = re.compile(r"^DS-\d{3,}$")
        if "id" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message="Missing mandatory field: id",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'id:' in DS-NNN format (e.g. 'id: DS-001')."
                    ),
                )
            )
        elif not isinstance(data["id"], str) or not _ds_id_pattern.match(data["id"]):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="design_frontmatter",
                    message=f"Invalid id format: {data['id']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and correct 'id:' to match DS-NNN format "
                        f"(e.g. 'id: DS-001')."
                    ),
                )
            )

    return issues


def check_stack_frontmatter(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Validate all Stack post files have mandatory frontmatter fields.

    Checks that every ``.md`` file in ``.lexibrary/stack/posts/`` has valid
    YAML frontmatter with ``id`` (ST-NNN), ``title``, ``tags`` (min 1),
    ``status``, ``created``, ``author``, and optionally ``resolution_type``.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for invalid frontmatter.
    """
    issues: list[ValidationIssue] = []
    posts_dir = lexibrary_dir / "stack" / "posts"
    if not posts_dir.is_dir():
        return issues

    valid_statuses = {"open", "resolved", "outdated", "duplicate", "stale"}
    valid_resolution_types = {
        "fix",
        "workaround",
        "wontfix",
        "cannot_reproduce",
        "by_design",
    }
    id_pattern = re.compile(r"^ST-\d{3,}$")

    for md_path in sorted(posts_dir.glob("*.md")):
        rel_path = _rel(md_path, project_root)

        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Could not read Stack post file",
                    artifact=rel_path,
                )
            )
            continue

        fm_match = _FRONTMATTER_RE.match(text)
        if not fm_match:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Missing YAML frontmatter",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add --- delimited YAML frontmatter "
                        f"with id, title, tags, status, created, author fields."
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
                    check="stack_frontmatter",
                    message="Invalid YAML in frontmatter",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and fix the YAML syntax in the frontmatter block.",
                )
            )
            continue

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Frontmatter is not a YAML mapping",
                    artifact=rel_path,
                    suggestion=(f"Edit {rel_path}: frontmatter must be a YAML key-value mapping."),
                )
            )
            continue

        # id — must be present and match ST-NNN pattern
        if "id" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Missing mandatory field: id",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'id:' in ST-NNN format (e.g. 'id: ST-042')."
                    ),
                )
            )
        elif not isinstance(data["id"], str) or not id_pattern.match(data["id"]):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message=f"Invalid id format: {data['id']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and correct 'id:' to match ST-NNN format "
                        f"(e.g. 'id: ST-042')."
                    ),
                )
            )

        # title — must be present and a non-empty string
        if "title" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Missing mandatory field: title",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and add a 'title:' field to the frontmatter.",
                )
            )
        elif not isinstance(data["title"], str) or not data["title"].strip():
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Field 'title' must be a non-empty string",
                    artifact=rel_path,
                    suggestion=(f"Edit {rel_path} and set 'title:' to a non-empty string."),
                )
            )

        # tags — must be present, a list, and have at least 1 element
        if "tags" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Missing mandatory field: tags",
                    artifact=rel_path,
                    suggestion=(f"Edit {rel_path} and add a 'tags:' list with at least one tag."),
                )
            )
        elif not isinstance(data["tags"], list):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Field 'tags' must be a list",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and change 'tags:' to a YAML list (e.g. '- bug')."
                    ),
                )
            )
        elif len(data["tags"]) < 1:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Field 'tags' must have at least 1 element",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and add at least one tag to the 'tags:' list.",
                )
            )

        # status — must be one of valid values
        if "status" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Missing mandatory field: status",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'status:' set to one of: "
                        f"{', '.join(sorted(valid_statuses))}."
                    ),
                )
            )
        elif data["status"] not in valid_statuses:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message=f"Invalid status: {data['status']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set status to one of: "
                        f"{', '.join(sorted(valid_statuses))}."
                    ),
                )
            )

        # created — must be present and a valid date
        if "created" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Missing mandatory field: created",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'created:' with a valid date (YYYY-MM-DD format)."
                    ),
                )
            )
        else:
            from datetime import date as date_type  # noqa: PLC0415
            from datetime import datetime as datetime_type  # noqa: PLC0415

            if not isinstance(data["created"], (date_type, datetime_type)):
                issues.append(
                    ValidationIssue(
                        severity="error",
                        check="stack_frontmatter",
                        message=f"Invalid created date: {data['created']}",
                        artifact=rel_path,
                        suggestion=(
                            f"Edit {rel_path} and set 'created:' to a valid date "
                            f"in YYYY-MM-DD format."
                        ),
                    )
                )

        # author — must be present and a non-empty string
        if "author" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Missing mandatory field: author",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and add an 'author:' field to the frontmatter.",
                )
            )
        elif not isinstance(data["author"], str) or not data["author"].strip():
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message="Field 'author' must be a non-empty string",
                    artifact=rel_path,
                    suggestion=(f"Edit {rel_path} and set 'author:' to a non-empty string."),
                )
            )

        # resolution_type — optional, but if present must be valid
        if (
            "resolution_type" in data
            and data["resolution_type"] is not None
            and data["resolution_type"] not in valid_resolution_types
        ):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="stack_frontmatter",
                    message=f"Invalid resolution_type: {data['resolution_type']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set resolution_type to one of: "
                        f"{', '.join(sorted(valid_resolution_types))}."
                    ),
                )
            )

    return issues


def check_iwh_frontmatter(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Validate all IWH signal files have mandatory fields.

    Finds all ``.iwh`` files under ``.lexibrary/`` (recursively), parses their
    YAML content, and validates ``author``, ``created`` (ISO 8601), and
    ``scope`` fields.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for invalid IWH files.
    """
    issues: list[ValidationIssue] = []
    if not lexibrary_dir.is_dir():
        return issues

    valid_scopes = {"warning", "incomplete", "blocked"}

    for iwh_path in sorted(lexibrary_dir.rglob(".iwh")):
        if not iwh_path.is_file():
            continue

        rel_path = _rel(iwh_path, project_root)

        try:
            text = iwh_path.read_text(encoding="utf-8")
        except OSError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="iwh_frontmatter",
                    message="Could not read IWH file",
                    artifact=rel_path,
                )
            )
            continue

        # IWH files use frontmatter-style YAML; fall back to raw content
        fm_match = _FRONTMATTER_RE.match(text)
        yaml_text = fm_match.group(1) if fm_match else text

        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="iwh_frontmatter",
                    message="Invalid YAML in IWH file",
                    artifact=rel_path,
                    suggestion=(
                        f"Delete and recreate via: lexi iwh write "
                        f"{str(iwh_path.parent.relative_to(lexibrary_dir))} "
                        f"--scope incomplete --body 'description'"
                    ),
                )
            )
            continue

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="iwh_frontmatter",
                    message="IWH file content is not a YAML mapping",
                    artifact=rel_path,
                    suggestion=(
                        f"Delete and recreate via: lexi iwh write "
                        f"{str(iwh_path.parent.relative_to(lexibrary_dir))} "
                        f"--scope incomplete --body 'description'"
                    ),
                )
            )
            continue

        # author — must be present and a non-empty string
        if "author" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="iwh_frontmatter",
                    message="Missing mandatory field: author",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and add an 'author:' field.",
                )
            )
        elif not isinstance(data["author"], str) or not data["author"].strip():
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="iwh_frontmatter",
                    message="Field 'author' must be a non-empty string",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and set 'author:' to a non-empty string.",
                )
            )

        # created — must be present and a valid ISO 8601 datetime
        if "created" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="iwh_frontmatter",
                    message="Missing mandatory field: created",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'created:' with an ISO 8601 datetime "
                        f"(e.g. '2026-01-15T12:00:00Z')."
                    ),
                )
            )
        else:
            from datetime import date as date_type  # noqa: PLC0415
            from datetime import datetime as datetime_type  # noqa: PLC0415

            if not isinstance(data["created"], (date_type, datetime_type)):
                created_val = data["created"]
                if isinstance(created_val, str):
                    try:
                        datetime_type.fromisoformat(created_val)
                    except (ValueError, TypeError):
                        issues.append(
                            ValidationIssue(
                                severity="error",
                                check="iwh_frontmatter",
                                message=f"Invalid created datetime: {created_val}",
                                artifact=rel_path,
                                suggestion=(
                                    f"Edit {rel_path} and set 'created:' to a valid "
                                    f"ISO 8601 datetime (e.g. '2026-01-15T12:00:00Z')."
                                ),
                            )
                        )
                else:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            check="iwh_frontmatter",
                            message=f"Invalid created datetime: {data['created']}",
                            artifact=rel_path,
                            suggestion=(
                                f"Edit {rel_path} and set 'created:' to a valid "
                                f"ISO 8601 datetime (e.g. '2026-01-15T12:00:00Z')."
                            ),
                        )
                    )

        # scope — must be one of valid values
        if "scope" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="iwh_frontmatter",
                    message="Missing mandatory field: scope",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'scope:' set to one of: "
                        f"{', '.join(sorted(valid_scopes))}."
                    ),
                )
            )
        elif data["scope"] not in valid_scopes:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="iwh_frontmatter",
                    message=f"Invalid scope: {data['scope']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set scope to one of: "
                        f"{', '.join(sorted(valid_scopes))}."
                    ),
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Infrastructure checks (error + warning severity)
# ---------------------------------------------------------------------------


def check_config_valid(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Re-validate .lexibrary/config.yaml with the LexibraryConfig model.

    Loads the project config YAML and validates it with Pydantic.  Reports
    error-severity issues for missing files, YAML syntax errors, and
    per-field Pydantic validation failures.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for config problems.
    """
    from pydantic import ValidationError  # noqa: PLC0415

    from lexibrary.config.schema import LexibraryConfig  # noqa: PLC0415

    issues: list[ValidationIssue] = []
    config_path = lexibrary_dir / "config.yaml"
    artifact = _rel(config_path, project_root)

    if not config_path.exists():
        issues.append(
            ValidationIssue(
                severity="error",
                check="config_valid",
                message="Config file not found",
                artifact=artifact,
                suggestion=(
                    "Ask the user to run `lexictl init` to initialise "
                    "the library and create config.yaml."
                ),
            )
        )
        return issues

    # Try to read and parse YAML
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        issues.append(
            ValidationIssue(
                severity="error",
                check="config_valid",
                message=f"Could not read config file: {exc}",
                artifact=artifact,
            )
        )
        return issues

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        issues.append(
            ValidationIssue(
                severity="error",
                check="config_valid",
                message=f"Invalid YAML syntax: {exc}",
                artifact=artifact,
                suggestion=f"Edit {artifact} and fix the YAML syntax error reported above.",
            )
        )
        return issues

    if data is None:
        data = {}
    if not isinstance(data, dict):
        issues.append(
            ValidationIssue(
                severity="error",
                check="config_valid",
                message="Config file is not a YAML mapping",
                artifact=artifact,
                suggestion=(
                    f"Edit {artifact}: the file must contain a YAML key-value mapping "
                    f"(not a list or scalar)."
                ),
            )
        )
        return issues

    # Validate with Pydantic
    try:
        config = LexibraryConfig.model_validate(data)
    except ValidationError as exc:
        for error in exc.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="config_valid",
                    message=f"Validation error at '{field_path}': {error['msg']}",
                    artifact=artifact,
                )
            )
        return issues

    # Scope-root resolution guards (path-traversal, nested-roots, duplicates)
    # live in ``resolved_scope_roots`` rather than Pydantic validators because
    # they depend on the concrete ``project_root``. Surface them here so
    # ``lexi validate`` reports a structured error instead of crashing later
    # in a downstream command.
    try:
        config.resolved_scope_roots(project_root)
    except ValueError as exc:
        issues.append(
            ValidationIssue(
                severity="error",
                check="config_valid",
                message=f"Validation error at 'scope_roots': {exc}",
                artifact=artifact,
            )
        )

    return issues


def check_lexignore_syntax(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Validate each line of .lexignore as a gitignore pattern.

    Reads the ``.lexignore`` file in the project root (if it exists),
    compiles each non-empty, non-comment line as a gitignore pattern via
    pathspec, and reports lines that fail to compile at warning severity.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for invalid patterns.
    """
    import pathspec  # noqa: PLC0415

    issues: list[ValidationIssue] = []
    lexignore_path = project_root / ".lexignore"

    if not lexignore_path.exists():
        return issues

    try:
        text = lexignore_path.read_text(encoding="utf-8")
    except OSError:
        return issues

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        try:
            pathspec.PathSpec.from_lines("gitignore", [line])
        except Exception:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="lexignore_syntax",
                    message=f"Invalid gitignore pattern on line {line_no}: {line!r}",
                    artifact=".lexignore",
                    suggestion=(
                        f"Edit .lexignore line {line_no} and fix or remove the "
                        f"invalid pattern {line!r}."
                    ),
                )
            )

    return issues


def check_linkgraph_version(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Compare the stored linkgraph schema version to the current constant.

    Opens the SQLite database at ``.lexibrary/index.db``, reads the stored
    schema version from the ``meta`` table, and reports an error-severity
    issue if it does not match the current ``SCHEMA_VERSION``.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for version mismatches.
    """
    issues: list[ValidationIssue] = []
    db_path = lexibrary_dir / _INDEX_DB_NAME

    if not db_path.exists():
        return issues

    artifact = _rel(db_path, project_root)

    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error:
        issues.append(
            ValidationIssue(
                severity="error",
                check="linkgraph_version",
                message="Could not open linkgraph database",
                artifact=artifact,
                suggestion=(
                    "Delete the index file and ask the user to run `lexictl update` to rebuild it."
                ),
            )
        )
        return issues

    try:
        set_pragmas(conn)
        stored_version = check_schema_version(conn)
    except sqlite3.Error:
        issues.append(
            ValidationIssue(
                severity="error",
                check="linkgraph_version",
                message="Could not read schema version from linkgraph database",
                artifact=artifact,
                suggestion=(
                    "Delete the index file and ask the user to run `lexictl update` to rebuild it."
                ),
            )
        )
        return issues
    finally:
        conn.close()

    if stored_version is None:
        issues.append(
            ValidationIssue(
                severity="error",
                check="linkgraph_version",
                message="No schema version found in linkgraph database",
                artifact=artifact,
                suggestion=(
                    "Delete the index file and ask the user to run `lexictl update` to rebuild it."
                ),
            )
        )
        return issues

    if stored_version != SCHEMA_VERSION:
        issues.append(
            ValidationIssue(
                severity="error",
                check="linkgraph_version",
                message=(
                    f"Schema version mismatch: stored={stored_version}, current={SCHEMA_VERSION}"
                ),
                artifact=artifact,
                suggestion="Ask the user to run `lexictl update` to rebuild the linkgraph index.",
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
                    suggestion=(
                        f"Run: lexi design update {metadata.source} to refresh the design file."
                    ),
                )
            )

    return issues


def check_stale_agent_design(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Check that agent- or maintainer-edited design files have fresh source hashes.

    Iterates all design files, filters to those where ``updated_by`` is
    ``"agent"`` or ``"maintainer"``, and compares the stored ``source_hash``
    against the current SHA-256 of the source file.  Returns warning-severity
    issues for every mismatch so that human-authored design notes are not
    silently left pointing at stale code.

    Archivist-owned files (``updated_by`` is ``"archivist"``,
    ``"bootstrap-quick"``, ``"skeleton-fallback"``, etc.) are intentionally
    skipped — those are already covered by ``check_hash_freshness``, and the
    remediation path (``lexictl update``) is different.

    Skips design files whose source no longer exists on disk (that is handled
    by the ``file_existence`` check).
    """
    issues: list[ValidationIssue] = []

    designs_dir = lexibrary_dir / DESIGNS_DIR
    if not designs_dir.is_dir():
        return issues

    for design_path in sorted(designs_dir.rglob("*.md")):
        # Read frontmatter to determine who last edited this design file
        frontmatter = parse_design_file_frontmatter(design_path)
        if frontmatter is None:
            continue
        if frontmatter.updated_by not in ("agent", "maintainer"):
            continue

        # Read the staleness metadata block for source path and stored hash
        metadata = parse_design_file_metadata(design_path)
        if metadata is None:
            continue

        source_path = project_root / metadata.source
        if not source_path.is_file():
            # Missing source is handled by check_file_existence, not here
            continue

        current_hash = hash_file(source_path)
        if current_hash == metadata.source_hash:
            continue

        rel_design = str(design_path.relative_to(lexibrary_dir))
        issues.append(
            ValidationIssue(
                severity="warning",
                check="stale_agent_design",
                message=(
                    f"Design file last edited by {frontmatter.updated_by!r} is stale: "
                    f"source has changed since the design was written "
                    f"(stored {metadata.source_hash[:12]}... "
                    f"vs current {current_hash[:12]}...)"
                ),
                artifact=rel_design,
                suggestion=(
                    f"Run: lexictl curate {metadata.source} to regenerate the design "
                    f"file, then review agent-authored notes to ensure they still apply."
                ),
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
                        suggestion=(
                            "Trim the design file body, or increase "
                            "token_budgets.design_file_tokens in .lexibrary/config.yaml."
                        ),
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
                        suggestion=(
                            "Trim the concept body, or increase "
                            "token_budgets.concept_file_tokens in .lexibrary/config.yaml."
                        ),
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
                    suggestion=(
                        "Raise `token_budgets.aindex_tokens` in `.lexibrary/config.yaml`, "
                        "or shorten the per-child billboard descriptions in this directory's "
                        "source design files (each child's description is sourced from its "
                        "design file's `description` frontmatter field)."
                    ),
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

    Honours ``concepts.orphan_verify_ttl_days`` from config: when a concept
    has a ``last_verified`` date and ``(date.today() - last_verified).days``
    is within the configured TTL window, the orphan warning is suppressed.
    Setting ``orphan_verify_ttl_days`` to 0 disables TTL honouring and always
    emits the warning regardless of ``last_verified``.
    """
    issues: list[ValidationIssue] = []

    concepts_dir = lexibrary_dir / "concepts"
    if not concepts_dir.is_dir():
        return issues

    config = load_config(project_root)
    orphan_verify_ttl_days = config.concepts.orphan_verify_ttl_days

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
            text = _HTML_COMMENT_RE.sub("", text)
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
            text = _HTML_COMMENT_RE.sub("", text)
            for match in _WIKILINK_RE.findall(text):
                referenced.add(match.strip().lower())

    # Scan concept files themselves for cross-references
    for md_path in concepts_dir.glob("*.md"):
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _HTML_COMMENT_RE.sub("", text)
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
            # TTL honouring: when orphan_verify_ttl_days > 0 and the concept has a
            # last_verified date within that window, suppress the warning. The
            # operator has recently vouched for this concept even though nothing
            # currently links to it. Setting orphan_verify_ttl_days to 0 disables
            # TTL honouring entirely.
            if orphan_verify_ttl_days > 0 and concept.frontmatter.last_verified is not None:
                days_since_verified = (date.today() - concept.frontmatter.last_verified).days
                if days_since_verified <= orphan_verify_ttl_days:
                    continue

            concept_slug = next(
                (
                    p.stem
                    for p in concepts_dir.glob("*.md")
                    if p.stem.lower() == concept.frontmatter.title.lower().replace(" ", "-")
                ),
                concept.frontmatter.title,
            )
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="orphan_concepts",
                    message="Concept has no inbound wikilink references.",
                    artifact=f"concepts/{concept.frontmatter.title}",
                    suggestion=(
                        f"Add [[{concept.frontmatter.title}]] to a relevant design file via: "
                        f"lexi concept link {concept_slug} <source-file>. "
                        f"Or deprecate it: lexi concept deprecate {concept_slug}"
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
                        suggestion=(
                            f"Edit the design file and remove or correct the dependency "
                            f"on '{dep_stripped}'."
                        ),
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
        try:
            post = parse_stack_post(post_path)
        except Exception:
            logger.warning("Skipping malformed Stack post: %s", post_path)
            continue
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
                    suggestion=(
                        "Run: lexi lookup <stale-file> to review, then "
                        "run: lexi stack comment <id> --body 'Verified still applies' "
                        "or run: lexi stack mark-outdated <id> if no longer relevant."
                    ),
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
        try:
            post = parse_stack_post(post_path)
        except Exception:
            logger.warning("Skipping malformed Stack post: %s", post_path)
            continue
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
    """Find directories within any declared scope root that lack .aindex files.

    Walks each declared scope root's directory tree (iterating
    ``config.resolved_scope_roots(project_root).resolved``) and checks that
    each directory has a corresponding ``.aindex`` file in ``.lexibrary/``.
    A directory under ``baml_src/`` lacking an ``.aindex`` is reported just as
    one under ``src/`` would be.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for unindexed directories.
    """
    issues: list[ValidationIssue] = []

    # Load config to discover declared scope roots. If the config is broken,
    # fall back to ``project_root`` as a single scope root so we still produce
    # output rather than silently no-oping.
    try:
        config = load_config(project_root)
    except Exception:
        config = None

    if config is None:
        roots: list[Path] = [project_root]
    else:
        try:
            roots = config.resolved_scope_roots(project_root).resolved
        except Exception:
            # Resolution failures (path traversal / nesting / duplicates) are
            # surfaced by ``check_config_valid``; this check should not raise.
            return issues

    seen: set[Path] = set()
    for scope_root in roots:
        if not scope_root.is_dir():
            continue
        # Walk directories, skipping hidden dirs and .lexibrary itself
        for dirpath in _iter_directories(scope_root, project_root, lexibrary_dir):
            # When two declared roots are siblings the same dirpath cannot
            # appear twice, but the nested-roots guard would also prevent
            # overlap. The de-duplication here is a belt-and-braces guard
            # against a future change in the resolver.
            if dirpath in seen:
                continue
            seen.add(dirpath)

            expected_aindex = aindex_path(project_root, dirpath)
            if not expected_aindex.exists():
                dir_rel = str(dirpath.relative_to(project_root))
                issues.append(
                    ValidationIssue(
                        severity="info",
                        check="aindex_coverage",
                        message=f"Directory not indexed: {dir_rel}",
                        artifact=dir_rel,
                        suggestion=(
                            f"Ask the user to run `lexictl update` to index the "
                            f"directory '{dir_rel}'."
                        ),
                    )
                )

    return issues


def check_bidirectional_deps(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Compare design file dependency and dependent lists against the ``ast_import`` graph.

    For each design file, parses the ``## Dependencies`` and ``## Dependents``
    sections and diffs them in both directions against the link graph:

    * **Dependencies drift** -- forward ``ast_import`` edges outbound from the
      source file that do not match ``design.dependencies``.
    * **Dependents drift** -- reverse ``ast_import`` edges (modules that
      import this source) that do not match ``design.dependents``. Skipped
      when the design's ``StalenessMetadata.dependents_complete`` is
      ``False`` -- the list was produced without a link graph, so it is
      authoritatively empty and any mismatch is a false positive.

    Mismatches in either direction produce warning-severity issues and the
    ``message`` field distinguishes the drift direction (``dependencies
    drift: ...`` vs ``dependents drift: ...``).

    Returns an empty list when the index is absent, corrupt, or has a
    schema version mismatch -- graceful degradation per D2.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for dependency / dependent
        mismatches.
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

        # Build two lookups in a single pass:
        #   graph_imports: source artifact path -> set of ast_import target paths (forward)
        #   graph_importers: target artifact path -> set of ast_import source paths (reverse)
        graph_imports: dict[str, set[str]] = {}
        graph_importers: dict[str, set[str]] = {}
        rows = conn.execute(
            "SELECT a_src.path, a_tgt.path "
            "FROM links AS l "
            "JOIN artifacts AS a_src ON l.source_id = a_src.id "
            "JOIN artifacts AS a_tgt ON l.target_id = a_tgt.id "
            "WHERE l.link_type = 'ast_import'"
        ).fetchall()
        for src_path, tgt_path in rows:
            graph_imports.setdefault(src_path, set()).add(tgt_path)
            graph_importers.setdefault(tgt_path, set()).add(src_path)

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
        # ``rel_design`` is lexibrary-relative (e.g. "designs/src/foo.py.md")
        # to match the contract consumed by ``validator.fixes.fix_bidirectional_deps``
        # and mirror the path convention used by ``check_orphaned_designs``.
        rel_design = str(design_path.relative_to(lexibrary_dir))

        # --- Dependencies (forward) ------------------------------------------------
        design_deps: set[str] = set()
        for dep in design.dependencies:
            dep_stripped = dep.strip()
            if dep_stripped and dep_stripped != "(none)":
                design_deps.add(dep_stripped)

        graph_deps = graph_imports.get(source_path, set())

        # Direction 1a: dep listed in design file but not found in graph
        for dep in sorted(design_deps - graph_deps):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="bidirectional_deps",
                    message=(
                        f"dependencies drift: {dep} is listed in the design file "
                        f"but not found as an ast_import link in the graph"
                    ),
                    artifact=rel_design,
                    suggestion=(
                        "The link graph index may be stale; ask the user "
                        "to run `lexictl update` to rebuild it."
                    ),
                )
            )

        # Direction 1b: graph link exists but not listed in design file
        for dep in sorted(graph_deps - design_deps):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="bidirectional_deps",
                    message=(
                        f"dependencies drift: {dep} exists in the link graph "
                        f"but is not listed in the design file dependencies"
                    ),
                    artifact=rel_design,
                    suggestion=(
                        f"Run: lexi design update {source_path} to regenerate "
                        f"the design file with current import data, or ask the user to run "
                        f"`lexictl update` to rebuild the index."
                    ),
                )
            )

        # --- Dependents (reverse) --------------------------------------------------
        # Skip when the design's dependents list was produced without a link graph --
        # the list is authoritatively empty and any reverse-diff would be noise.
        if not design.metadata.dependents_complete:
            continue

        design_dependents: set[str] = set()
        for dep in design.dependents:
            dep_stripped = dep.strip()
            if dep_stripped and dep_stripped != "(none)":
                design_dependents.add(dep_stripped)

        graph_dependents = graph_importers.get(source_path, set())

        # Direction 2a: dependent listed in design file but not found in graph
        for dep in sorted(design_dependents - graph_dependents):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="bidirectional_deps",
                    message=(
                        f"dependents drift: {dep} is listed as a dependent in the "
                        f"design file but no ast_import edge from that source is in the graph"
                    ),
                    artifact=rel_design,
                    suggestion=(
                        "The link graph index may be stale; ask the user "
                        "to run `lexictl update` to rebuild it."
                    ),
                )
            )

        # Direction 2b: graph reverse edge exists but not listed in design file
        for dep in sorted(graph_dependents - design_dependents):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="bidirectional_deps",
                    message=(
                        f"dependents drift: {dep} imports this source in the link graph "
                        f"but is not listed in the design file dependents"
                    ),
                    artifact=rel_design,
                    suggestion=(
                        f"Run: lexi design update {source_path} to regenerate the "
                        f"design file with current reverse-import data, or ask the user "
                        f"to run `lexictl backfill-dependents` / `lexictl update`."
                    ),
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
                    suggestion=(
                        "Ask the user to run `lexictl update` to rebuild "
                        "the index and remove stale entries."
                    ),
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
                        f"Orphaned .aindex file: source directory {relative_dir} no longer exists"
                    ),
                    artifact=rel_aindex,
                    suggestion=(
                        "Ask the user to run `lexictl update` to remove "
                        f"this orphaned .aindex file, "
                        f"or delete it manually: {rel_aindex}"
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
                        f"Orphaned .iwh file: source directory {relative_dir} no longer exists"
                    ),
                    artifact=rel_iwh,
                    suggestion=(
                        f"Ask the user to run `lexictl update` to remove this orphaned .iwh file, "
                        f"or delete it manually: {rel_iwh}"
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

    # The prefix used by the project root in artifact paths stored in the DB
    lexibrary_prefix = ".lexibrary/"

    # Check each artifact's backing file
    for artifact_path, kind in rows:
        full_path = project_root / artifact_path
        if not full_path.exists():
            # Normalise to lexibrary-relative format so fixers can resolve
            # the path as ``project_root / ".lexibrary" / artifact``.
            # The DB stores paths like ``.lexibrary/designs/src/foo.py.md``
            # but fixers expect ``designs/src/foo.py.md``.
            normalized_path = artifact_path
            if normalized_path.startswith(lexibrary_prefix):
                normalized_path = normalized_path[len(lexibrary_prefix) :]

            issues.append(
                ValidationIssue(
                    severity="info",
                    check="orphan_artifacts",
                    message=(f"Index contains {kind} artifact for deleted file: {artifact_path}"),
                    artifact=normalized_path,
                    suggestion=(
                        "Ask the user to run `lexictl update` to rebuild "
                        "the index and prune stale entries."
                    ),
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
                    message=(f"Design file references missing source: {source_rel}"),
                    artifact=rel_design,
                    suggestion=(
                        "Ask the user to run `lexictl update` to trigger "
                        f"the deprecation workflow for "
                        f"'{source_rel}' and mark the design file as deprecated."
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
                    message=(f"Design file has {count} comments (threshold: {threshold})"),
                    artifact=rel_design,
                    suggestion=(
                        f"Run: lexi design comment {rel_design.replace('designs/', '', 1)} "
                        f"--body 'Summary of changes' to add context, or manually review "
                        f"and prune {rel_design}."
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
                    message=(f"Deprecated design file has exceeded TTL ({ttl_commits} commits)"),
                    artifact=rel_design,
                    suggestion=(
                        "Ask the user to run `lexictl update` to "
                        f"hard-delete the expired deprecated "
                        f"design file '{rel_design}'."
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
                    message=(f"Active concept references missing file(s): {missing_str}"),
                    artifact=f"concepts/{concept.frontmatter.title}",
                    suggestion=(
                        f"Review and update the linked file references in "
                        f"concepts/{concept.frontmatter.title}.md, or deprecate: "
                        f"lexi concept deprecate "
                        f"{concept.frontmatter.title.lower().replace(' ', '-')}"
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
        active_concepts.append((concept.frontmatter.title, list(concept.frontmatter.aliases)))

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
                            "Review whether one should supersede the other, then run: "
                            "lexi concept deprecate <slug> --superseded-by <other-slug>"
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
    directory exists under the project root.  Multi-path scopes (comma-
    separated) are supported — each individual path is validated.
    Conventions with ``scope == "project"`` are always valid and are
    skipped.  Deprecated conventions are also skipped.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for orphaned scopes.
    """
    from lexibrary.artifacts.convention import split_scope

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

        # Check each scope path individually
        scope_paths = split_scope(scope)
        missing = [p for p in scope_paths if not (project_root / p).is_dir()]
        if missing:
            rel_convention = str(md_path.relative_to(lexibrary_dir))
            missing_str = ", ".join(missing)
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="convention_orphaned_scope",
                    message=(
                        f"Convention scope director{'ies do' if len(missing) > 1 else 'y does'} "
                        f"not exist: {missing_str}"
                    ),
                    artifact=rel_convention,
                    suggestion=(
                        f"Update the scope in {rel_convention}, or deprecate the convention: "
                        f"lexi convention deprecate {md_path.stem}"
                    ),
                )
            )

    return issues


def check_convention_stale(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect active conventions whose scope directories are all empty.

    An active convention whose scope directories all exist but none contain
    source files (non-directory entries) may be stale.  Multi-path scopes
    (comma-separated) are supported — the convention is only flagged if
    *every* scope directory is empty.  Conventions with
    ``scope == "project"`` are skipped (project-wide conventions are always
    relevant). Deprecated and draft conventions are also skipped.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for stale conventions.
    """
    from lexibrary.artifacts.convention import split_scope

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

        scope_paths = split_scope(scope)

        # Check each scope path — if any has files, the convention is not stale
        any_has_files = False
        all_exist = True
        for sp in scope_paths:
            scope_dir = project_root / sp
            if not scope_dir.is_dir():
                # If any directory doesn't exist, orphaned_scope covers it
                all_exist = False
                continue
            try:
                for child in scope_dir.iterdir():
                    if child.is_file():
                        any_has_files = True
                        break
            except PermissionError:
                continue
            if any_has_files:
                break

        if all_exist and not any_has_files:
            rel_convention = str(md_path.relative_to(lexibrary_dir))
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="convention_stale",
                    message=(
                        f"Active convention scoped to '{scope}' "
                        f"but scope directories contain no source files"
                    ),
                    artifact=rel_convention,
                    suggestion=(
                        f"Review whether this convention is still relevant, or deprecate it: "
                        f"lexi convention deprecate {md_path.stem}"
                    ),
                )
            )

    return issues


def check_convention_gap(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect directories with many source files but no applicable conventions.

    Walks each declared scope root's source tree and flags directories that
    contain 5 or more source files but have zero conventions applicable to
    them (via scope matching). This is a nudge to consider adding conventions
    for high-traffic directories.

    Convention applicability is resolved through
    :meth:`ConventionIndex.find_by_any_scope`, which delegates owning-root
    discovery to :func:`find_owning_root` and respects the always-match
    semantics of ``scope: "."`` conventions.

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

    # Load config to discover declared scope roots.
    try:
        config = load_config(project_root)
    except Exception:
        config = None

    if config is None:
        # Config load failed: fall back to project root as the single scope
        # root so the check still runs rather than silently skipping.
        from lexibrary.config.schema import LexibraryConfig  # noqa: PLC0415

        config = LexibraryConfig()
        roots = [project_root]
    else:
        try:
            roots = config.resolved_scope_roots(project_root).resolved
        except Exception:
            # Config-resolution failures (path traversal / nesting / duplicates)
            # are surfaced by ``check_config_valid``; this check should not raise.
            return issues

    file_threshold = 5

    seen: set[Path] = set()
    for scope_root in roots:
        if not scope_root.is_dir():
            continue
        for directory in _iter_directories(scope_root, project_root, lexibrary_dir):
            if directory in seen:
                continue
            seen.add(directory)

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

            # Check if any active (non-deprecated) conventions apply to this
            # directory. Use a representative file path for scope matching;
            # ``find_by_any_scope`` resolves the owning root internally.
            rel_dir = str(directory.relative_to(project_root))
            representative = f"{rel_dir}/example.py" if rel_dir != "." else "example.py"
            applicable = conv_index.find_by_any_scope(representative, config.scope_roots)

            # Filter to only active conventions
            active_applicable = [c for c in applicable if c.frontmatter.status == "active"]

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
                            f"Run: lexi convention new --scope {rel_dir} "
                            f"--body 'Describe the coding standard for this directory.'"
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
                        f"Review comments in {rel_convention} to determine if the rule needs "
                        f"revision, then either update it in place or deprecate: "
                        f"lexi convention deprecate {md_path.stem}"
                    ),
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Error-severity: cross-artifact checks
# ---------------------------------------------------------------------------


def check_duplicate_aliases(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect duplicate aliases and titles across concept files.

    Collects every concept title and alias, then reports when two or more
    concept files claim the same name (case-insensitive).

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for duplicate aliases.
    """
    issues: list[ValidationIssue] = []
    concepts_dir = lexibrary_dir / "concepts"
    if not concepts_dir.is_dir():
        return issues

    # Map lowercase alias/title -> list of (original_name, source_file_stem)
    seen: dict[str, list[tuple[str, str]]] = {}

    for md_path in sorted(concepts_dir.glob("*.md")):
        concept = parse_concept_file(md_path)
        if concept is None:
            continue

        file_stem = md_path.stem
        title = concept.frontmatter.title
        names_to_check = [title] + list(concept.frontmatter.aliases)

        for name in names_to_check:
            key = name.strip().lower()
            if not key:
                continue
            seen.setdefault(key, []).append((name, file_stem))

    # Report duplicates
    for _key, entries in sorted(seen.items()):
        if len(entries) <= 1:
            continue
        files = [stem for _, stem in entries]
        for original_name, file_stem in entries:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="duplicate_aliases",
                    message=(
                        f"Alias/title '{original_name}' is duplicated "
                        f"across files: {', '.join(sorted(set(files)))}"
                    ),
                    artifact=f"concepts/{file_stem}.md",
                    suggestion=(
                        f"Edit {f'concepts/{file_stem}.md'} and remove or rename the "
                        f"duplicate alias/title '{original_name}'."
                    ),
                )
            )

    return issues


def check_duplicate_slugs(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect duplicate slugs within a single artifact type.

    Artifact files may have ID-prefixed filenames (e.g. ``CN-001-error-handling.md``).
    This check strips the ID prefix before comparing slugs, then flags cases where
    two or more files *of the same artifact type* share the same slug.

    Slugs are only required to be unique within a type because:
    - Filesystem paths are unique via ID prefix (e.g. ``CN-019-…`` vs ``PB-004-…``).
    - Wikilinks resolve by title, not slug.
    - Per-type index lookups (``ConceptIndex.find()``, ``PlaybookIndex.find()``)
      operate in separate namespaces.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for within-type duplicate slugs.
    """
    issues: list[ValidationIssue] = []

    # Regex to strip ID prefix from filenames: XX-NNN- at the start of the stem
    _id_prefix_re = re.compile(r"^[A-Z]{2}-\d{3,}-")

    # Collect slugs per artifact type: (kind, slug) -> list of rel_path
    slug_sources: dict[tuple[str, str], list[str]] = {}

    artifact_dirs = {
        "concepts": lexibrary_dir / "concepts",
        "conventions": lexibrary_dir / "conventions",
        "playbooks": lexibrary_dir / "playbooks",
    }

    for kind, artifact_dir in artifact_dirs.items():
        if not artifact_dir.is_dir():
            continue
        for md_path in sorted(artifact_dir.glob("*.md")):
            stem = md_path.stem
            # Strip ID prefix if present (e.g. CN-001-error-handling -> error-handling)
            slug = _id_prefix_re.sub("", stem)
            rel_path = f"{kind}/{md_path.name}"
            slug_sources.setdefault((kind, slug), []).append(rel_path)

    for (kind, slug), sources in sorted(slug_sources.items()):
        if len(sources) <= 1:
            continue
        for source in sources:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="duplicate_slugs",
                    message=(
                        f"Slug '{slug}' is used by multiple {kind} files: "
                        f"{', '.join(sorted(sources))}"
                    ),
                    artifact=source,
                    suggestion=(
                        f"Rename one of {', '.join(sorted(sources))} to use a unique slug."
                    ),
                )
            )

    return issues


def check_artifact_id_uniqueness(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect duplicate artifact IDs across all artifact types.

    Scans frontmatter ``id`` fields in concepts, conventions, playbooks,
    stack posts, and design files. Reports an error when two or more
    artifacts share the same ID.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for duplicate IDs.
    """
    issues: list[ValidationIssue] = []

    # id -> list of relative paths that claim it
    id_sources: dict[str, list[str]] = {}

    # Scan flat artifact directories (concepts, conventions, playbooks)
    flat_dirs = {
        "concepts": lexibrary_dir / "concepts",
        "conventions": lexibrary_dir / "conventions",
        "playbooks": lexibrary_dir / "playbooks",
    }
    for kind, artifact_dir in flat_dirs.items():
        if not artifact_dir.is_dir():
            continue
        for md_path in sorted(artifact_dir.glob("*.md")):
            artifact_id = _extract_frontmatter_id(md_path)
            if artifact_id is not None:
                rel_path = f"{kind}/{md_path.name}"
                id_sources.setdefault(artifact_id, []).append(rel_path)

    # Scan stack posts
    posts_dir = lexibrary_dir / "stack" / "posts"
    if posts_dir.is_dir():
        for md_path in sorted(posts_dir.glob("*.md")):
            artifact_id = _extract_frontmatter_id(md_path)
            if artifact_id is not None:
                rel_path = f"stack/posts/{md_path.name}"
                id_sources.setdefault(artifact_id, []).append(rel_path)

    # Scan design files (recursive)
    designs_dir = lexibrary_dir / DESIGNS_DIR
    if designs_dir.is_dir():
        for md_path in sorted(designs_dir.rglob("*.md")):
            artifact_id = _extract_frontmatter_id(md_path)
            if artifact_id is not None:
                rel_path = str(md_path.relative_to(lexibrary_dir))
                id_sources.setdefault(artifact_id, []).append(rel_path)

    for artifact_id, sources in sorted(id_sources.items()):
        if len(sources) <= 1:
            continue
        for source in sources:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="artifact_id_uniqueness",
                    message=(
                        f"Duplicate artifact ID '{artifact_id}' found in: "
                        f"{', '.join(sorted(sources))}"
                    ),
                    artifact=source,
                    suggestion=(
                        f"Assign a unique ID to each artifact. "
                        f"Files sharing ID '{artifact_id}': {', '.join(sorted(sources))}."
                    ),
                )
            )

    return issues


def _extract_frontmatter_id(md_path: Path) -> str | None:
    """Extract the ``id`` value from a markdown file's YAML frontmatter.

    Returns ``None`` if the file cannot be read, has no frontmatter,
    or the ``id`` field is missing/not a string.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None

    try:
        data = yaml.safe_load(fm_match.group(1))
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict):
        return None

    raw_id = data.get("id")
    if isinstance(raw_id, str) and raw_id.strip():
        return raw_id.strip()
    return None


def check_stack_refs_validity(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Verify that Stack post refs.files and refs.designs entries exist on disk.

    Parses all Stack posts and checks that every entry in ``refs.files``
    and ``refs.designs`` resolves to an existing file.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for broken refs.
    """
    issues: list[ValidationIssue] = []
    stack_dir = lexibrary_dir / "stack"
    if not stack_dir.is_dir():
        return issues

    posts_dir = stack_dir / "posts"
    # Check both stack/ and stack/posts/ patterns
    search_dirs: list[Path] = []
    if posts_dir.is_dir():
        search_dirs.append(posts_dir)
    search_dirs.append(stack_dir)

    seen_paths: set[Path] = set()
    for search_dir in search_dirs:
        for md_path in sorted(search_dir.glob("ST-*-*.md")):
            if md_path in seen_paths:
                continue
            seen_paths.add(md_path)

            post = parse_stack_post(md_path)
            if post is None:
                continue

            rel_post = _rel(md_path, project_root)

            for file_ref in post.frontmatter.refs.files:
                target = project_root / file_ref
                if not target.exists():
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            check="stack_refs_validity",
                            message=f"refs.files entry does not exist: {file_ref}",
                            artifact=rel_post,
                            suggestion=(
                                f"Edit {rel_post} and remove or update the stale "
                                f"refs.files entry '{file_ref}'."
                            ),
                        )
                    )

            for design_ref in post.frontmatter.refs.designs:
                target = project_root / design_ref
                if not target.exists():
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            check="stack_refs_validity",
                            message=f"refs.designs entry does not exist: {design_ref}",
                            artifact=rel_post,
                            suggestion=(
                                f"Edit {rel_post} and remove or update the stale "
                                f"refs.designs entry '{design_ref}'."
                            ),
                        )
                    )

    return issues


def check_design_deps_existence(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Verify that Dependencies and Dependents in design files resolve.

    Parses each design file and checks that every entry in the
    ``## Dependencies`` and ``## Dependents`` sections points to an
    existing design file on disk.  Entries whose source path is matched
    by the project's ignore patterns (e.g. gitignored generated code like
    ``baml_client/``) are silently skipped — the archivist intentionally
    omits design files for ignored sources, so missing design files for
    those paths are not a library health issue.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for broken deps.
    """
    issues: list[ValidationIssue] = []

    # Build ignore matcher once for the whole check so we don't re-read
    # .gitignore files on every design file iteration.
    config = load_config(project_root)
    matcher = create_ignore_matcher(config, project_root)

    for design_path in _iter_design_files(lexibrary_dir):
        design = parse_design_file(design_path)
        if design is None:
            continue

        rel_design = _rel(design_path, project_root)

        # Check Dependencies
        for dep in design.dependencies:
            dep_stripped = dep.strip()
            if not dep_stripped or dep_stripped == "(none)":
                continue
            # Dependencies are project-relative source paths; look for their design file
            dep_design = lexibrary_dir / DESIGNS_DIR / f"{dep_stripped}.md"
            if not dep_design.exists():
                # Skip entries whose source file is gitignored / lexignored —
                # the archivist won't create design files for those paths.
                source_path = project_root / dep_stripped
                if matcher.is_ignored(source_path):
                    continue
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        check="design_deps_existence",
                        message=(f"Dependency '{dep_stripped}' has no design file"),
                        artifact=rel_design,
                        suggestion=(
                            f"Remove '{dep_stripped}' from the Dependencies section of "
                            f"{rel_design}, or create the missing design file."
                        ),
                    )
                )

        # Check Dependents
        for dep in design.dependents:
            dep_stripped = dep.strip()
            if not dep_stripped or dep_stripped == "(none)":
                continue
            dep_design = lexibrary_dir / DESIGNS_DIR / f"{dep_stripped}.md"
            if not dep_design.exists():
                # Skip entries whose source file is gitignored / lexignored.
                source_path = project_root / dep_stripped
                if matcher.is_ignored(source_path):
                    continue
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        check="design_deps_existence",
                        message=(f"Dependent '{dep_stripped}' has no design file"),
                        artifact=rel_design,
                        suggestion=(
                            f"Remove '{dep_stripped}' from the Dependents section of "
                            f"{rel_design}, or create the missing design file."
                        ),
                    )
                )

    return issues


def check_aindex_entries(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Verify that .aindex child map entries exist on disk.

    Parses all ``.aindex`` files under ``.lexibrary/designs/`` and checks
    that every child map entry (file or directory) exists in the
    corresponding source directory.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for stale entries.
    """
    from lexibrary.artifacts.aindex_parser import parse_aindex  # noqa: PLC0415

    issues: list[ValidationIssue] = []
    designs_dir = lexibrary_dir / DESIGNS_DIR
    if not designs_dir.is_dir():
        return issues

    for aindex_path_obj in sorted(designs_dir.rglob(".aindex")):
        aindex = parse_aindex(aindex_path_obj)
        if aindex is None:
            continue

        # The directory_path from the aindex is project-relative
        source_dir = project_root / aindex.directory_path
        rel_aindex = _rel(aindex_path_obj, project_root)

        for entry in aindex.entries:
            child_path = source_dir / entry.name
            if entry.entry_type == "dir":
                if not child_path.is_dir():
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            check="aindex_entries",
                            message=(
                                f"Child directory '{entry.name}' does not exist "
                                f"in {aindex.directory_path}"
                            ),
                            artifact=rel_aindex,
                            suggestion=(
                                "Ask the user to run `lexictl update` to "
                                f"rebuild .aindex files, or delete "
                                f"the stale entry '{entry.name}' from {rel_aindex} manually."
                            ),
                        )
                    )
            else:
                if not child_path.is_file():
                    issues.append(
                        ValidationIssue(
                            severity="warning",
                            check="aindex_entries",
                            message=(
                                f"Child file '{entry.name}' does not exist "
                                f"in {aindex.directory_path}"
                            ),
                            artifact=rel_aindex,
                            suggestion=(
                                "Ask the user to run `lexictl update` to "
                                f"rebuild .aindex files, or delete "
                                f"the stale entry '{entry.name}' from {rel_aindex} manually."
                            ),
                        )
                    )

    return issues


# ---------------------------------------------------------------------------
# Body and structure checks
# ---------------------------------------------------------------------------

# Regex for HTML comment metadata footer used in design files
_META_FOOTER_RE = re.compile(r"<!--\s*lexibrary:meta\b", re.DOTALL)


def check_design_structure(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Verify design files have expected body sections and metadata footer.

    Checks each ``.md`` file in ``.lexibrary/designs/`` (recursively) for:

    - An H1 heading (source path)
    - A ``## Interface Contract`` section
    - A ``## Dependencies`` section
    - A ``## Dependents`` section
    - A ``<!-- lexibrary:meta ... -->`` metadata footer

    Files that fail frontmatter parsing are skipped (handled by the
    ``design_frontmatter`` check).

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for missing sections.
    """
    issues: list[ValidationIssue] = []

    design_files = _iter_design_files(lexibrary_dir)
    if not design_files:
        return issues

    required_sections = ["Interface Contract", "Dependencies", "Dependents"]

    for design_path in design_files:
        rel_path = _rel(design_path, project_root)

        try:
            text = design_path.read_text(encoding="utf-8")
        except OSError:
            continue

        # Skip files without parseable frontmatter (design_frontmatter handles those)
        fm_match = _FRONTMATTER_RE.match(text)
        if not fm_match:
            continue

        try:
            data = yaml.safe_load(fm_match.group(1))
        except yaml.YAMLError:
            continue

        if not isinstance(data, dict):
            continue

        # Extract body after frontmatter
        body = text[fm_match.end() :]
        body_lines = body.splitlines()

        # Check for H1 heading
        has_h1 = any(line.strip().startswith("# ") for line in body_lines)
        if not has_h1:
            # Derive the source file path from the design file path for the suggestion
            design_rel = str(design_path.relative_to(lexibrary_dir / DESIGNS_DIR))
            source_from_design = design_rel[:-3] if design_rel.endswith(".md") else design_rel
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="design_structure",
                    message="Missing H1 heading (source path)",
                    artifact=rel_path,
                    suggestion=(
                        f"Run: lexi design update {source_from_design} "
                        f"to regenerate the design file with all required sections."
                    ),
                )
            )

        # Check for required ## sections
        found_sections: set[str] = set()
        for line in body_lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                section_name = stripped[3:].strip()
                found_sections.add(section_name)

        for section in required_sections:
            if section not in found_sections:
                design_rel = str(design_path.relative_to(lexibrary_dir / DESIGNS_DIR))
                source_from_design = design_rel[:-3] if design_rel.endswith(".md") else design_rel
                issues.append(
                    ValidationIssue(
                        severity="warning",
                        check="design_structure",
                        message=f"Missing '## {section}' section",
                        artifact=rel_path,
                        suggestion=(
                            f"Run: lexi design update {source_from_design} "
                            f"to regenerate the design file with all required sections."
                        ),
                    )
                )

        # Check for metadata footer
        if not _META_FOOTER_RE.search(text):
            design_rel = str(design_path.relative_to(lexibrary_dir / DESIGNS_DIR))
            source_from_design = design_rel[:-3] if design_rel.endswith(".md") else design_rel
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="design_structure",
                    message="Missing metadata footer (<!-- lexibrary:meta ... -->)",
                    artifact=rel_path,
                    suggestion=(
                        f"Run: lexi design update {source_from_design} "
                        f"to regenerate the design file with the metadata footer."
                    ),
                )
            )

    return issues


def check_stack_body_sections(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Check that Stack posts have a non-empty ``## Problem`` section.

    Parses all Stack post files and verifies that ``## Problem`` exists
    and contains non-whitespace content.  Posts with malformed YAML are
    skipped gracefully.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of warning-severity ValidationIssues for missing/empty problem sections.
    """
    issues: list[ValidationIssue] = []

    posts_dir = lexibrary_dir / "stack" / "posts"
    if not posts_dir.is_dir():
        return issues

    for md_path in sorted(posts_dir.glob("*.md")):
        rel_path = _rel(md_path, project_root)

        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue

        # Skip files with no parseable frontmatter
        fm_match = _FRONTMATTER_RE.match(text)
        if not fm_match:
            continue

        try:
            data = yaml.safe_load(fm_match.group(1))
        except yaml.YAMLError:
            continue

        if not isinstance(data, dict):
            continue

        # Extract body after frontmatter
        body = text[fm_match.end() :]
        body_lines = body.splitlines()

        # Look for ## Problem section and extract its content
        in_problem = False
        problem_content: list[str] = []

        for line in body_lines:
            stripped = line.strip()
            if stripped.startswith("## Problem"):
                in_problem = True
                continue
            if in_problem and (stripped.startswith("## ") or stripped.startswith("### ")):
                break
            if in_problem:
                problem_content.append(line)

        if not in_problem:
            # No ## Problem heading found at all
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="stack_body_sections",
                    message="Missing '## Problem' section",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add a '## Problem' section describing the issue."
                    ),
                )
            )
        elif not "".join(problem_content).strip():
            # ## Problem exists but has no content
            issues.append(
                ValidationIssue(
                    severity="warning",
                    check="stack_body_sections",
                    message="Empty '## Problem' section",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add a problem description "
                        f"under the '## Problem' section."
                    ),
                )
            )

    return issues


def check_concept_body(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Check that concept files have non-empty body content after frontmatter.

    Parses all ``.md`` files in ``.lexibrary/concepts/`` and verifies that
    the body (content after the closing ``---``) contains non-whitespace text.
    Concepts with empty bodies produce info-severity issues.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for empty concept bodies.
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
            continue

        # Skip files with no parseable frontmatter
        fm_match = _FRONTMATTER_RE.match(text)
        if not fm_match:
            continue

        try:
            data = yaml.safe_load(fm_match.group(1))
        except yaml.YAMLError:
            continue

        if not isinstance(data, dict):
            continue

        # Extract body after frontmatter
        body = text[fm_match.end() :]

        if not body.strip():
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="concept_body",
                    message="Concept has empty body",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add a summary or description after the frontmatter."
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
                        f"Trim the design file body in {rel_path}, or increase "
                        f"token_budgets.lookup_total_tokens in .lexibrary/config.yaml."
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
                    message=(f"IWH signal expired: {int(age_hours)}h old (TTL is {ttl_hours}h)"),
                    artifact=rel_path,
                    suggestion=(
                        f"Run: lexi iwh read {str(iwh_file.parent.relative_to(lexibrary_dir))} "
                        f"to consume the signal, or delete the file manually: {rel_path}"
                    ),
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Playbook checks
# ---------------------------------------------------------------------------


def check_playbook_frontmatter(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Validate all playbook files have mandatory frontmatter fields.

    Checks that every ``.md`` file in the playbooks directory has valid YAML
    frontmatter with ``title``, ``status`` (draft/active/deprecated),
    ``source`` (user/agent), and parseable ``trigger_files`` globs.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for invalid frontmatter.
    """
    import pathspec  # noqa: PLC0415

    issues: list[ValidationIssue] = []
    playbooks_dir = lexibrary_dir / "playbooks"
    if not playbooks_dir.is_dir():
        return issues

    valid_statuses = {"draft", "active", "deprecated"}
    valid_sources = {"user", "agent"}

    for md_path in sorted(playbooks_dir.glob("*.md")):
        rel_path = _rel(md_path, project_root)

        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message="Could not read playbook file",
                    artifact=rel_path,
                )
            )
            continue

        fm_match = _FRONTMATTER_RE.match(text)
        if not fm_match:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message="Missing YAML frontmatter",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add --- delimited YAML frontmatter "
                        f"with title, status, source fields."
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
                    check="playbook_frontmatter",
                    message="Invalid YAML in frontmatter",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and fix the YAML syntax in the frontmatter block.",
                )
            )
            continue

        if not isinstance(data, dict):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message="Frontmatter is not a YAML mapping",
                    artifact=rel_path,
                    suggestion=(f"Edit {rel_path}: frontmatter must be a YAML key-value mapping."),
                )
            )
            continue

        # title -- must be present and a non-empty string
        if "title" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message="Missing mandatory field: title",
                    artifact=rel_path,
                    suggestion=f"Edit {rel_path} and add a 'title:' field to the frontmatter.",
                )
            )
        elif not isinstance(data["title"], str) or not data["title"].strip():
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message="Field 'title' must be a non-empty string",
                    artifact=rel_path,
                    suggestion=(f"Edit {rel_path} and set 'title:' to a non-empty string."),
                )
            )

        # status -- must be one of valid values
        if "status" in data and data["status"] not in valid_statuses:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message=f"Invalid status: {data['status']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set status to one of: "
                        f"{', '.join(sorted(valid_statuses))}."
                    ),
                )
            )

        # source -- must be one of valid values
        if "source" in data and data["source"] not in valid_sources:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message=f"Invalid source: {data['source']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and set source to one of: "
                        f"{', '.join(sorted(valid_sources))}."
                    ),
                )
            )

        # trigger_files -- each entry must be a valid gitignore glob
        trigger_files = data.get("trigger_files", [])
        if isinstance(trigger_files, list):
            for pattern in trigger_files:
                if not isinstance(pattern, str):
                    continue
                try:
                    pathspec.PathSpec.from_lines("gitignore", [pattern])
                except Exception:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            check="playbook_frontmatter",
                            message=(f"Invalid trigger_files glob pattern: {pattern!r}"),
                            artifact=rel_path,
                            suggestion=(
                                f"Edit {rel_path} and fix the trigger_files pattern "
                                f"{pattern!r} to use valid gitignore syntax."
                            ),
                        )
                    )

        # id — must be present and match PB-NNN pattern (3+ digits)
        _pb_id_pattern = re.compile(r"^PB-\d{3,}$")
        if "id" not in data:
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message="Missing mandatory field: id",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and add 'id:' in PB-NNN format (e.g. 'id: PB-001')."
                    ),
                )
            )
        elif not isinstance(data["id"], str) or not _pb_id_pattern.match(data["id"]):
            issues.append(
                ValidationIssue(
                    severity="error",
                    check="playbook_frontmatter",
                    message=f"Invalid id format: {data['id']}",
                    artifact=rel_path,
                    suggestion=(
                        f"Edit {rel_path} and correct 'id:' to match PB-NNN format "
                        f"(e.g. 'id: PB-001')."
                    ),
                )
            )

    return issues


def check_playbook_wikilinks(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Parse wikilinks in playbook bodies and verify each resolves.

    Uses WikilinkResolver to check every ``[[link]]`` found in playbook
    body text. Unresolved links produce error-severity issues with
    suggestions from fuzzy matching.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of error-severity ValidationIssues for unresolved wikilinks.
    """
    issues: list[ValidationIssue] = []

    playbooks_dir = lexibrary_dir / "playbooks"
    if not playbooks_dir.is_dir():
        return issues

    # Build resolver
    concepts_dir = lexibrary_dir / "concepts"
    index = ConceptIndex.load(concepts_dir)
    stack_dir = lexibrary_dir / "stack"
    convention_dir = lexibrary_dir / "conventions"
    resolver = WikilinkResolver(
        index,
        stack_dir=stack_dir,
        convention_dir=convention_dir,
        playbook_dir=playbooks_dir,
    )

    for md_path in sorted(playbooks_dir.glob("*.md")):
        playbook = parse_playbook_file(md_path)
        if playbook is None:
            continue

        # Extract wikilinks from body text
        body_links = _WIKILINK_RE.findall(playbook.body)
        for link_text in body_links:
            result = resolver.resolve(link_text)
            if isinstance(result, UnresolvedLink):
                suggestion = ""
                if result.suggestions:
                    suggestion = f"Did you mean [[{result.suggestions[0]}]]?"
                rel_path = _rel(md_path, project_root)
                issues.append(
                    ValidationIssue(
                        severity="error",
                        check="playbook_wikilinks",
                        message=f"[[{link_text}]] does not resolve",
                        artifact=rel_path,
                        suggestion=suggestion,
                    )
                )

    return issues


def check_playbook_staleness(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect active playbooks that may be stale.

    Flags active playbooks where:
    - ``last_verified`` is unset (never verified)
    - Commits since ``last_verified`` exceed ``config.playbooks.staleness_commits``
    - Calendar days since ``last_verified`` exceed ``config.playbooks.staleness_days``

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for stale playbooks.
    """
    issues: list[ValidationIssue] = []

    playbooks_dir = lexibrary_dir / "playbooks"
    if not playbooks_dir.is_dir():
        return issues

    # Load config for staleness thresholds
    try:
        config = load_config(project_root)
    except Exception:
        config = None

    staleness_commits = 100  # default
    staleness_days = 180  # default
    if config is not None:
        staleness_commits = config.playbooks.staleness_commits
        staleness_days = config.playbooks.staleness_days

    today = date.today()

    for md_path in sorted(playbooks_dir.glob("*.md")):
        playbook = parse_playbook_file(md_path)
        if playbook is None:
            continue

        # Only check active playbooks
        if playbook.frontmatter.status != "active":
            continue

        rel_path = _rel(md_path, project_root)
        last_verified = playbook.frontmatter.last_verified

        if last_verified is None:
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="playbook_staleness",
                    message=(
                        f"Active playbook '{playbook.frontmatter.title}' has never been verified"
                    ),
                    artifact=rel_path,
                    suggestion=("Run `lexi playbook verify <name>` to mark as recently verified."),
                )
            )
            continue

        # Check commit-based staleness
        since_iso = last_verified.isoformat()
        commit_count = _count_commits_since(project_root, since_iso)
        if commit_count > staleness_commits:
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="playbook_staleness",
                    message=(
                        f"Active playbook '{playbook.frontmatter.title}' "
                        f"is stale: {commit_count} commits since last verified "
                        f"(threshold: {staleness_commits})"
                    ),
                    artifact=rel_path,
                    suggestion=(
                        "Run `lexi playbook verify <name>` to re-verify, "
                        "or update the playbook if steps have changed."
                    ),
                )
            )

        # Check calendar-day staleness
        days_since = (today - last_verified).days
        if days_since > staleness_days:
            issues.append(
                ValidationIssue(
                    severity="info",
                    check="playbook_staleness",
                    message=(
                        f"Active playbook '{playbook.frontmatter.title}' "
                        f"is stale: {days_since} days since last verified "
                        f"(threshold: {staleness_days})"
                    ),
                    artifact=rel_path,
                    suggestion=(
                        "Run `lexi playbook verify <name>` to re-verify, "
                        "or update the playbook if steps have changed."
                    ),
                )
            )

    return issues


def check_playbook_deprecated_ttl(
    project_root: Path,
    lexibrary_dir: Path,
) -> list[ValidationIssue]:
    """Detect deprecated playbooks past the TTL window.

    Flags deprecated playbooks whose ``deprecated_at`` timestamp exceeds the
    commit-based TTL window (``config.deprecation.ttl_commits``). Also verifies
    that ``superseded_by`` targets exist when set.

    Args:
        project_root: Root directory of the project.
        lexibrary_dir: Path to the .lexibrary directory.

    Returns:
        List of info-severity ValidationIssues for expired deprecated playbooks.
    """
    issues: list[ValidationIssue] = []

    playbooks_dir = lexibrary_dir / "playbooks"
    if not playbooks_dir.is_dir():
        return issues

    # Load config for TTL
    try:
        config = load_config(project_root)
    except Exception:
        config = None

    ttl_commits = 50  # default
    if config is not None:
        ttl_commits = config.deprecation.ttl_commits

    # Build index for superseded_by resolution
    pb_index = PlaybookIndex(playbooks_dir)
    pb_index.load()

    for md_path in sorted(playbooks_dir.glob("*.md")):
        playbook = parse_playbook_file(md_path)
        if playbook is None:
            continue

        if playbook.frontmatter.status != "deprecated":
            continue

        rel_path = _rel(md_path, project_root)

        # Check TTL expiry
        deprecated_at = playbook.frontmatter.deprecated_at
        if deprecated_at is not None:
            since_iso = deprecated_at.isoformat()
            commit_count = _count_commits_since(project_root, since_iso)
            if commit_count > ttl_commits:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        check="playbook_deprecated_ttl",
                        message=(
                            f"Deprecated playbook '{playbook.frontmatter.title}' "
                            f"has exceeded TTL ({ttl_commits} commits)"
                        ),
                        artifact=rel_path,
                        suggestion=(f"Delete or archive the deprecated playbook file: {rel_path}"),
                    )
                )

        # Verify superseded_by target exists
        superseded_by = playbook.frontmatter.superseded_by
        if superseded_by is not None:
            target = pb_index.find(superseded_by)
            if target is None:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        check="playbook_deprecated_ttl",
                        message=(
                            f"Deprecated playbook '{playbook.frontmatter.title}' "
                            f"has superseded_by='{superseded_by}' but no such "
                            f"playbook exists"
                        ),
                        artifact=rel_path,
                        suggestion=(
                            f"Edit {rel_path} and correct the superseded_by value to "
                            f"reference an existing playbook slug, or remove the field."
                        ),
                    )
                )

    return issues
