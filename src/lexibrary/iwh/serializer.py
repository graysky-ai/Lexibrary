"""Serializer for IWH files to markdown format with YAML frontmatter."""

from __future__ import annotations

import yaml

from lexibrary.iwh.model import IWHFile


def serialize_iwh(iwh: IWHFile) -> str:
    """Serialize an IWHFile to a markdown string with YAML frontmatter.

    Produces:
    - ``---`` delimited YAML frontmatter containing author, created (ISO 8601), scope
    - The markdown body after the closing ``---`` delimiter
    - Trailing newline
    """
    fm_data: dict[str, object] = {
        "author": iwh.author,
        "created": iwh.created.isoformat(),
        "scope": iwh.scope,
    }

    fm_str = yaml.dump(
        fm_data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    ).rstrip("\n")

    parts: list[str] = [f"---\n{fm_str}\n---\n"]

    if iwh.body:
        parts.append(iwh.body.rstrip("\n"))
        parts.append("\n")

    result = "".join(parts)
    # Ensure trailing newline
    if not result.endswith("\n"):
        result += "\n"
    return result
