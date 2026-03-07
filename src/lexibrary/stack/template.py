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
    problem: str | None = None,
    context: str | None = None,
    evidence: list[str] | None = None,
    attempts: list[str] | None = None,
) -> str:
    """Render a new Stack post template with YAML frontmatter and body.

    Two modes:

    - **Scaffold mode** (no content params): all 4 body sections are emitted
      with HTML comment placeholders for the user to fill in.
    - **Populated mode** (any content param provided): only sections with
      content are emitted.  ``## Problem`` is always included even if
      *problem* is ``None``, because every post needs a problem section.

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

    populated = any(p is not None for p in (problem, context, evidence, attempts))

    parts: list[str] = [f"---\n{fm_str}\n---\n"]

    if populated:
        # Populated mode: emit only sections with content.
        # ## Problem is always present.
        parts.append("\n## Problem\n")
        if problem:
            parts.append(f"\n{problem}\n")

        if context is not None:
            parts.append("\n### Context\n")
            parts.append(f"\n{context}\n")

        if evidence is not None:
            parts.append("\n### Evidence\n")
            for item in evidence:
                parts.append(f"\n- {item}")
            parts.append("\n")

        if attempts is not None:
            parts.append("\n### Attempts\n")
            for item in attempts:
                parts.append(f"\n- {item}")
            parts.append("\n")
    else:
        # Scaffold mode: all 4 sections with placeholder comments.
        parts.append(
            "\n## Problem\n"
            "\n"
            "<!-- Describe the problem or issue here -->\n"
            "\n"
            "### Context\n"
            "\n"
            "<!-- Explain what you were doing when the issue occurred -->\n"
            "\n"
            "### Evidence\n"
            "\n"
            "<!-- Add supporting evidence, error logs, or reproduction steps -->\n"
            "\n"
            "### Attempts\n"
            "\n"
            "<!-- Describe what you have already tried -->\n"
        )

    return "".join(parts)
