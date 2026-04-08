"""Parser for concept file artifacts from markdown format."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from lexibrary.artifacts.concept import ConceptFile, ConceptFileFrontmatter
from lexibrary.wiki.patterns import extract_wikilinks as _extract_wikilinks

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
# Backtick-delimited paths containing "/" and ending with a known extension
_FILE_REF_RE = re.compile(
    r"`([^`]*?/[^`]+\.(?:py|ts|tsx|js|jsx|yaml|yml|toml|md|json|css|html|sql|sh|rs|go))`"
)


def parse_concept_file(path: Path) -> ConceptFile | None:
    """Parse a concept file into a ConceptFile model.

    Returns None if the file doesn't exist, has no frontmatter, or
    frontmatter fails validation.
    """
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm_match = _FRONTMATTER_RE.match(text)
    if not fm_match:
        return None

    try:
        data = yaml.safe_load(fm_match.group(1))
        if not isinstance(data, dict):
            return None
        frontmatter = ConceptFileFrontmatter(**data)
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        # Pydantic validation errors are ValueError subclasses
        _ = exc
        return None

    body = text[fm_match.end() :]

    summary = _extract_summary(body)
    related_concepts = _extract_wikilinks(body)
    linked_files = _FILE_REF_RE.findall(body)
    decision_log = _extract_decision_log(body)

    return ConceptFile(
        frontmatter=frontmatter,
        body=body,
        summary=summary,
        related_concepts=related_concepts,
        linked_files=linked_files,
        decision_log=decision_log,
        file_path=path,
    )


def _extract_summary(body: str) -> str:
    """Extract the first non-empty paragraph before any ## heading."""
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    # Join and take first non-empty paragraph (split on blank lines)
    text = "\n".join(lines).strip()
    if not text:
        return ""
    paragraphs = re.split(r"\n\s*\n", text)
    for para in paragraphs:
        stripped = para.strip()
        if stripped:
            return stripped
    return ""


def _extract_decision_log(body: str) -> list[str]:
    """Extract bullet items from a ## Decision Log section."""
    in_section = False
    items: list[str] = []
    for line in body.splitlines():
        if line.startswith("## Decision Log"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                items.append(stripped[2:])
    return items
