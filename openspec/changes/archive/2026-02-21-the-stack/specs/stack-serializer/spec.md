## ADDED Requirements

### Requirement: Serialize stack post to markdown
The system SHALL provide a `serialize_stack_post(post: StackPost) -> str` function in `src/lexibrary/stack/serializer.py` that produces a markdown string with:
1. YAML frontmatter delimited by `---` containing all `StackPostFrontmatter` fields
2. `## Problem` section with the problem description
3. `### Evidence` section with evidence items as a bullet list
4. `## Answers` section containing answer blocks
5. Each answer as `### A{n}` with metadata line, body, and `#### Comments` section
6. Trailing newline

#### Scenario: Serialize post with no answers
- **WHEN** `serialize_stack_post()` is called on a `StackPost` with no answers
- **THEN** the output SHALL contain YAML frontmatter, `## Problem`, `### Evidence`, but no `## Answers` section

#### Scenario: Serialize post with answers and comments
- **WHEN** `serialize_stack_post()` is called on a `StackPost` with 2 answers (one with comments)
- **THEN** the output SHALL contain `### A1` and `### A2` blocks, each with metadata lines, and the first answer's `#### Comments` section

#### Scenario: Serialize accepted answer
- **WHEN** `serialize_stack_post()` is called with an answer where `accepted=True`
- **THEN** the answer metadata line SHALL include `| **Accepted:** true`

#### Scenario: Serialize answer with negative votes
- **WHEN** an answer has `votes=-1`
- **THEN** the metadata line SHALL show `**Votes:** -1`

### Requirement: YAML frontmatter serialization
The serializer SHALL output YAML frontmatter with nested `refs` block containing `concepts`, `files`, and `designs` lists. Empty lists SHALL still be serialized (not omitted). The `bead` and `duplicate_of` fields SHALL be serialized as `null` when None.

#### Scenario: Serialize refs with values
- **WHEN** a post has `refs.concepts=["DateHandling"]` and `refs.files=["src/foo.py"]`
- **THEN** the YAML frontmatter SHALL contain a `refs:` block with the populated lists

#### Scenario: Serialize null optional fields
- **WHEN** a post has `bead=None` and `duplicate_of=None`
- **THEN** the YAML SHALL contain `bead: null` and `duplicate_of: null`

### Requirement: Round-trip integrity
A `StackPost` serialized with `serialize_stack_post()` and then parsed with `parse_stack_post()` SHALL produce an equivalent `StackPost` model.

#### Scenario: Round-trip with all fields
- **WHEN** a fully populated `StackPost` is serialized and parsed back
- **THEN** all fields SHALL match the original
