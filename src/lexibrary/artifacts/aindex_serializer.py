"""Serializer for .aindex file artifacts to v2 markdown format."""

from __future__ import annotations

from lexibrary.artifacts.aindex import AIndexFile


def serialize_aindex(data: AIndexFile) -> str:
    """Serialize an AIndexFile to v2 .aindex markdown format."""
    parts: list[str] = []

    # H1 heading with trailing /
    dir_path = data.directory_path
    if not dir_path.endswith("/"):
        dir_path = dir_path + "/"
    parts.append(f"# {dir_path}")
    parts.append("")

    # Billboard
    parts.append(data.billboard)
    parts.append("")

    # Child Map section
    parts.append("## Child Map")
    parts.append("")

    files = sorted(
        [e for e in data.entries if e.entry_type == "file"],
        key=lambda e: e.name.lower(),
    )
    dirs = sorted(
        [e for e in data.entries if e.entry_type == "dir"],
        key=lambda e: e.name.lower(),
    )
    all_sorted = files + dirs

    if not all_sorted:
        parts.append("(none)")
    else:
        parts.append("| Name | Type | Description |")
        parts.append("| --- | --- | --- |")
        for entry in all_sorted:
            if entry.entry_type == "file":
                name_cell = f"`{entry.name}`"
            else:
                name = entry.name if entry.name.endswith("/") else entry.name + "/"
                name_cell = f"`{name}`"
            parts.append(f"| {name_cell} | {entry.entry_type} | {entry.description} |")

    parts.append("")

    # Staleness metadata footer as HTML comment
    meta = data.metadata
    meta_fields: list[str] = [
        f'source="{meta.source}"',
        f'source_hash="{meta.source_hash}"',
    ]
    if meta.interface_hash is not None:
        meta_fields.append(f'interface_hash="{meta.interface_hash}"')
    meta_fields.append(f'generated="{meta.generated.isoformat()}"')
    meta_fields.append(f'generator="{meta.generator}"')

    parts.append(f"<!-- lexibrary:meta {' '.join(meta_fields)} -->")

    return "\n".join(parts) + "\n"
