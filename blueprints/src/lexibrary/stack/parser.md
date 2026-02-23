# stack/parser

**Summary:** Parses Stack post markdown files with YAML frontmatter into `StackPost` models — extracts problem/evidence sections and answer blocks.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `parse_stack_post` | `(path: Path) -> StackPost \| None` | Parse a Stack post file; returns `None` if file doesn't exist, has no valid frontmatter, or fails validation |

## Internal Functions

| Name | Purpose |
| --- | --- |
| `_extract_problem_and_evidence` | Extract `## Problem` content and `### Evidence` bullet items from body |
| `_extract_answers` | Find all `### A{n}` answer blocks and parse each |
| `_parse_single_answer` | Parse a single answer block: metadata line, body, `#### Comments` section |

## Regex Patterns

- `_FRONTMATTER_RE` -- `^---\n(.*?)\n---\n?` matches YAML frontmatter block
- `_ANSWER_HEADER_RE` -- `^###\s+A(\d+)\s*$` matches answer headers like `### A1`
- `_METADATA_RE` -- extracts `**Date:** ... | **Author:** ... | **Votes:** ...` with optional `**Accepted:** true`

## Dependencies

- `lexibrarian.stack.models` -- `StackAnswer`, `StackPost`, `StackPostFrontmatter`

## Dependents

- `lexibrarian.stack.index` -- `StackIndex.build()` calls `parse_stack_post` for each file
- `lexibrarian.stack.mutations` -- `_load_post()` calls `parse_stack_post`
- `lexibrarian.cli` -- `stack_view` command

## Key Concepts

- Graceful failure: returns `None` on any parse error (missing file, bad YAML, validation failure)
- Section parsing is line-based: tracks `in_problem`/`in_evidence` state and resets on encountering new `##` or `### A{n}` headers
- Answer metadata line is optional — defaults to today's date, `"unknown"` author, 0 votes if not found
