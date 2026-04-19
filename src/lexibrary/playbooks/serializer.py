"""Serializer for playbook file artifacts to markdown format."""

from __future__ import annotations

import yaml

from lexibrary.artifacts.playbook import PlaybookFile

# Tooltip comment emitted above the title field in YAML frontmatter.
_TITLE_COMMENT = "# title: use a semantic name that describes the procedure"


def serialize_playbook_file(playbook: PlaybookFile) -> str:
    """Serialize a PlaybookFile to a markdown string with YAML frontmatter.

    Produces:
    - ``---`` delimited YAML frontmatter with a tooltip comment above ``title``
    - ``trigger_files`` rendered as a YAML flow list for readability
    - Optional fields (``estimated_minutes``, ``deprecated_at``,
      ``deprecated_reason``, ``superseded_by``, ``aliases``) omitted when
      ``None`` or empty
    - ``last_verified`` serialized as ISO date (YYYY-MM-DD)
    - ``deprecated_at`` serialized as ISO datetime string
    - A blank line after the closing ``---``
    - The full body text
    - Trailing newline
    """
    fm = playbook.frontmatter

    # Build ordered frontmatter dict, omitting optional None/empty fields
    fm_data: dict[str, object] = {
        "title": fm.title,
        "id": fm.id,
    }

    # trigger_files — always include (even if empty, it's a core field)
    fm_data["trigger_files"] = fm.trigger_files

    # tags — always include
    fm_data["tags"] = fm.tags

    fm_data["status"] = fm.status
    fm_data["source"] = fm.source

    # Optional fields — omit when None or empty
    if fm.estimated_minutes is not None:
        fm_data["estimated_minutes"] = fm.estimated_minutes

    if fm.last_verified is not None:
        fm_data["last_verified"] = fm.last_verified.isoformat()

    if fm.deprecated_at is not None:
        fm_data["deprecated_at"] = fm.deprecated_at.isoformat()

    if fm.deprecated_reason is not None:
        fm_data["deprecated_reason"] = fm.deprecated_reason

    if fm.superseded_by is not None:
        fm_data["superseded_by"] = fm.superseded_by

    if fm.aliases:
        fm_data["aliases"] = fm.aliases

    # Serialize to YAML string
    fm_str = yaml.dump(fm_data, default_flow_style=False, sort_keys=False).rstrip("\n")

    # Replace the block-style trigger_files with flow list format
    fm_str = _replace_with_flow_list(fm_str, "trigger_files", fm.trigger_files)
    # Also replace tags with flow list for consistency
    fm_str = _replace_with_flow_list(fm_str, "tags", fm.tags)

    # Inject title tooltip comment above the title line
    fm_str = f"{_TITLE_COMMENT}\n{fm_str}"

    parts = [f"---\n{fm_str}\n---\n"]
    if playbook.body:
        parts.append(playbook.body)
    result = "".join(parts)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _replace_with_flow_list(yaml_str: str, key: str, values: list[str]) -> str:
    """Replace a YAML block list with an inline flow list for *key*.

    If *values* is empty the field is rendered as ``key: []``.
    """
    flow = f"[{', '.join(values)}]" if values else "[]"
    target = f"{key}: {flow}"

    lines = yaml_str.splitlines()
    new_lines: list[str] = []
    skip_items = False
    for line in lines:
        # Detect the key line itself
        if line.startswith(f"{key}:"):
            new_lines.append(target)
            # If the dump produced a block list, skip subsequent "- item" lines
            skip_items = line.rstrip() == f"{key}:"
            continue
        if skip_items:
            if line.startswith("- ") or line.startswith("  -"):
                continue  # skip block list item
            skip_items = False
        new_lines.append(line)

    return "\n".join(new_lines)
