## ADDED Requirements

### Requirement: StackPostRefs model
The system SHALL define a `StackPostRefs` Pydantic 2 model in `src/lexibrary/stack/models.py` with fields:
- `concepts` (list[str]) — related concept names, default `[]`
- `files` (list[str]) — related source file paths, default `[]`
- `designs` (list[str]) — related design file paths, default `[]`

#### Scenario: Create empty refs
- **WHEN** a `StackPostRefs` is created with no arguments
- **THEN** `concepts`, `files`, and `designs` SHALL all default to empty lists

#### Scenario: Create refs with values
- **WHEN** a `StackPostRefs` is created with `concepts=["DateHandling"]`, `files=["src/models/event.py"]`
- **THEN** all provided values SHALL be stored correctly

### Requirement: StackPostFrontmatter model
The system SHALL define a `StackPostFrontmatter` Pydantic 2 model in `src/lexibrary/stack/models.py` with fields:
- `id` (str) — auto-assigned `ST-NNN` identifier
- `title` (str) — short problem description
- `tags` (list[str]) — lowercase labels, minimum 1 tag required
- `status` (Literal["open", "resolved", "outdated", "duplicate"]) — default `"open"`
- `created` (date) — ISO date of post creation
- `author` (str) — agent session ID or human identifier
- `bead` (str | None) — optional Bead ID for traceability, default `None`
- `votes` (int) — net vote count (up minus down), default `0`
- `duplicate_of` (str | None) — `ST-NNN` pointer when status is `duplicate`, default `None`
- `refs` (StackPostRefs) — cross-references, default `StackPostRefs()`

#### Scenario: Create frontmatter with required fields
- **WHEN** a `StackPostFrontmatter` is created with `id="ST-001"`, `title="Test"`, `tags=["bug"]`, `created=date(2026, 2, 21)`, `author="agent-123"`
- **THEN** `status` SHALL default to `"open"`, `votes` to `0`, `bead` to `None`, `duplicate_of` to `None`

#### Scenario: Tags must have at least one element
- **WHEN** a `StackPostFrontmatter` is created with `tags=[]`
- **THEN** Pydantic SHALL raise a `ValidationError`

#### Scenario: Status is constrained to valid values
- **WHEN** a `StackPostFrontmatter` is created with `status="invalid"`
- **THEN** Pydantic SHALL raise a `ValidationError`

#### Scenario: Valid status values accepted
- **WHEN** a `StackPostFrontmatter` is created with `status="resolved"`
- **THEN** the model SHALL validate successfully

### Requirement: StackAnswer model
The system SHALL define a `StackAnswer` Pydantic 2 model in `src/lexibrary/stack/models.py` with fields:
- `number` (int) — answer number (1, 2, 3...)
- `date` (date) — date the answer was added
- `author` (str) — agent session ID or human identifier
- `votes` (int) — net vote count, default `0`
- `accepted` (bool) — whether this answer is accepted, default `False`
- `body` (str) — answer content
- `comments` (list[str]) — raw comment lines, default `[]`

#### Scenario: Create answer with defaults
- **WHEN** a `StackAnswer` is created with `number=1`, `date=date(2026, 2, 21)`, `author="agent-456"`, `body="Solution text"`
- **THEN** `votes` SHALL default to `0`, `accepted` to `False`, `comments` to `[]`

#### Scenario: Answer with comments
- **WHEN** a `StackAnswer` is created with `comments=["2026-02-21 agent-789: Good point"]`
- **THEN** comments SHALL be stored as raw string lines

### Requirement: StackPost model
The system SHALL define a `StackPost` Pydantic 2 model in `src/lexibrary/stack/models.py` with fields:
- `frontmatter` (StackPostFrontmatter) — mutable metadata
- `problem` (str) — `## Problem` section content
- `evidence` (list[str]) — `### Evidence` items, default `[]`
- `answers` (list[StackAnswer]) — parsed answers, default `[]`
- `raw_body` (str) — full body text for preservation, default `""`

#### Scenario: Create post with no answers
- **WHEN** a `StackPost` is created with `frontmatter` and `problem="Some problem"`
- **THEN** `answers` SHALL default to `[]` and `evidence` to `[]`

#### Scenario: Create post with answers
- **WHEN** a `StackPost` is created with two `StackAnswer` objects
- **THEN** `answers` SHALL contain both answers in order

### Requirement: Stack module public API
`src/lexibrary/stack/__init__.py` SHALL re-export: `StackPost`, `StackAnswer`, `StackPostFrontmatter`, `StackPostRefs`.

#### Scenario: StackPost importable from stack module
- **WHEN** `from lexibrary.stack import StackPost` is used
- **THEN** the import SHALL succeed
