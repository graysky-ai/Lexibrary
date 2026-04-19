"""Serializer for convention file artifacts to markdown format."""

from __future__ import annotations

import yaml

from lexibrary.artifacts.convention import ConventionFile


def serialize_convention_file(convention: ConventionFile) -> str:
    """Serialize a ConventionFile to a markdown string with YAML frontmatter.

    Produces:
    - ``---`` delimited YAML frontmatter (title, scope, tags, status,
      source, priority, and optionally aliases, deprecated_at, and
      deprecated_reason)
    - ``aliases`` is included only when non-empty
    - ``deprecated_at`` is included only when not None
    - ``deprecated_reason`` is included only when not None
    - A blank line after the closing ``---``
    - The full body text
    - Trailing newline
    """
    fm_data: dict[str, object] = {
        "title": convention.frontmatter.title,
        "id": convention.frontmatter.id,
        "scope": convention.frontmatter.scope,
        "tags": convention.frontmatter.tags,
        "status": convention.frontmatter.status,
        "source": convention.frontmatter.source,
        "priority": convention.frontmatter.priority,
    }

    if convention.frontmatter.aliases:
        fm_data["aliases"] = convention.frontmatter.aliases

    if convention.frontmatter.deprecated_at is not None:
        fm_data["deprecated_at"] = convention.frontmatter.deprecated_at.isoformat()

    if convention.frontmatter.deprecated_reason is not None:
        fm_data["deprecated_reason"] = convention.frontmatter.deprecated_reason

    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    parts = [f"---\n{fm_str}\n---\n"]
    if convention.body:
        parts.append(convention.body)
    result = "".join(parts)
    if not result.endswith("\n"):
        result += "\n"
    return result
