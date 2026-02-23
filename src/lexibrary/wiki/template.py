"""Template rendering and path derivation for concept files."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def render_concept_template(name: str, tags: list[str] | None = None) -> str:
    """Render a new concept file template with placeholder sections.

    Returns a markdown string with YAML frontmatter and body scaffolding.
    """
    resolved_tags = tags if tags is not None else []
    fm_data: dict[str, object] = {
        "title": name,
        "aliases": [],
        "tags": resolved_tags,
        "status": "draft",
    }
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


def concept_file_path(name: str, concepts_dir: Path) -> Path:
    """Derive a PascalCase file path for a concept name.

    Removes spaces and special characters, capitalizes word boundaries,
    and appends ``.md``.
    """
    # Split on non-alphanumeric characters to get words
    words = re.split(r"[^a-zA-Z0-9]+", name)
    pascal = "".join(w.capitalize() for w in words if w)
    return concepts_dir / f"{pascal}.md"
