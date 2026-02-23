"""Template rendering for new Stack posts."""

from __future__ import annotations

from datetime import date

import yaml


def render_post_template(
    *,
    post_id: str,
    title: str,
    tags: list[str],
    author: str,
    bead: str | None = None,
    refs_files: list[str] | None = None,
    refs_concepts: list[str] | None = None,
) -> str:
    """Render a new Stack post template with YAML frontmatter and body scaffold.

    Returns a markdown string ready to be written to disk.
    """
    refs_data: dict[str, list[str]] = {}
    if refs_concepts:
        refs_data["concepts"] = refs_concepts
    if refs_files:
        refs_data["files"] = refs_files

    fm_data: dict[str, object] = {
        "id": post_id,
        "title": title,
        "tags": tags,
        "status": "open",
        "created": date.today(),
        "author": author,
        "votes": 0,
    }
    if bead is not None:
        fm_data["bead"] = bead
    if refs_data:
        fm_data["refs"] = refs_data

    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    body = (
        f"---\n{fm_str}\n---\n"
        "\n"
        "## Problem\n"
        "\n"
        "<!-- Describe the problem or question here -->\n"
        "\n"
        "### Evidence\n"
        "\n"
        "<!-- Add supporting evidence, error logs, or reproduction steps -->\n"
    )
    return body
