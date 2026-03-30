"""Template rendering and path derivation for concept files."""

from __future__ import annotations

from pathlib import Path

import yaml

from lexibrary.artifacts.slugs import slugify


def render_concept_template(
    name: str,
    tags: list[str] | None = None,
    *,
    concept_id: str | None = None,
) -> str:
    """Render a new concept file template with placeholder sections.

    Parameters
    ----------
    name:
        The concept title.
    tags:
        Optional list of tags.
    concept_id:
        Optional artifact ID (e.g. ``"CN-001"``).  When provided the
        ``id`` field is included in the YAML frontmatter.

    Returns a markdown string with YAML frontmatter and body scaffolding.
    """
    resolved_tags = tags if tags is not None else []
    fm_data: dict[str, object] = {
        "title": name,
        "aliases": [],
        "tags": resolved_tags,
        "status": "active",
    }
    if concept_id is not None:
        fm_data["id"] = concept_id
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    body = (
        f"---\n{fm_str}\n---\n"
        "\n"
        "<!-- Brief summary of this concept -->\n"
        "\n"
        "## Details\n"
        "\n"
        "## Decision Log\n"
        "\n"
        "## Related\n"
        "\n"
        "<!-- add [[wikilinks]] here -->\n"
    )
    return body


def concept_file_path(concept_id: str, name: str, concepts_dir: Path) -> Path:
    """Derive an ID-prefixed kebab-case file path for a concept name.

    Uses the canonical :func:`~lexibrary.artifacts.slugs.slugify` to produce
    a kebab-case slug, then returns
    ``concepts_dir / "<concept_id>-<slug>.md"`` (e.g.
    ``CN-005-error-handling.md``).
    """
    slug = slugify(name)
    return concepts_dir / f"{concept_id}-{slug}.md"
