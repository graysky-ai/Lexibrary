"""Serializer for concept file artifacts to markdown format."""

from __future__ import annotations

import yaml

from lexibrary.artifacts.concept import ConceptFile


def serialize_concept_file(concept: ConceptFile) -> str:
    """Serialize a ConceptFile to a markdown string with YAML frontmatter.

    Produces:
    - ``---`` delimited YAML frontmatter (title, aliases, tags, status,
      superseded_by if not None)
    - Raw body content as-is
    - Trailing newline
    """
    fm_data: dict[str, object] = {
        "title": concept.frontmatter.title,
        "id": concept.frontmatter.id,
        "aliases": concept.frontmatter.aliases,
        "tags": concept.frontmatter.tags,
        "status": concept.frontmatter.status,
    }
    if concept.frontmatter.superseded_by is not None:
        fm_data["superseded_by"] = concept.frontmatter.superseded_by
    if concept.frontmatter.deprecated_at is not None:
        fm_data["deprecated_at"] = concept.frontmatter.deprecated_at.isoformat()

    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    parts = [f"---\n{fm_str}\n---\n"]
    if concept.body:
        parts.append(concept.body)
    result = "".join(parts)
    if not result.endswith("\n"):
        result += "\n"
    return result
