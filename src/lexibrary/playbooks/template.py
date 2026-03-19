"""Template rendering for new playbook files."""

from __future__ import annotations

import yaml

# Must match the comment in serializer.py for round-trip consistency.
_TITLE_COMMENT = "# title: use a semantic name that describes the procedure"


def render_playbook_template(
    title: str,
    trigger_files: list[str] | None = None,
    tags: list[str] | None = None,
    *,
    estimated_minutes: int | None = None,
) -> str:
    """Render a scaffolded playbook markdown file.

    Produces YAML frontmatter with a tooltip comment above ``title:``,
    followed by Overview, Steps (numbered checkboxes), and Notes sections.

    Parameters
    ----------
    title:
        The playbook title (semantic name).
    trigger_files:
        Glob patterns for file-context discovery.
    tags:
        Categorisation tags.
    estimated_minutes:
        Optional time estimate for the procedure.
    """
    triggers = trigger_files or []
    tag_list = tags or []

    fm_data: dict[str, object] = {
        "title": title,
        "trigger_files": triggers,
        "tags": tag_list,
        "status": "draft",
        "source": "user",
    }
    if estimated_minutes is not None:
        fm_data["estimated_minutes"] = estimated_minutes

    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    # Replace block-style lists with flow lists for readability
    fm_str = _replace_with_flow_list(fm_str, "trigger_files", triggers)
    fm_str = _replace_with_flow_list(fm_str, "tags", tag_list)

    # Inject title tooltip comment above the title line
    fm_str = f"{_TITLE_COMMENT}\n{fm_str}"

    parts: list[str] = [f"---\n{fm_str}\n---\n"]

    # Body scaffold
    parts.append(
        "\n## Overview\n"
        "\n"
        "<!-- Describe what this playbook does and when to use it -->\n"
        "\n"
        "## Steps\n"
        "\n"
        "1. [ ] Step one\n"
        "2. [ ] Step two\n"
        "3. [ ] Step three\n"
        "\n"
        "## Notes\n"
        "\n"
        "<!-- Related: [[playbook: ...]], [[concept: ...]] -->\n"
    )

    return "".join(parts)


def _replace_with_flow_list(yaml_str: str, key: str, values: list[str]) -> str:
    """Replace a YAML block list with an inline flow list for *key*."""
    flow = f"[{', '.join(values)}]" if values else "[]"
    target = f"{key}: {flow}"

    lines = yaml_str.splitlines()
    new_lines: list[str] = []
    skip_items = False
    for line in lines:
        if line.startswith(f"{key}:"):
            new_lines.append(target)
            skip_items = line.rstrip() == f"{key}:"
            continue
        if skip_items:
            if line.startswith("- ") or line.startswith("  -"):
                continue
            skip_items = False
        new_lines.append(line)

    return "\n".join(new_lines)
