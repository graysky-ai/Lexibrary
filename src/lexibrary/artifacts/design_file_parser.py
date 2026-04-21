"""Parser for design file artifacts from markdown format."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

from lexibrary.artifacts.design_file import (
    CallPathNote,
    DataFlowNote,
    DesignFile,
    DesignFileFrontmatter,
    EnumNote,
    StalenessMetadata,
)

# Legacy multi-line HTML comment footer: <!-- lexibrary:meta\nkey: value\n-->
_FOOTER_MULTILINE_RE = re.compile(r"<!--\s*lexibrary:meta\n(.*?)\n-->", re.DOTALL)
# Compact inline footer (§1.3 SHARED_BLOCK_B): <!-- lexibrary:meta {k: v, ...} -->
# Captures the inside of the flow mapping, excluding the surrounding braces.
_FOOTER_INLINE_RE = re.compile(r"<!--\s*lexibrary:meta\s+\{(?P<body>.*?)\}\s*-->")
# Combined matcher that strips either footer form from text (used to clean
# up preserved-section bodies that may accidentally include the footer).
_FOOTER_ANY_RE = re.compile(r"<!--\s*lexibrary:meta(?:\n.*?\n|\s+\{.*?\}\s*)-->", re.DOTALL)
# Backward-compatible alias for downstream modules that strip the footer
# from raw text (archivist.pipeline, archivist.change_checker, fixtures).
# The alias now matches BOTH the legacy multi-line and the §1.3 compact
# inline form so that stripping is footer-form-agnostic.
_FOOTER_RE = _FOOTER_ANY_RE
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Entry-line pattern for enrichment bullets: `- **{name}** — {body}`
# Accepts either em-dash (—) or plain dash (-) as the separator for flexibility.
_ENRICHMENT_BULLET_RE = re.compile(r"^-\s+\*\*(?P<name>[^*]+)\*\*\s*[—-]\s*(?P<body>.*)$")

# Data flow bullet pattern: `- **{parameter}** in **{location}** — {effect}`
_DATA_FLOW_BULLET_RE = re.compile(
    r"^-\s+\*\*(?P<parameter>[^*]+)\*\*\s+in\s+\*\*(?P<location>[^*]+)\*\*\s*[—-]\s*(?P<effect>.*)$"
)

# Re-exports bullet pattern: `- From `{source-module}`: Name1, Name2, Name3`
# The source module is wrapped in inline code backticks; names are a
# comma-separated list.
_REEXPORTS_BULLET_RE = re.compile(r"^-\s+From\s+`(?P<source>[^`]+)`\s*:\s*(?P<names>.+)$")


def _split_csv(raw: str) -> list[str]:
    """Split a comma-separated list, trimming whitespace and trailing period."""
    stripped = raw.strip().rstrip(".")
    return [item.strip() for item in stripped.split(",") if item.strip()]


def _parse_enrichment_entries(
    section_lines: list[str], continuation_label: str
) -> list[tuple[str, str, list[str]]]:
    """Parse a section of bullet entries where each entry may have a continuation line.

    Format:
        - **{name}** — {body}
          {continuation_label}: v1, v2, v3.

    The continuation line is optional. Returns a list of (name, body, values)
    tuples where `values` is empty when no continuation line is present.
    """
    entries: list[tuple[str, str, list[str]]] = []
    current: tuple[str, str, list[str]] | None = None
    continuation_prefix = f"{continuation_label}:"
    for raw_line in section_lines:
        stripped = raw_line.rstrip()
        if not stripped.strip():
            continue
        match = _ENRICHMENT_BULLET_RE.match(stripped.strip())
        if match:
            if current is not None:
                entries.append(current)
            current = (match.group("name").strip(), match.group("body").strip(), [])
            continue
        # Continuation line — must be indented and belong to the current entry
        if current is None:
            continue
        indented = raw_line.startswith(" ") or raw_line.startswith("\t")
        if not indented:
            continue
        content = stripped.strip()
        if content.startswith(continuation_prefix):
            values_raw = content[len(continuation_prefix) :]
            current = (current[0], current[1], _split_csv(values_raw))
    if current is not None:
        entries.append(current)
    return entries


def _parse_enum_notes(section_lines: list[str]) -> list[EnumNote]:
    """Parse the `## Enums & constants` section body into EnumNote objects."""
    return [
        EnumNote(name=name, role=role, values=values)
        for name, role, values in _parse_enrichment_entries(section_lines, "Values")
    ]


def _parse_call_path_notes(section_lines: list[str]) -> list[CallPathNote]:
    """Parse the `## Call paths` section body into CallPathNote objects."""
    return [
        CallPathNote(entry=entry, narrative=narrative, key_hops=key_hops)
        for entry, narrative, key_hops in _parse_enrichment_entries(section_lines, "Key hops")
    ]


def _parse_data_flow_notes(section_lines: list[str]) -> list[DataFlowNote]:
    """Parse the `## Data flows` section body into DataFlowNote objects.

    Each bullet has the format: `- **{parameter}** in **{location}** — {effect}`
    """
    notes: list[DataFlowNote] = []
    for raw_line in section_lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = _DATA_FLOW_BULLET_RE.match(stripped)
        if match:
            notes.append(
                DataFlowNote(
                    parameter=match.group("parameter").strip(),
                    location=match.group("location").strip(),
                    effect=match.group("effect").strip(),
                )
            )
    return notes


def _parse_reexports(section_lines: list[str]) -> dict[str, list[str]]:
    """Parse the `## Re-exports` section body into a source-module → names map.

    Each bullet has the format: ``- From `<source-module>`: Name1, Name2, Name3``.
    Returns an empty dict when no bullets are present (e.g. malformed section).
    """
    reexports: dict[str, list[str]] = {}
    for raw_line in section_lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = _REEXPORTS_BULLET_RE.match(stripped)
        if match:
            source = match.group("source").strip()
            names = _split_csv(match.group("names"))
            reexports[source] = names
    return reexports


def _parse_footer(footer_body: str) -> StalenessMetadata | None:
    """Parse YAML-style key: value lines from a multi-line footer body."""
    attrs: dict[str, str] = {}
    for line in footer_body.splitlines():
        line = line.strip()
        if not line:
            continue
        if ": " in line:
            key, _, value = line.partition(": ")
            attrs[key.strip()] = value.strip()
    return _attrs_to_metadata(attrs)


def _parse_inline_footer(inline_body: str) -> StalenessMetadata | None:
    """Parse the contents of a compact inline footer (``{k: v, k: v}``).

    ``inline_body`` is the text captured between ``{`` and ``}`` in the
    ``<!-- lexibrary:meta {...} -->`` form. The contents are interpreted
    as a YAML flow mapping via ``yaml.safe_load(f"{{{inline_body}}}")``.
    """
    try:
        data = yaml.safe_load("{" + inline_body + "}")
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    # Normalise values to strings so _attrs_to_metadata can consume the
    # same dict shape produced by the multi-line parser. yaml.safe_load may
    # yield datetime / int / bool values for unquoted scalars — coerce them
    # back to the string form the downstream constructor expects.
    attrs: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, bool):
            attrs[str(key)] = "true" if value else "false"
        elif isinstance(value, datetime):
            attrs[str(key)] = value.isoformat()
        elif value is None:
            continue
        else:
            attrs[str(key)] = str(value)
    return _attrs_to_metadata(attrs)


def _attrs_to_metadata(attrs: dict[str, str]) -> StalenessMetadata | None:
    """Construct a ``StalenessMetadata`` from a flat string-valued dict."""
    try:
        return StalenessMetadata(
            source=attrs["source"],
            source_hash=attrs["source_hash"],
            interface_hash=attrs.get("interface_hash"),
            design_hash=attrs["design_hash"],
            generated=datetime.fromisoformat(attrs["generated"]),
            generator=attrs["generator"],
            dependents_complete=attrs.get("dependents_complete", "false").strip().lower() == "true",
        )
    except (KeyError, ValueError):
        return None


def _find_footer_metadata(text: str) -> StalenessMetadata | None:
    """Locate a footer (inline or multi-line) in ``text`` and parse it.

    Inline is attempted first because it is the §1.3 canonical form; legacy
    multi-line is the fallback for on-disk files written before §1.3.
    """
    inline = _FOOTER_INLINE_RE.search(text)
    if inline is not None:
        parsed = _parse_inline_footer(inline.group("body"))
        if parsed is not None:
            return parsed
    multi = _FOOTER_MULTILINE_RE.search(text)
    if multi is not None:
        return _parse_footer(multi.group(1))
    return None


def parse_design_file_metadata(path: Path) -> StalenessMetadata | None:
    """Extract only the HTML comment footer from a design file.

    Cheaper than parse_design_file() — searches only the footer.
    Returns None if file doesn't exist or footer is absent/corrupt.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _find_footer_metadata(text)


