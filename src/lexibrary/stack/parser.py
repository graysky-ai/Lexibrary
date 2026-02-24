"""Parser for Stack post files from markdown format with YAML frontmatter."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import yaml

from lexibrary.exceptions import ConfigError
from lexibrary.stack.models import (
    StackAnswer,
    StackPost,
    StackPostFrontmatter,
)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_ANSWER_HEADER_RE = re.compile(r"^###\s+A(\d+)\s*$")
_METADATA_RE = re.compile(
    r"\*\*Date:\*\*\s*(\S+)\s*\|\s*"
    r"\*\*Author:\*\*\s*(\S+)\s*\|\s*"
    r"\*\*Votes:\*\*\s*(-?\d+)"
    r"(?:\s*\|\s*\*\*Accepted:\*\*\s*(true))?"
)


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
        raise ConfigError(
            f"Failed to parse Stack post frontmatter in {path}: {exc}"
        ) from exc

    raw_body = text[fm_match.end() :]
    problem, evidence = _extract_problem_and_evidence(raw_body)
    answers = _extract_answers(raw_body)

    return StackPost(
        frontmatter=frontmatter,
        problem=problem,
        evidence=evidence,
        answers=answers,
        raw_body=raw_body,
    )


def _extract_problem_and_evidence(body: str) -> tuple[str, list[str]]:
    """Extract ## Problem content and ### Evidence bullet items."""
    lines = body.splitlines()
    problem_lines: list[str] = []
    evidence_items: list[str] = []
    in_problem = False
    in_evidence = False

    for line in lines:
        # Check for section headers
        if line.startswith("## Problem"):
            in_problem = True
            in_evidence = False
            continue
        if line.startswith("### Evidence"):
            in_problem = False
            in_evidence = True
            continue
        # Any other ## or ### A{n} header ends current section
        if line.startswith("## ") or _ANSWER_HEADER_RE.match(line):
            in_problem = False
            in_evidence = False
            continue

        if in_problem:
            problem_lines.append(line)
        elif in_evidence:
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                evidence_items.append(stripped[2:])

    problem = "\n".join(problem_lines).strip()
    return problem, evidence_items


def _extract_answers(body: str) -> list[StackAnswer]:
    """Extract ### A{n} answer blocks from the body."""
    lines = body.splitlines()
    answers: list[StackAnswer] = []

    # Find all answer block start indices
    answer_starts: list[tuple[int, int]] = []  # (line_index, answer_number)
    for i, line in enumerate(lines):
        m = _ANSWER_HEADER_RE.match(line)
        if m:
            answer_starts.append((i, int(m.group(1))))

    for idx, (start_line, answer_num) in enumerate(answer_starts):
        # Determine end of this answer block
        end_line = answer_starts[idx + 1][0] if idx + 1 < len(answer_starts) else len(lines)

        answer_lines = lines[start_line + 1 : end_line]
        answer = _parse_single_answer(answer_num, answer_lines)
        if answer is not None:
            answers.append(answer)

    return answers


def _parse_single_answer(number: int, lines: list[str]) -> StackAnswer | None:
    """Parse a single answer block from its content lines."""
    answer_date = date.today()
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
                    answer_date = date.fromisoformat(m.group(1))
                except ValueError:
                    answer_date = date.today()
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

    return StackAnswer(
        number=number,
        date=answer_date,
        author=author,
        votes=votes,
        accepted=accepted,
        body=body,
        comments=comments,
    )
