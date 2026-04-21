"""Serializer for design file artifacts to markdown format."""

# Staleness hashes in the footer serve three distinct purposes:
#   source_hash     — SHA-256 of raw source bytes (detects source drift).
#   interface_hash  — SHA-256 of the extracted interface skeleton (detects
#                     skeleton drift without re-reading source).
#   design_hash     — SHA-256 of the rendered design body excluding the
#                     footer (detects agent/human edits to the design file).

from __future__ import annotations

import hashlib
import re

import yaml

from lexibrary.artifacts.design_file import DesignFile
from lexibrary.utils.languages import detect_language

# Matches a leading inner code fence, e.g. ```python\n, ```ts\n, or ```\n.
_INNER_FENCE_OPEN_RE = re.compile(r"^```[A-Za-z0-9_+-]*\n")

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


# YAML flow-style reserved characters: if any appear in a scalar, quote the
# whole value. Outside the flow context `{`, `}`, and `,` are unremarkable,
# but the compact meta footer IS a flow mapping, so they matter here. The
# remaining characters are the leading-indicator set that triggers YAML's
# plain-scalar ambiguity rules.
_YAML_FLOW_RESERVED = frozenset("{},:#&*!|>'\"%@`")


def _yaml_flow_scalar(value: str) -> str:
    """Emit ``value`` as a flow-style YAML scalar.

    Unquoted when the value contains no reserved YAML character; otherwise
    wrapped in single quotes with embedded single quotes doubled. SHA-256
    hex digests, ISO-8601 timestamps, and plain source paths are safe
    unquoted (matches SHARED_BLOCK_B's "SHA-256 hex digests are safe
    unquoted" guarantee).
    """
    if any(ch in _YAML_FLOW_RESERVED for ch in value):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return value


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
    }
    # Omit status when equal to the default "active"; only emit non-default values.
    if data.frontmatter.status != "active":
        frontmatter_dict["status"] = data.frontmatter.status
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

    # --- Interface Contract OR Re-exports ---
    # Aggregator modules (detected by classify_aggregator in the pipeline)
    # render ``## Re-exports`` in place of ``## Interface Contract``. The
    # dedicated path SHALL suppress the Interface Contract section entirely.
    if data.reexports:
        parts.append("## Re-exports")
        parts.append("")
        for source_module, names in data.reexports.items():
            joined = ", ".join(names)
            parts.append(f"- From `{source_module}`: {joined}")
        parts.append("")
    else:
        # Strip a leading ```<lang>\n and trailing \n``` from the contract body so
        # we never emit a doubled fence when the upstream producer (e.g. the LLM)
        # already wrapped the skeleton in its own code fence. The outer fence we
        # append below is the canonical one.
        contract = data.interface_contract
        if _INNER_FENCE_OPEN_RE.match(contract):
            contract = _INNER_FENCE_OPEN_RE.sub("", contract, count=1)
        if contract.endswith("\n```"):
            contract = contract[: -len("\n```")]
        elif contract.endswith("```"):
            contract = contract[: -len("```")]
        parts.append("## Interface Contract")
        parts.append("")
        lang = _lang_tag(data.source_path)
        parts.append(f"```{lang}")
        parts.append(contract)
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
    # The `*(see `lexi lookup` for live reverse references)*` hint line was
    # removed in §1.2 — `lexi lookup` is the authoritative source for reverse
    # references and the hint was static noise on every design file. The
    # parser still tolerates legacy on-disk files that carry the hint.
    parts.append("## Dependents")
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

    # --- HTML comment metadata footer (compact inline YAML, §1.3) ---
    # Single-line form: `<!-- lexibrary:meta {k: v, k: v, ...} -->`. Values
    # are emitted unquoted unless they contain a reserved YAML character (per
    # SHARED_BLOCK_B). SHA-256 hex digests, ISO-8601 timestamps, and plain
    # source paths are all safe unquoted. The ``interface_hash`` key is
    # omitted entirely when ``metadata.interface_hash is None`` (matches the
    # pre-§1.3 conditional-emit behaviour).
    meta = data.metadata
    footer_fields: list[tuple[str, str]] = [
        ("source", meta.source),
        ("source_hash", meta.source_hash),
    ]
    if meta.interface_hash is not None:
        footer_fields.append(("interface_hash", meta.interface_hash))
    footer_fields.append(("design_hash", design_hash))
    footer_fields.append(("generated", meta.generated.isoformat()))
    footer_fields.append(("generator", meta.generator))
    footer_fields.append(("dependents_complete", str(meta.dependents_complete).lower()))

    inner = ", ".join(f"{key}: {_yaml_flow_scalar(value)}" for key, value in footer_fields)
    parts.append(f"<!-- lexibrary:meta {{{inner}}} -->")

    return "\n".join(parts) + "\n"
