"""Parser for Stack post files from markdown format with YAML frontmatter."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

from lexibrary.exceptions import ConfigError
from lexibrary.stack.models import (
    StackFinding,
    StackPost,
    StackPostFrontmatter,
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_FINDING_HEADER_RE = re.compile(r"^###\s+F(\d+)\s*$")
_METADATA_RE = re.compile(
    r"\*\*Date:\*\*\s*(\S+)\s*\|\s*"
    r"\*\*Author:\*\*\s*(\S+)\s*\|\s*"
    r"\*\*Votes:\*\*\s*(-?\d+)"
    r"(?:\s*\|\s*\*\*Accepted:\*\*\s*(true))?"
)


_HTML_COMMENT_RE = re.compile(r"^\s*<!--.*-->\s*$")


def parse_stack_post(path: Path) -> StackPost | None:
    """Parse a Stack post file into a StackPost model.

    Returns None if the file doesn't exist, has no valid frontmatter,
    or frontmatter fails validation.
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
        frontmatter = StackPostFrontmatter(**data)
    except (yaml.YAMLError, TypeError, ValueError) as exc:
        raise ConfigError(f"Failed to parse Stack post frontmatter in {path}: {exc}") from exc

    raw_body = text[fm_match.end() :]
    problem, context, evidence, attempts = _extract_body_sections(raw_body)
    findings = _extract_findings(raw_body)

    return StackPost(
        frontmatter=frontmatter,
        problem=problem,
        context=context,
        evidence=evidence,
        attempts=attempts,
        findings=findings,
        raw_body=raw_body,
    )


def _extract_body_sections(body: str) -> tuple[str, str, list[str], list[str]]:
    """Extract body sections: Problem, Context, Evidence, and Attempts.

    Uses order-independent section extraction via a ``current_section``
    state variable.  Sections are identified by their header and collected
    regardless of position.  A ``## Findings`` or ``### F{n}`` header
    terminates all body section extraction.

    HTML comment lines (``<!-- ... -->``) are stripped from extracted content.

    Returns:
        (problem, context, evidence, attempts) tuple.
    """
    lines = body.splitlines()
    problem_lines: list[str] = []
    context_lines: list[str] = []
    evidence_items: list[str] = []
    attempts_items: list[str] = []
    current_section: str | None = None

    for line in lines:
        # ## Findings or ### F{n} terminates body section extraction
        if line.startswith("## Findings") or _FINDING_HEADER_RE.match(line):
            break

        # Check for section headers
        if line.startswith("## Problem"):
            current_section = "problem"
            continue
        if line.startswith("### Context"):
            current_section = "context"
            continue
        if line.startswith("### Evidence"):
            current_section = "evidence"
            continue
        if line.startswith("### Attempts"):
            current_section = "attempts"
            continue
        # Any other ## or ### header ends current section
        if line.startswith("## ") or line.startswith("### "):
            current_section = None
            continue

        # Skip HTML comment lines
        if _HTML_COMMENT_RE.match(line):
            continue

        if current_section == "problem":
            problem_lines.append(line)
        elif current_section == "context":
            context_lines.append(line)
        elif current_section == "evidence":
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                evidence_items.append(stripped[2:])
        elif current_section == "attempts":
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                attempts_items.append(stripped[2:])

    problem = "\n".join(problem_lines).strip()
    context = "\n".join(context_lines).strip()
    return problem, context, evidence_items, attempts_items


def _extract_findings(body: str) -> list[StackFinding]:
    """Extract ### F{n} finding blocks from the body."""
    lines = body.splitlines()
    findings: list[StackFinding] = []

    # Find all finding block start indices
    finding_starts: list[tuple[int, int]] = []  # (line_index, finding_number)
    for i, line in enumerate(lines):
        m = _FINDING_HEADER_RE.match(line)
        if m:
            finding_starts.append((i, int(m.group(1))))

    for idx, (start_line, finding_num) in enumerate(finding_starts):
        # Determine end of this finding block
        end_line = finding_starts[idx + 1][0] if idx + 1 < len(finding_starts) else len(lines)

        finding_lines = lines[start_line + 1 : end_line]
        finding = _parse_single_finding(finding_num, finding_lines)
        if finding is not None:
            findings.append(finding)

    return findings


def _parse_single_finding(number: int, lines: list[str]) -> StackFinding | None:
    """Parse a single finding block from its content lines."""
    finding_date = date.today()
    author = "unknown"
    votes = 0
    accepted = False
    body_lines: list[str] = []
    comments: list[str] = []
    in_comments = False
    metadata_found = False

    for line in lines:
        # Check for comments section
        if line.strip() == "#### Comments":
            in_comments = True
            continue

        # Check for metadata line (first occurrence only)
        if not metadata_found:
            m = _METADATA_RE.search(line)
            if m:
                try:
                    finding_date = date.fromisoformat(m.group(1))
                except ValueError:
                    finding_date = date.today()
                author = m.group(2)
                votes = int(m.group(3))
                accepted = m.group(4) == "true"
                metadata_found = True
                continue

        if in_comments:
            stripped = line.strip()
            if stripped:
                comments.append(stripped)
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    return StackFinding(
        number=number,
        date=finding_date,
        author=author,
        votes=votes,
        accepted=accepted,
        body=body,
        comments=comments,
    )
