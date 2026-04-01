"""View render -- format :class:`ViewResult` for terminal output.

Dispatches on ``isinstance(result.content, ...)`` for mypy
exhaustiveness checking.  The renderer never calls ``info()`` or any
other output function directly -- it returns strings for the CLI
handler to emit.

This module also provides :func:`render_view_error` for formatting
:class:`ViewError` subtypes as plain text or JSON.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from lexibrary.artifacts.concept import ConceptFile
from lexibrary.artifacts.convention import ConventionFile
from lexibrary.artifacts.design_file import DesignFile
from lexibrary.artifacts.playbook import PlaybookFile
from lexibrary.stack.models import StackPost

if TYPE_CHECKING:
    from lexibrary.services.view import ViewError, ViewResult


# ---------------------------------------------------------------------------
# Public dispatch
# ---------------------------------------------------------------------------


def render_view(result: ViewResult) -> str:
    """Format a :class:`ViewResult` as plain-text output.

    Dispatches to a per-type renderer based on ``isinstance`` narrowing
    of ``result.content``.  Returns a multi-line string suitable for
    ``info()`` output.
    """
    content = result.content

    if isinstance(content, ConceptFile):
        return _render_concept(result, content)
    if isinstance(content, ConventionFile):
        return _render_convention(result, content)
    if isinstance(content, PlaybookFile):
        return _render_playbook(result, content)
    if isinstance(content, DesignFile):
        return _render_design(result, content)
    if isinstance(content, StackPost):
        return _render_stack(result, content)

    # Unreachable if ArtifactContent union is exhaustive, but satisfies mypy.
    return f"[Unknown artifact type: {result.kind}]"  # pragma: no cover


# ---------------------------------------------------------------------------
# Error rendering
# ---------------------------------------------------------------------------


def render_view_error(err: ViewError, *, fmt: str = "plain") -> str:
    """Format a :class:`ViewError` for output.

    Parameters
    ----------
    err:
        The caught :class:`ViewError` subclass.
    fmt:
        Output format -- ``"plain"`` for human-readable text, ``"json"``
        for a machine-readable JSON object.

    Returns
    -------
    str
        Formatted error text.
    """
    if fmt == "json":
        return _render_error_json(err)
    return _render_error_plain(err)


def _render_error_plain(err: ViewError) -> str:
    """Render a :class:`ViewError` as plain text for terminal output."""
    lines: list[str] = [f"Error: {err}"]

    if err.hint:
        lines.append(f"Hint: {err.hint}")

    return "\n".join(lines)


def _render_error_json(err: ViewError) -> str:
    """Render a :class:`ViewError` as a JSON object."""
    from lexibrary.services.view import (  # noqa: PLC0415
        ArtifactNotFoundError,
        ArtifactParseError,
        InvalidArtifactIdError,
        UnknownPrefixError,
    )

    error_type: str
    if isinstance(err, InvalidArtifactIdError):
        error_type = "invalid_id"
    elif isinstance(err, UnknownPrefixError):
        error_type = "unknown_prefix"
    elif isinstance(err, ArtifactNotFoundError):
        error_type = "not_found"
    elif isinstance(err, ArtifactParseError):
        error_type = "parse_error"
    else:
        error_type = "view_error"

    obj: dict[str, str] = {"error": error_type}
    if err.artifact_id:
        obj["artifact_id"] = err.artifact_id
    if err.hint:
        obj["hint"] = err.hint

    return json.dumps(obj)


# ---------------------------------------------------------------------------
# Per-type renderers
# ---------------------------------------------------------------------------


def _render_concept(result: ViewResult, concept: ConceptFile) -> str:
    """Render a concept artifact for display."""
    fm = concept.frontmatter
    lines: list[str] = []

    # Header
    lines.append(f"# {fm.id}: {fm.title}")
    lines.append("")
    lines.append(f"Type: concept | Status: {fm.status}")

    if fm.tags:
        lines.append(f"Tags: {', '.join(fm.tags)}")
    if fm.aliases:
        lines.append(f"Aliases: {', '.join(fm.aliases)}")
    if fm.superseded_by:
        lines.append(f"Superseded by: {fm.superseded_by}")

    # Summary
    if concept.summary:
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(concept.summary)

    # Body
    if concept.body:
        lines.append("")
        lines.append("## Body")
        lines.append("")
        lines.append(concept.body.strip())

    # Related concepts
    if concept.related_concepts:
        lines.append("")
        lines.append("## Related Concepts")
        lines.append("")
        for rc in concept.related_concepts:
            lines.append(f"- {rc}")

    # Linked files
    if concept.linked_files:
        lines.append("")
        lines.append("## Linked Files")
        lines.append("")
        for lf in concept.linked_files:
            lines.append(f"- {lf}")

    # Decision log
    if concept.decision_log:
        lines.append("")
        lines.append("## Decision Log")
        lines.append("")
        for entry in concept.decision_log:
            lines.append(f"- {entry}")

    return "\n".join(lines)


def _render_convention(result: ViewResult, convention: ConventionFile) -> str:
    """Render a convention artifact for display."""
    fm = convention.frontmatter
    lines: list[str] = []

    # Header
    lines.append(f"# {fm.id}: {fm.title}")
    lines.append("")
    lines.append(f"Type: convention | Status: {fm.status} | Scope: {fm.scope}")
    lines.append(f"Priority: {fm.priority} | Source: {fm.source}")

    if fm.tags:
        lines.append(f"Tags: {', '.join(fm.tags)}")
    if fm.aliases:
        lines.append(f"Aliases: {', '.join(fm.aliases)}")

    # Rule
    if convention.rule:
        lines.append("")
        lines.append("## Rule")
        lines.append("")
        lines.append(convention.rule)

    # Body
    if convention.body:
        lines.append("")
        lines.append("## Body")
        lines.append("")
        lines.append(convention.body.strip())

    return "\n".join(lines)


def _render_playbook(result: ViewResult, playbook: PlaybookFile) -> str:
    """Render a playbook artifact for display."""
    fm = playbook.frontmatter
    lines: list[str] = []

    # Header
    lines.append(f"# {fm.id}: {fm.title}")
    lines.append("")
    status_parts = ["Type: playbook", f"Status: {fm.status}"]
    if fm.estimated_minutes:
        status_parts.append(f"Est: {fm.estimated_minutes} min")
    lines.append(" | ".join(status_parts))

    if fm.tags:
        lines.append(f"Tags: {', '.join(fm.tags)}")
    if fm.last_verified:
        lines.append(f"Last verified: {fm.last_verified.isoformat()}")
    if fm.trigger_files:
        lines.append(f"Trigger files: {', '.join(fm.trigger_files)}")
    if fm.superseded_by:
        lines.append(f"Superseded by: {fm.superseded_by}")

    # Overview
    if playbook.overview:
        lines.append("")
        lines.append("## Overview")
        lines.append("")
        lines.append(playbook.overview.strip())

    # Body
    if playbook.body:
        lines.append("")
        lines.append("## Steps")
        lines.append("")
        lines.append(playbook.body.strip())

    return "\n".join(lines)


def _render_design(result: ViewResult, design: DesignFile) -> str:
    """Render a design file artifact for display."""
    fm = design.frontmatter
    lines: list[str] = []

    # Header
    lines.append(f"# {fm.id}: {design.source_path}")
    lines.append("")
    lines.append(f"Type: design | Status: {fm.status} | Updated by: {fm.updated_by}")

    if design.tags:
        lines.append(f"Tags: {', '.join(design.tags)}")

    # Description
    lines.append("")
    lines.append("## Description")
    lines.append("")
    lines.append(fm.description)

    # Summary
    if design.summary:
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(design.summary.strip())

    # Interface contract
    if design.interface_contract:
        lines.append("")
        lines.append("## Interface Contract")
        lines.append("")
        lines.append(design.interface_contract.strip())

    # Dependencies
    if design.dependencies:
        lines.append("")
        lines.append("## Dependencies")
        lines.append("")
        for dep in design.dependencies:
            lines.append(f"- {dep}")

    # Dependents
    if design.dependents:
        lines.append("")
        lines.append("## Dependents")
        lines.append("")
        for dep in design.dependents:
            lines.append(f"- {dep}")

    return "\n".join(lines)


def _render_stack(result: ViewResult, post: StackPost) -> str:
    """Render a stack post artifact for display.

    Follows the same formatting as the existing ``lexi stack view``
    command for consistency.
    """
    fm = post.frontmatter
    lines: list[str] = []

    # Header
    lines.append(f"# {fm.id}: {fm.title}")
    lines.append("")
    lines.append(f"Status: {fm.status} | Votes: {fm.votes} | Tags: {', '.join(fm.tags)}")
    lines.append(f"Created: {fm.created.isoformat()} | Author: {fm.author}")
    if fm.bead:
        lines.append(f"Bead: {fm.bead}")
    if fm.refs.files:
        lines.append(f"Files: {', '.join(fm.refs.files)}")
    if fm.refs.concepts:
        lines.append(f"Concepts: {', '.join(fm.refs.concepts)}")
    if fm.duplicate_of:
        lines.append(f"Duplicate of: {fm.duplicate_of}")
    if fm.resolution_type:
        lines.append(f"Resolution: {fm.resolution_type}")

    # Problem
    lines.append("")
    lines.append("## Problem")
    lines.append("")
    lines.append(post.problem)

    # Context
    if post.context:
        lines.append("")
        lines.append("### Context")
        lines.append("")
        lines.append(post.context)

    # Evidence
    if post.evidence:
        lines.append("")
        lines.append("### Evidence")
        lines.append("")
        for item in post.evidence:
            lines.append(f"  - {item}")

    # Attempts
    if post.attempts:
        lines.append("")
        lines.append("### Attempts")
        lines.append("")
        for item in post.attempts:
            lines.append(f"  - {item}")

    # Findings
    if post.findings:
        lines.append("")
        lines.append(f"## Findings ({len(post.findings)})")
        lines.append("")
        for finding in post.findings:
            accepted_badge = " (accepted)" if finding.accepted else ""
            lines.append(
                f"### F{finding.number}{accepted_badge}  "
                f"Votes: {finding.votes} | {finding.date.isoformat()} | {finding.author}"
            )
            lines.append(finding.body)
            if finding.comments:
                lines.append("  Comments:")
                for c in finding.comments:
                    lines.append(f"    {c}")
            lines.append("")
    else:
        lines.append("")
        lines.append("No findings yet.")

    return "\n".join(lines)
