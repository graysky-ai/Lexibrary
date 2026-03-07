"""Parser for design file artifacts from markdown format."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import yaml

from lexibrary.artifacts.design_file import DesignFile, DesignFileFrontmatter, StalenessMetadata

# Multiline HTML comment footer: <!-- lexibrary:meta\nkey: value\n-->
_FOOTER_RE = re.compile(r"<!--\s*lexibrary:meta\n(.*?)\n-->", re.DOTALL)
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_footer(footer_body: str) -> StalenessMetadata | None:
    """Parse YAML-style key: value lines from the footer body."""
    attrs: dict[str, str] = {}
    for line in footer_body.splitlines():
        line = line.strip()
        if not line:
            continue
        if ": " in line:
            key, _, value = line.partition(": ")
            attrs[key.strip()] = value.strip()
    try:
        return StalenessMetadata(
            source=attrs["source"],
            source_hash=attrs["source_hash"],
            interface_hash=attrs.get("interface_hash"),
            design_hash=attrs["design_hash"],
            generated=datetime.fromisoformat(attrs["generated"]),
            generator=attrs["generator"],
        )
    except (KeyError, ValueError):
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
    match = _FOOTER_RE.search(text)
    if not match:
        return None
    return _parse_footer(match.group(1))


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

    # --- Interface Contract (strip fenced code block delimiters) ---
    contract_lines = _section_lines("Interface Contract")
    # Remove opening ``` line and closing ``` line
    filtered = [ln for ln in contract_lines if ln.strip()]
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
    wikilinks = _wikilink_list("Wikilinks")
    tags = _bullet_list("Tags")
    # Recognize both "## Stack" (new) and "## Guardrails" (legacy) for backward compat
    stack_refs = _bullet_list("Stack") or _bullet_list("Guardrails")

    # --- Metadata footer ---
    footer_match = _FOOTER_RE.search(text)
    if not footer_match:
        return None
    metadata = _parse_footer(footer_match.group(1))
    if metadata is None:
        return None

    # Use section text for summary (first non-empty paragraph after H1, before first H2)
    # For simplicity: summary = interface_contract section is mandatory; there's no
    # separate "summary" section in the spec. We store summary as empty string —
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
        wikilinks=wikilinks,
        tags=tags,
        stack_refs=stack_refs,
        metadata=metadata,
    )