def parse_design_file_frontmatter(path: Path) -> DesignFileFrontmatter | None:
    """Extract only the YAML frontmatter from a design file.

    Returns None if file doesn't exist or frontmatter is absent/invalid.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        data = yaml.safe_load(match.group(1))
        if not isinstance(data, dict):
            return None
        # Parse deprecated_at from ISO string if present
        deprecated_at_raw = data.get("deprecated_at")
        deprecated_at = None
        if deprecated_at_raw is not None:
            if isinstance(deprecated_at_raw, datetime):
                deprecated_at = deprecated_at_raw
            elif isinstance(deprecated_at_raw, str):
                deprecated_at = datetime.fromisoformat(deprecated_at_raw)
        return DesignFileFrontmatter(
            description=data["description"],
            id=data["id"],
            updated_by=data.get("updated_by", "archivist"),
            status=data.get("status", "active"),
            deprecated_at=deprecated_at,
            deprecated_reason=data.get("deprecated_reason"),
        )
    except (yaml.YAMLError, KeyError, ValueError):
        return None


def parse_design_file(path: Path) -> DesignFile | None:
    """Parse a full design file into a DesignFile model.

    Returns None if file doesn't exist or content is malformed (missing
    frontmatter, H1 heading, or metadata footer).
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # --- Frontmatter ---
    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None
    try:
        fm_data = yaml.safe_load(fm_match.group(1))
        if not isinstance(fm_data, dict):
            return None
        # Parse deprecated_at from ISO string if present
        deprecated_at_raw = fm_data.get("deprecated_at")
        deprecated_at = None
        if deprecated_at_raw is not None:
            if isinstance(deprecated_at_raw, datetime):
                deprecated_at = deprecated_at_raw
            elif isinstance(deprecated_at_raw, str):
                deprecated_at = datetime.fromisoformat(deprecated_at_raw)
        frontmatter = DesignFileFrontmatter(
            description=fm_data["description"],
            id=fm_data["id"],
            updated_by=fm_data.get("updated_by", "archivist"),
            status=fm_data.get("status", "active"),
            deprecated_at=deprecated_at,
            deprecated_reason=fm_data.get("deprecated_reason"),
        )
    except (yaml.YAMLError, KeyError, ValueError):
        return None

    # Strip frontmatter block from text for further parsing
    body_text = text[fm_match.end() :]
    lines = body_text.splitlines()

    # --- H1 heading = source_path ---
    source_path: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            source_path = stripped[2:].strip()
            break
    if source_path is None:
        return None

    # --- Locate section boundaries ---
    section_starts: dict[str, int] = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("## "):
            section_name = stripped[3:].strip()
            if section_name not in section_starts:
                section_starts[section_name] = i

    def _section_lines(name: str) -> list[str]:
        if name not in section_starts:
            return []
        start = section_starts[name]
        end = len(lines)
        for _, idx in section_starts.items():
            if idx > start:
                end = min(end, idx)
        return lines[start + 1 : end]

    def _section_text(name: str) -> str:
        return "\n".join(ln for ln in _section_lines(name) if ln.strip()).strip()

    def _bullet_list(name: str) -> list[str]:
        result: list[str] = []
        for line in _section_lines(name):
            stripped = line.strip()
            if stripped.startswith("- "):
                result.append(stripped[2:])
        return result

    def _wikilink_list(name: str) -> list[str]:
        """Parse a bullet list of wikilinks, stripping [[]] brackets if present."""
        result: list[str] = []
        for item in _bullet_list(name):
            # Strip [[]] brackets for both bracketed and unbracketed formats
            if item.startswith("[[") and item.endswith("]]"):
                result.append(item[2:-2])
            else:
                result.append(item)
        return result

    # --- Re-exports (aggregator modules) OR Interface Contract ---
    # Aggregator modules carry a ``## Re-exports`` section in place of
    # ``## Interface Contract``. When Re-exports is present, we leave
    # ``interface_contract`` as the empty string (the Pydantic field requires
    # a string, and reexports is the authoritative field for aggregators).
    reexports_raw = _parse_reexports(_section_lines("Re-exports"))
    reexports: dict[str, list[str]] | None = reexports_raw if reexports_raw else None
    if reexports is not None:
        interface_contract = ""
    else:
        contract_lines = _section_lines("Interface Contract")
        # Remove opening ``` line and closing ``` line (outer canonical fence).
        filtered = [ln for ln in contract_lines if ln.strip()]
        if filtered and filtered[0].startswith("```"):
            filtered = filtered[1:]
        if filtered and filtered[-1].strip() == "```":
            filtered = filtered[:-1]
        # Legacy tolerance: some on-disk files (produced before the §1.1 serializer
        # fix) contain a second inner fence wrapped inside the outer fence. Strip
        # an additional inner ```<lang> opener and trailing ``` closer if they
        # remain, so legacy files round-trip to the same logical contract body.
        if filtered and filtered[0].startswith("```"):
            filtered = filtered[1:]
        if filtered and filtered[-1].strip() == "```":
            filtered = filtered[:-1]
        interface_contract = "\n".join(filtered).strip()

    # --- Dependencies / Dependents ---
    dep_lines = _bullet_list("Dependencies")
    dep_lines = [d for d in dep_lines]  # keep as-is (may be empty if "(none)")
    dependents = _bullet_list("Dependents")

    # --- Optional sections ---
    tests = _section_text("Tests") or None
    complexity_warning = _section_text("Complexity Warning") or None
    enum_notes = _parse_enum_notes(_section_lines("Enums & constants"))
    call_path_notes = _parse_call_path_notes(_section_lines("Call paths"))
    data_flow_notes = _parse_data_flow_notes(_section_lines("Data flows"))
    wikilinks = _wikilink_list("Wikilinks")
    tags = _bullet_list("Tags")
    # Recognize both "## Stack" (new) and "## Guardrails" (legacy) for backward compat
    stack_refs = _bullet_list("Stack") or _bullet_list("Guardrails")

    # --- Preserved (non-standard) sections ---
    _standard_sections = {
        "Interface Contract",
        "Re-exports",
        "Dependencies",
        "Dependents",
        "Tests",
        "Complexity Warning",
        "Enums & constants",
        "Call paths",
        "Data flows",
        "Wikilinks",
        "Tags",
        "Stack",
        "Guardrails",
    }
    preserved_sections: dict[str, str] = {}
    for sec_name in section_starts:
        if sec_name not in _standard_sections:
            content_text = _section_text(sec_name)
            if content_text:
                # Strip any metadata footer that may have been captured
                content_text = _FOOTER_ANY_RE.sub("", content_text).strip()
                if content_text:
                    preserved_sections[sec_name] = content_text

    # --- Metadata footer (§1.3 SHARED_BLOCK_B: inline OR legacy multi-line) ---
    metadata = _find_footer_metadata(text)
    if metadata is None:
        return None

    # Use section text for summary (first non-empty paragraph after H1, before first H2)
    # For simplicity: summary = interface_contract section is mandatory; there's no
    # separate "summary" section in the spec. We store summary as empty string --
    # the serializer doesn't emit a "Summary" section. Callers set summary before
    # constructing DesignFile. During parsing, summary is derived from frontmatter description.
    summary = frontmatter.description

    return DesignFile(
        source_path=source_path,
        frontmatter=frontmatter,
        summary=summary,
        interface_contract=interface_contract,
        dependencies=dep_lines,
        dependents=dependents,
        tests=tests,
        complexity_warning=complexity_warning,
        enum_notes=enum_notes,
        call_path_notes=call_path_notes,
        data_flow_notes=data_flow_notes,
        wikilinks=wikilinks,
        tags=tags,
        stack_refs=stack_refs,
        preserved_sections=preserved_sections,
        reexports=reexports,
        metadata=metadata,
    )
