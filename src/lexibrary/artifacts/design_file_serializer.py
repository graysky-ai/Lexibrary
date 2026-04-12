"""Serializer for design file artifacts to markdown format."""

from __future__ import annotations

import hashlib

import yaml

from lexibrary.artifacts.design_file import DesignFile
from lexibrary.utils.languages import detect_language

# Mapping from detect_language() result to fenced-code-block tag
_LANG_TAG: dict[str, str] = {
    "Python": "python",
    "Python Stub": "python",
    "JavaScript": "javascript",
    "JavaScript JSX": "jsx",
    "TypeScript": "typescript",
    "TypeScript JSX": "tsx",
    "Java": "java",
    "Kotlin": "kotlin",
    "Kotlin Script": "kotlin",
    "Go": "go",
    "Rust": "rust",
    "C": "c",
    "C Header": "c",
    "C++": "cpp",
    "C++ Header": "cpp",
    "C#": "csharp",
    "Ruby": "ruby",
    "PHP": "php",
    "Swift": "swift",
    "Scala": "scala",
    "R": "r",
    "Shell": "bash",
    "Bash": "bash",
    "Zsh": "zsh",
    "SQL": "sql",
    "HTML": "html",
    "CSS": "css",
    "SCSS": "scss",
    "JSON": "json",
    "YAML": "yaml",
    "TOML": "toml",
    "Markdown": "markdown",
    "Dockerfile": "dockerfile",
    "BAML": "baml",
}


def _lang_tag(source_path: str) -> str:
    """Return fenced-code-block language tag for the source file."""
    lang = detect_language(source_path)
    return _LANG_TAG.get(lang, "text")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def serialize_design_file(data: DesignFile) -> str:
    """Serialize a DesignFile to markdown with YAML frontmatter and HTML comment footer."""
    parts: list[str] = []

    # --- YAML frontmatter ---
    description = data.frontmatter.description
    if "\n" in description:
        description = " ".join(description.split())
    frontmatter_dict: dict[str, object] = {
        "description": description,
        "id": data.frontmatter.id,
        "updated_by": data.frontmatter.updated_by,
        "status": data.frontmatter.status,
    }
    # Conditionally include deprecation fields only when non-null
    if data.frontmatter.deprecated_at is not None:
        frontmatter_dict["deprecated_at"] = data.frontmatter.deprecated_at.isoformat()
    if data.frontmatter.deprecated_reason is not None:
        frontmatter_dict["deprecated_reason"] = data.frontmatter.deprecated_reason
    parts.append("---")
    parts.append(yaml.dump(frontmatter_dict, default_flow_style=False, sort_keys=False).rstrip())
    parts.append("---")
    parts.append("")

    # --- H1 heading ---
    parts.append(f"# {data.source_path}")
    parts.append("")

    # --- Interface Contract ---
    parts.append("## Interface Contract")
    parts.append("")
    lang = _lang_tag(data.source_path)
    parts.append(f"```{lang}")
    parts.append(data.interface_contract)
    parts.append("```")
    parts.append("")

    # --- Dependencies ---
    parts.append("## Dependencies")
    parts.append("")
    if data.dependencies:
        for dep in data.dependencies:
            parts.append(f"- {dep}")
    else:
        parts.append("(none)")
    parts.append("")

    # --- Dependents ---
    parts.append("## Dependents")
    parts.append("")
    parts.append("*(see `lexi lookup` for live reverse references)*")
    parts.append("")
    if data.dependents:
        for dep in data.dependents:
            parts.append(f"- {dep}")
    else:
        parts.append("(none)")
    parts.append("")

    # --- Preserved sections (agent-authored content) ---
    # Preserved sections go after standard sections but before optional metadata
    for heading, body in data.preserved_sections.items():
        parts.append(f"## {heading}")
        parts.append("")
        parts.append(body)
        parts.append("")

    # --- Optional sections ---
    if data.tests is not None:
        parts.append("## Tests")
        parts.append("")
        parts.append(data.tests)
        parts.append("")

    if data.complexity_warning is not None:
        parts.append("## Complexity Warning")
        parts.append("")
        parts.append(data.complexity_warning)
        parts.append("")

    if data.enum_notes:
        parts.append("## Enums & constants")
        parts.append("")
        for enum in data.enum_notes:
            parts.append(f"- **{enum.name}** — {enum.role}")
            if enum.values:
                parts.append(f"  Values: {', '.join(enum.values)}.")
        parts.append("")

    if data.call_path_notes:
        parts.append("## Call paths")
        parts.append("")
        for call_path in data.call_path_notes:
            parts.append(f"- **{call_path.entry}** — {call_path.narrative}")
            if call_path.key_hops:
                parts.append(f"  Key hops: {', '.join(call_path.key_hops)}.")
        parts.append("")

    if data.data_flow_notes:
        parts.append("## Data flows")
        parts.append("")
        for d in data.data_flow_notes:
            parts.append(f"- **{d.parameter}** in **{d.location}** — {d.effect}")
        parts.append("")

    if data.wikilinks:
        parts.append("## Wikilinks")
        parts.append("")
        for link in data.wikilinks:
            # Wrap in [[brackets]] if not already wrapped (avoid double-wrapping)
            if link.startswith("[[") and link.endswith("]]"):
                parts.append(f"- {link}")
            else:
                parts.append(f"- [[{link}]]")
        parts.append("")

    if data.tags:
        parts.append("## Tags")
        parts.append("")
        for tag in data.tags:
            parts.append(f"- {tag}")
        parts.append("")

    if data.stack_refs:
        parts.append("## Stack")
        parts.append("")
        for ref in data.stack_refs:
            parts.append(f"- {ref}")
        parts.append("")

    # Compute design_hash from frontmatter + body (everything so far)
    body_text = "\n".join(parts)
    design_hash = _sha256(body_text)

    # --- HTML comment metadata footer ---
    meta = data.metadata
    footer_lines = ["<!-- lexibrary:meta"]
    footer_lines.append(f"source: {meta.source}")
    footer_lines.append(f"source_hash: {meta.source_hash}")
    if meta.interface_hash is not None:
        footer_lines.append(f"interface_hash: {meta.interface_hash}")
    footer_lines.append(f"design_hash: {design_hash}")
    footer_lines.append(f"generated: {meta.generated.isoformat()}")
    footer_lines.append(f"generator: {meta.generator}")
    footer_lines.append("-->")

    parts.append("\n".join(footer_lines))

    return "\n".join(parts) + "\n"
