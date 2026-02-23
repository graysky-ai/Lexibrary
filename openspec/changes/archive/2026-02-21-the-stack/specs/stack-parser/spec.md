## ADDED Requirements

### Requirement: Parse stack post from file
The system SHALL provide a `parse_stack_post(path: Path) -> StackPost | None` function in `src/lexibrary/stack/parser.py` that:
- Extracts YAML frontmatter between `---` delimiters into `StackPostFrontmatter`
- Extracts `## Problem` section content into `problem` field
- Extracts `### Evidence` items (bullet list) into `evidence` field
- Parses `### A{n}` answer blocks with metadata line (`Date`, `Author`, `Votes`, `Accepted`) and body
- Parses `#### Comments` sections within answers as raw string lines
- Returns `None` if the file does not exist or is malformed
- Stores the full body text in `raw_body`

#### Scenario: Parse well-formed post with answers
- **WHEN** `parse_stack_post()` is called on a valid post file with 2 answers and comments
- **THEN** it SHALL return a `StackPost` with correctly populated frontmatter, problem, evidence, and 2 `StackAnswer` objects with their comments

#### Scenario: Parse post with no answers
- **WHEN** `parse_stack_post()` is called on a post file that has only `## Problem` and `### Evidence` sections
- **THEN** it SHALL return a `StackPost` with `answers=[]`

#### Scenario: Parse post with accepted answer
- **WHEN** `parse_stack_post()` is called on a post where an answer has `**Accepted:** true`
- **THEN** the corresponding `StackAnswer` SHALL have `accepted=True`

#### Scenario: Parse nonexistent file
- **WHEN** `parse_stack_post()` is called on a path that does not exist
- **THEN** it SHALL return `None`

#### Scenario: Parse malformed file
- **WHEN** `parse_stack_post()` is called on a file with invalid YAML frontmatter
- **THEN** it SHALL return `None`

### Requirement: Parse answer metadata line
The parser SHALL extract answer metadata from lines matching the format:
`**Date:** <date> | **Author:** <author> | **Votes:** <votes>` with optional `| **Accepted:** true`

#### Scenario: Parse metadata with accepted flag
- **WHEN** an answer block contains `**Date:** 2026-02-21 | **Author:** agent-456 | **Votes:** 2 | **Accepted:** true`
- **THEN** the parser SHALL set `date=date(2026, 2, 21)`, `author="agent-456"`, `votes=2`, `accepted=True`

#### Scenario: Parse metadata without accepted flag
- **WHEN** an answer block contains `**Date:** 2026-02-21 | **Author:** agent-456 | **Votes:** -1`
- **THEN** the parser SHALL set `accepted=False`

### Requirement: Parse comment lines with vote context
The parser SHALL recognize comment lines containing `[upvote]` or `[downvote]` context markers and preserve them as raw strings.

#### Scenario: Parse downvote comment
- **WHEN** a comment line contains `**2026-02-22 agent-123 [downvote]:** This approach is unreliable.`
- **THEN** the full line SHALL be stored in the answer's `comments` list
