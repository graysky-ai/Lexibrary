# Phase 6 — The Stack

**Reference:** `plans/v2-master-plan.md` (Phase 6 section), `lexibrary-overview.md` (section 6)
**Depends on:** Phase 1 (Foundation), Phase 4 (Archivist), Phase 5 (Concepts Wiki — wikilink resolver)
**Consumed by:** Phase 7 (Validation & Search), Phase 8 (Agent Setup)

---

## Sub-Phases

Phase 6 is structured into sub-phases. Core model work (6a) must come first; then several tracks can run in parallel.

| Sub-Phase | Name | Depends On | Can Parallel With | Task Groups |
|-----------|------|------------|-------------------|-------------|
| **6a** | Models & Parser/Serializer | Phase 1 | — | TG1 |
| **6b** | Stack Index & Search | 6a | 6c, 6e, 6f | TG2 |
| **6c** | Mutations & Voting | 6a | 6b, 6e, 6f | TG3 |
| **6d** | CLI Commands | 6a, 6b, 6c | 6e, 6f | TG4 |
| **6e** | Design File Integration | 6a, Phase 4 | 6b, 6c, 6f | TG5 |
| **6f** | Wikilink Resolver Update | 6a, Phase 5 | 6b, 6c, 6e | TG6 |
| **6g** | Unified Search | 6b, Phase 5 | 6d | TG7 |
| **6h** | Init & Scaffolding Update | 6a | any | TG8 |

**Critical path:** 6a → 6b + 6c (parallel) → 6d
**Independent tracks:** 6e (design file integration) and 6f (resolver update) can run any time after 6a

---

## Goal

A Stack Overflow–inspired knowledge base embedded in the codebase where agents record problems, solutions, and hard-won lessons. Posts are searchable, votable, and cross-linked to concepts, design files, and source code. Agents create posts when they solve non-trivial problems, add answers when they find alternatives, and search The Stack before debugging. The Stack grows organically alongside the codebase — a living record of what's been tried, what failed, and what works.

---

## Decisions Made

| # | Decision | Resolution |
|---|----------|------------|
| D-035 | Rename Guardrail Forum → The Stack | All references to "guardrails" in the architecture become "The Stack" or "stack posts." CLI command group is `lexi stack`. Directory is `.lexibrary/stack/`. Wikilink pattern changes from `GR-NNN` to `ST-NNN`. |
| D-036 | Vote model | Posts and answers have a `votes` field (net: up minus down). Individual vote actions are recorded as comments that show `[upvote]` or `[downvote]` context. Downvotes require an accompanying comment explaining why. |
| D-037 | Tags unified across artifact types | Tags in Stack posts, concepts, and design files share the same namespace (lowercase, hyphenated). `lexi search --tag auth` returns results from all three artifact types in a single query. |
| D-038 | Unified search | `lexi search` is the single cross-artifact search command. Returns ranked results from design files, concepts, and Stack posts. Specialized commands (`lexi concepts`, `lexi stack search`) still exist for focused browsing. |
| D-039 | Post storage model | Markdown files with YAML frontmatter (mutable: votes, status, accepted) and append-only body (answers and comments are only ever appended, never edited or deleted). |
| D-040 | Post statuses | `open`, `resolved`, `outdated`, `duplicate`. Status lives in frontmatter. Transitions: open → resolved (answer accepted), any → outdated (referenced files changed), any → duplicate (with `duplicate_of` pointer). |
| D-041 | Staleness detection | When source files referenced by a post change significantly (hash comparison during `lexi update`), the post is flagged by `lexi validate`. Agents verify or mark outdated. |
| D-042 | Downvotes require comment | A downvote without explanation is noise. The CLI enforces that `lexi stack vote <id> down` requires a `--comment` flag. The comment is appended to the answer with `[downvote]` context. |
| D-043 | Wikilink pattern | Stack posts use `[[ST-NNN]]` wikilink pattern (e.g., `[[ST-001]]`). The resolver (from Phase 5) is extended to recognise `ST-NNN` alongside concept names. |
| D-044 | Bead integration | Optional `bead` field in frontmatter links a post to a Bead ID for traceability. No hard dependency on Beads — field is simply omitted if not using Beads. |

---

## Post Format

Each post is a single markdown file in `.lexibrary/stack/`. Naming convention: `ST-NNN-<slug>.md` (e.g., `ST-001-timezone-naive-datetimes.md`).

### YAML Frontmatter (mutable)

```yaml
---
id: ST-001
title: "Timezone-naive datetimes cause silent data corruption"
tags: [datetime, data-integrity, utils]
status: open               # open | resolved | outdated | duplicate
created: 2026-02-21
author: agent-session-abc123
bead: null                 # optional Bead ID
votes: 3                   # net score (up - down)
duplicate_of: null         # ST-NNN if duplicate
refs:
  concepts: [DateHandling, UTCConvention]
  files: [src/models/event.py, src/api/events.py]
  designs: [src/models/event.py.md]
---
```

| Field | Type | Required | Mutable | Description |
|-------|------|----------|---------|-------------|
| `id` | string | yes | no | Auto-assigned `ST-NNN` ID |
| `title` | string | yes | no | Short problem description |
| `tags` | list[string] | yes | yes | Lowercase labels — shared namespace with concepts and design files |
| `status` | enum | yes | yes | `open`, `resolved`, `outdated`, `duplicate` |
| `created` | date | yes | no | ISO date of post creation |
| `author` | string | yes | no | Agent session ID or human identifier |
| `bead` | string | no | no | Bead ID for traceability (if using Beads) |
| `votes` | int | yes | yes | Net vote count (up minus down) |
| `duplicate_of` | string | no | yes | `ST-NNN` pointer when status is `duplicate` |
| `refs.concepts` | list[string] | no | yes | Related concept names |
| `refs.files` | list[string] | no | yes | Related source file paths |
| `refs.designs` | list[string] | no | yes | Related design file paths |

### Markdown Body (append-only)

```markdown
## Problem

Using `datetime.now()` anywhere in this codebase produces timezone-naive
datetimes that silently corrupt data when compared against the DB (which
stores UTC).

### Evidence
- Test failure: `tests/test_events.py::test_event_overlap`
- Stack trace: `TypeError: can't compare offset-naive and offset-aware datetimes`

---

## Answers

### A1
**Date:** 2026-02-21 | **Author:** agent-session-def456 | **Votes:** 2 | **Accepted:** true

All datetime creation must go through `utils/time.py:now()` which enforces
UTC. The linter rule `TZ001` catches bare `datetime.now()` calls.

**Refs:** [[UTCConvention]], `src/utils/time.py`

#### Comments
- **2026-02-21 agent-session-ghi789:** Also need to patch `datetime.utcnow()`
  which is deprecated in Python 3.12+.

---

### A2
**Date:** 2026-02-22 | **Author:** agent-session-xyz000 | **Votes:** -1

Wrapping individual call sites with `timezone.now()` also works.

#### Comments
- **2026-02-22 agent-session-abc123 [downvote]:** This approach misses call
  sites and causes intermittent bugs. The centralized `utils/time.py` approach
  (A1) is more reliable.
```

### Body Sections

| Section | Required | Append-only | Description |
|---------|----------|-------------|-------------|
| `## Problem` | yes | yes (initial write) | Problem description with evidence |
| `### Evidence` | yes | yes | Test failures, stack traces, observable behaviour |
| `## Answers` | no | yes (new answers appended) | Solution attempts |
| `### A{n}` | — | yes | Individual answer with date, author, votes, accepted flag |
| `#### Comments` | — | yes | Comments on an answer, showing vote context |

### Append-Only Enforcement

The body is append-only at the application level. The CLI provides `stack answer` and `stack vote` (which appends a comment) — no edit or delete commands. This is a soft constraint: users can edit files directly, but the tooling never offers it. Git history provides full audit trail.

Frontmatter mutations (votes, status, accepted) are the exception — these are metadata updates that don't alter the evidence record.

---

## StackPost Model

```python
class StackPostRefs(BaseModel):
    concepts: list[str] = []
    files: list[str] = []
    designs: list[str] = []

class StackPostFrontmatter(BaseModel):
    id: str                                        # ST-NNN
    title: str
    tags: list[str] = Field(min_length=1)
    status: Literal["open", "resolved", "outdated", "duplicate"] = "open"
    created: date
    author: str
    bead: str | None = None
    votes: int = 0
    duplicate_of: str | None = None
    refs: StackPostRefs = StackPostRefs()

class StackAnswer(BaseModel):
    number: int                                    # 1, 2, 3...
    date: date
    author: str
    votes: int = 0
    accepted: bool = False
    body: str
    comments: list[str] = []                       # raw comment lines

class StackPost(BaseModel):
    frontmatter: StackPostFrontmatter
    problem: str                                   # ## Problem section
    evidence: list[str] = []                       # ### Evidence items
    answers: list[StackAnswer] = []
    raw_body: str                                  # full body for preservation
```

---

## New Module: `src/lexibrary/stack/`

```
src/lexibrary/stack/
├── __init__.py          ← Public API re-exports
├── models.py            ← StackPost, StackAnswer, StackPostFrontmatter
├── parser.py            ← Parse stack posts from disk
├── serializer.py        ← Serialize StackPost to markdown
├── index.py             ← Build stack index for search
├── template.py          ← Post template for `lexi stack post`
└── mutations.py         ← Append answer, record vote, update status
```

### Module Responsibilities

**`models.py`** — Pydantic models for posts, answers, frontmatter, refs.

**`parser.py`** — Parse stack post files from disk.
- YAML frontmatter extracted between `---` delimiters
- `## Problem` and `### Evidence` sections extracted
- `### A{n}` answer blocks parsed (date, author, votes, accepted, body, comments)
- Must handle posts with no answers yet (newly created)

**`serializer.py`** — Serialize `StackPost` to markdown.
- Used by `lexi stack post` (initial creation) and `mutations.py` (appending)
- Frontmatter is always fully rewritten (mutable fields)
- Body is serialized in full — the serializer reconstructs from the model, but `mutations.py` handles append operations by parsing, modifying the model, and re-serializing

**`index.py`** — Build the stack index for CLI display and search.

```python
class StackIndex:
    @classmethod
    def build(cls, project_root: Path) -> StackIndex
        """Scan stack/ directory, parse frontmatter from each file."""

    def search(self, query: str) -> list[StackPost]
        """Full-text search across titles, problems, answers, tags."""

    def by_tag(self, tag: str) -> list[StackPost]
        """Filter posts by tag (case-insensitive)."""

    def by_scope(self, path: str) -> list[StackPost]
        """Filter posts by referenced file path (glob matching)."""

    def by_status(self, status: str) -> list[StackPost]
        """Filter posts by status."""

    def by_concept(self, concept: str) -> list[StackPost]
        """Filter posts referencing a specific concept."""
```

**`template.py`** — Template for `lexi stack post`.

```python
def render_post_template(
    post_id: str,
    title: str,
    tags: list[str],
    author: str,
    bead: str | None = None,
    refs_files: list[str] | None = None,
    refs_concepts: list[str] | None = None,
) -> str
```

**`mutations.py`** — State transitions and append operations.

```python
def add_answer(post_path: Path, author: str, body: str) -> StackPost
    """Append a new answer to an existing post."""

def record_vote(
    post_path: Path,
    target: str,       # "post" or "A{n}"
    direction: str,    # "up" or "down"
    author: str,
    comment: str | None = None,  # required for downvotes
) -> StackPost
    """Record a vote on a post or answer. Updates frontmatter vote count
    and appends comment with vote context if provided."""

def accept_answer(post_path: Path, answer_num: int) -> StackPost
    """Mark an answer as accepted. Sets status to resolved."""

def mark_duplicate(post_path: Path, duplicate_of: str) -> StackPost
    """Mark post as duplicate of another post."""

def mark_outdated(post_path: Path) -> StackPost
    """Mark post as outdated (referenced files changed)."""
```

---

## CLI Commands

### Command Group: `lexi stack`

```
lexi stack search <query> [--tag <t>] [--scope <path>] [--status <s>] [--concept <c>]
lexi stack post --title "..." [--tag ...] [--bead <id>] [--file ...] [--concept ...]
lexi stack answer <post-id> --body "..."
lexi stack vote <post-id> [--answer <n>] up|down [--comment "..."]
lexi stack accept <post-id> --answer <n>
lexi stack view <post-id>
lexi stack list [--status <s>] [--tag <t>]
```

### `lexi stack search <query>` — Search posts

Full-text search across titles, problem descriptions, answers, and tags. Returns a ranked compact list.

```
$ lexi stack search "timezone"
ST-001  [resolved] ▲3  Timezone-naive datetimes cause silent data corruption
  Tags: datetime, data-integrity | Refs: src/models/event.py, [[DateHandling]]

ST-015  [open]     ▲1  UTC conversion edge case in DST transitions
  Tags: datetime, timezone | Refs: src/utils/time.py

2 posts found
```

**Flags:**
- `--tag <tag>` — filter by tag
- `--scope <path>` — filter by referenced file path (glob matching)
- `--status <status>` — filter by status (default: all non-outdated)
- `--concept <concept>` — filter by referenced concept

### `lexi stack post` — Create a new post

Creates a new post with auto-assigned ID. Writes the template and outputs the file path.

```
$ lexi stack post --title "datetime.now() causes timezone corruption" \
    --tag datetime --tag data-integrity \
    --file src/models/event.py
Created .lexibrary/stack/ST-001-datetime-now-causes-timezone-corruption.md

Fill in the ## Problem and ### Evidence sections, then add an answer
with `lexi stack answer ST-001 --body "..."` when you have a solution.
```

The agent then writes the problem description directly into the file (or via stdin if we add that). Minimal required flags: `--title` and at least one `--tag`.

### `lexi stack answer <post-id>` — Add an answer

Appends a new answer block to an existing post.

```
$ lexi stack answer ST-001 --body "All datetime creation must go through utils/time.py:now()"
Added answer A1 to ST-001
```

### `lexi stack vote <post-id>` — Vote on a post or answer

Updates vote count in frontmatter. For answer votes, also updates the answer's vote count. Downvotes require `--comment`.

```
$ lexi stack vote ST-001 up
Upvoted ST-001 (now ▲4)

$ lexi stack vote ST-001 --answer 2 down --comment "This misses call sites"
Downvoted A2 on ST-001 (now ▼-1). Comment recorded.
```

### `lexi stack accept <post-id>` — Accept an answer

Marks an answer as accepted and sets post status to `resolved`.

```
$ lexi stack accept ST-001 --answer 1
Accepted A1 on ST-001. Status → resolved.
```

### `lexi stack view <post-id>` — View a post

Displays the full post content with formatting.

```
$ lexi stack view ST-001
# ST-001: Timezone-naive datetimes cause silent data corruption  [resolved] ▲3
Tags: datetime, data-integrity
Refs: src/models/event.py, [[DateHandling]]

## Problem
Using `datetime.now()` anywhere in this codebase...

## Answers

✓ A1 (▲2) — agent-session-def456 — 2026-02-21
  All datetime creation must go through `utils/time.py:now()`...

  A2 (▼-1) — agent-session-xyz000 — 2026-02-22
  Wrapping individual call sites with `timezone.now()`...
```

### `lexi stack list` — Browse posts

```
$ lexi stack list
ST-001  [resolved] ▲3  Timezone-naive datetimes cause silent data corruption
ST-002  [open]     ▲0  Circular import between service modules
ST-003  [resolved] ▲5  Race condition in async payment processing

$ lexi stack list --status open
ST-002  [open]     ▲0  Circular import between service modules
```

---

## Unified Search: `lexi search`

The existing `lexi search` stub becomes the **cross-artifact search command**. It searches design files, concepts, and Stack posts in a single query and returns grouped results.

```
$ lexi search --tag auth
── Concepts ──
Authentication     — JWT-based auth with refresh token rotation
SessionManagement  — Server-side session handling for stateful flows

── Design Files ──
src/api/auth_controller.py  — Handles login/logout/refresh endpoints
src/middleware/jwt.py        — JWT validation middleware

── Stack ──
ST-007  [resolved] ▲4  Refresh token rotation breaks on clock skew
ST-012  [open]     ▲1  OAuth state parameter not validated

$ lexi search "timezone"
── Concepts ──
DateHandling  — UTC-everywhere convention for datetime handling

── Stack ──
ST-001  [resolved] ▲3  Timezone-naive datetimes cause silent data corruption
ST-015  [open]     ▲1  UTC conversion edge case in DST transitions
```

### Search Implementation

**Phase 6 (MVP):** File scanning. Parse YAML frontmatter from all artifacts for structured queries (tags, status, refs). Substring match on titles/summaries/bodies for text queries. Acceptable for < 500 total artifacts.

**Phase 10 (if needed):** SQLite index with full-text search. Schema designed from the start:

```sql
-- Unified search across all artifact types
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,           -- "concept:Auth", "design:src/foo.py", "stack:ST-001"
    artifact_type TEXT NOT NULL,   -- "concept", "design", "stack"
    title TEXT NOT NULL,
    body_text TEXT,                -- searchable text content
    path TEXT NOT NULL             -- file path for retrieval
);

CREATE TABLE artifact_tags (
    artifact_id TEXT,
    tag TEXT,
    PRIMARY KEY (artifact_id, tag)
);

CREATE TABLE artifact_refs (
    artifact_id TEXT,
    ref_type TEXT,                 -- "concept", "file", "design"
    ref_target TEXT
);

-- Stack-specific tables
CREATE TABLE stack_answers (
    post_id TEXT,
    answer_num INTEGER,
    votes INTEGER DEFAULT 0,
    accepted BOOLEAN DEFAULT FALSE,
    body_text TEXT,
    PRIMARY KEY (post_id, answer_num)
);

-- Full-text search across everything
CREATE VIRTUAL TABLE artifacts_fts USING fts5(
    title, body_text, content='artifacts'
);
```

The key design principle: **`lexi search` uses the same interface regardless of backend.** The query API is stable; only the implementation changes from file scanning to SQLite.

---

## Cross-Linking

### Design files reference Stack posts

Design files gain a `## Stack` section (replacing `## Guardrails`):

```markdown
## Stack
- [[ST-001]] Timezone-naive datetimes — use `utils/time.py:now()`
- [[ST-015]] UTC conversion edge case — check boundary conditions
```

The `guardrail_refs` field in `DesignFile` model becomes `stack_refs`.

### Stack posts reference everything

Posts reference concepts, files, and designs via the `refs` frontmatter block. These references are bidirectional at query time — `lexi stack search --scope src/models/` finds posts that reference files under that path.

### Wikilink resolution

The Phase 5 wikilink resolver is extended to handle `ST-NNN` patterns:

```
Resolution order (updated):
1. Strip [[ and ]] brackets
2. Stack pattern check: /^ST-\d{3}/ → scan stack/ directory
3. Concept exact name match (case-sensitive)
4. Concept alias match (case-insensitive)
5. Concept fuzzy match
6. Return UnresolvedLink
```

### `.aindex` files

No change. `.aindex` files don't reference Stack posts.

---

## Staleness Detection

When `lexi validate` (Phase 7) runs, it checks each Stack post's `refs.files` against current source file hashes:

1. For each post, compute SHA-256 of every referenced source file
2. If any file has changed significantly since the post was created (or last verified), flag the post
3. Output: `⚠️ ST-001 may be outdated: src/models/event.py has changed since this post was created`

Agents encountering a flagged post either:
- Verify the solution still applies → update a `last_verified` frontmatter field
- Mark the post outdated → `lexi stack vote ST-001 outdated` (or status update via mutation)

---

## Agent Integration

### When to search The Stack

Agents should search before debugging or attempting a novel approach:

1. **On error** — search by error message or pattern
2. **Before architectural decisions** — search by concept or topic
3. **When design file has Stack refs** — follow the links
4. **When entering a directory** — if `.aindex` mentions relevant Stack posts

### When to create a post

The trigger question: **"Did this take me more than one attempt to solve?"** If yes, post it.

1. **After solving a non-trivial bug** — especially if it involved failed approaches
2. **After discovering a pitfall** — non-obvious constraints or gotchas
3. **After finding documentation was misleading** — correct the record
4. **After a failed approach** — even without a solution yet (open post)

### When to add an answer or comment

1. **Found a better solution** — add a new answer
2. **Existing answer worked** — upvote it
3. **Existing answer didn't work in context** — downvote with comment + optionally add alternative answer
4. **Need to add nuance** — comment on the relevant answer

### Agent environment rules (Phase 8 integration)

```
- Before debugging an unfamiliar error, run `lexi stack search "<error or topic>"`.
  If a post exists with an accepted answer, try that solution first.
- After solving a bug that took >1 attempt, run `lexi stack post` to record
  the problem and solution. Include evidence (test failures, error messages).
- After using a Stack post's solution successfully, run `lexi stack vote <id> up`.
- After finding a Stack post's solution doesn't work, run
  `lexi stack vote <id> --answer <n> down --comment "reason"` and optionally
  add a new answer with `lexi stack answer <id>`.
- When a design file has a `## Stack` section, read the referenced posts before
  modifying the file.
```

### Hooks and automation

**Design file cross-linking:** When `lexi update` generates/refreshes a design file, scan Stack post `refs.files` for matches and auto-populate the `## Stack` section. This is a Phase 7+ enhancement — for Phase 6 MVP, cross-links are manual.

**Post-commit suggestion:** After a commit that changes test status (failures → passing), the agent environment rules suggest creating a Stack post. This is a soft prompt in the rules, not an automated hook.

**Staleness flagging:** `lexi validate` checks referenced file hashes and flags outdated posts. This runs during Phase 7 validation.

---

## Changes to Existing Code

### `artifacts/design_file.py`

Rename `guardrail_refs: list[str]` → `stack_refs: list[str]`.

### `artifacts/design_file_serializer.py`

Rename `## Guardrails` section → `## Stack`. Update serialization to use new field name.

### `artifacts/design_file_parser.py`

Update parser to recognize `## Stack` section (and `## Guardrails` for backward compatibility during transition).

### `wiki/resolver.py`

Extend resolution order: add `ST-NNN` pattern detection before concept lookup. Route to `.lexibrary/stack/ST-NNN-*.md` using glob matching.

### `cli.py`

- Replace `guardrail_app` and `guardrails` command with `stack_app` and `stack` sub-commands
- Implement `stack search`, `stack post`, `stack answer`, `stack vote`, `stack accept`, `stack view`, `stack list`
- Update `lexi search` stub to become unified cross-artifact search

### `init/scaffolder.py`

Replace `guardrails/` directory creation with `stack/` in the skeleton.

---

## Implementation Tasks

### Task Group 1: StackPost Model & Parser/Serializer

1. Create `stack/__init__.py` with public API re-exports
2. Create `stack/models.py` with `StackPost`, `StackAnswer`, `StackPostFrontmatter`, `StackPostRefs`
3. Create `stack/parser.py` — parse stack posts from disk (frontmatter + body extraction, answer parsing)
4. Create `stack/serializer.py` — serialize StackPost to markdown
5. Create `stack/template.py` — post template for `lexi stack post`
6. Write unit tests for model validation (mandatory fields, status enum, vote constraints)
7. Write unit tests for parser (valid posts, posts with no answers, posts with multiple answers and comments)
8. Write unit tests for serializer round-trip

### Task Group 2: Stack Index

1. Create `stack/index.py` — `StackIndex` class with `build()`, `search()`, `by_tag()`, `by_scope()`, `by_concept()`, `by_status()`
2. Implement search: full-text across titles, problem descriptions, answer bodies, tags
3. Write unit tests for index building and all search/filter methods

### Task Group 3: Mutations

1. Create `stack/mutations.py` — `add_answer()`, `record_vote()`, `accept_answer()`, `mark_duplicate()`, `mark_outdated()`
2. Implement vote logic: update frontmatter vote count, append comment with `[upvote]`/`[downvote]` context
3. Implement accept: set answer `Accepted: true`, update post status to `resolved`
4. Write unit tests for all mutations
5. Write tests verifying append-only body invariant (answers/comments never removed)

### Task Group 4: CLI Commands

1. Remove `guardrail_app` and `guardrails` command from `cli.py`
2. Add `stack_app` Typer sub-group
3. Implement `lexi stack post --title "..." [--tag ...] [--bead ...] [--file ...] [--concept ...]`
4. Implement `lexi stack search <query> [--tag] [--scope] [--status] [--concept]`
5. Implement `lexi stack answer <post-id> --body "..."`
6. Implement `lexi stack vote <post-id> [--answer <n>] up|down [--comment "..."]`
7. Implement `lexi stack accept <post-id> --answer <n>`
8. Implement `lexi stack view <post-id>`
9. Implement `lexi stack list [--status] [--tag]`
10. Write CLI tests with `typer.testing.CliRunner`

### Task Group 5: Design File Integration

1. Rename `guardrail_refs` → `stack_refs` in `DesignFile` model
2. Update `design_file_serializer.py`: `## Guardrails` → `## Stack`
3. Update `design_file_parser.py`: recognize both `## Stack` and `## Guardrails` (backward compat)
4. Update any BAML prompts that reference guardrails
5. Write tests for updated serializer/parser

### Task Group 6: Wikilink Resolver Update

1. Update `wiki/resolver.py` to recognize `ST-NNN` pattern (replacing `GR-NNN`)
2. Route `[[ST-001]]` to `.lexibrary/stack/ST-001-*.md` via glob
3. Update resolver tests

### Task Group 7: Unified Search (Phase 7 prep)

1. Update `lexi search` command to query across concepts (via `ConceptIndex`), design files (via frontmatter scan), and Stack posts (via `StackIndex`)
2. Group and format results by artifact type
3. Support `--tag`, `--scope`, and free-text query across all types
4. Write integration tests for cross-artifact search

### Task Group 8: Init & Scaffolding Update

1. Update `init/scaffolder.py`: `guardrails/` → `stack/`
2. Update config schema if any guardrail-specific config exists
3. Update blueprint/design files for renamed modules

---

## Acceptance Criteria

1. `lexi stack post --title "..." --tag ...` creates a valid post file with auto-assigned ID
2. `lexi stack answer ST-001 --body "..."` appends a new answer block to an existing post
3. `lexi stack vote ST-001 up` increments the post vote count
4. `lexi stack vote ST-001 --answer 1 down --comment "reason"` decrements A1 votes and appends comment with `[downvote]` context
5. `lexi stack vote <id> down` without `--comment` produces an error
6. `lexi stack accept ST-001 --answer 1` marks A1 accepted and post status → resolved
7. `lexi stack search "timezone"` returns matching posts ranked by relevance
8. `lexi stack search --tag datetime` filters by tag
9. `lexi stack search --scope src/models/` filters by referenced file path
10. `lexi search --tag auth` returns results from concepts, design files, AND Stack posts
11. Design files use `## Stack` section with `[[ST-NNN]]` references
12. Wikilink resolver correctly handles `[[ST-001]]` → `.lexibrary/stack/ST-001-*.md`
13. All new code has `from __future__ import annotations`
14. All output uses `rich.console.Console` — no bare `print()`
15. Test coverage for all new modules

---

## What to Watch Out For

- **ID assignment must be atomic** — scan existing `ST-NNN` files to find the next available ID. Handle concurrent creation gracefully (unlikely with single-agent sessions, but design for it).
- **Append-only body means parse-modify-serialize** — when adding an answer, parse the full post, append to the answers list, and re-serialize. Don't do string concatenation on the raw file — it's fragile and risks corrupting existing content.
- **Frontmatter vote counts can drift** — if an agent edits the file directly and changes a vote count without recording a comment, the count and the comment trail diverge. Accept this as a soft constraint — git history is the audit trail.
- **The `## Guardrails` → `## Stack` rename in design files** — existing design files generated by Phase 4 have `## Guardrails`. The parser must handle both section names during the transition. No bulk migration needed — files are updated naturally as `lexi update` runs.
- **Unified search performance** — scanning all three artifact types for every query is O(concepts + design_files + stack_posts). For MVP this is fine. Phase 10 SQLite index eliminates this if it becomes slow.
- **Post slugs in filenames** — the slug is derived from the title, truncated to ~50 chars, lowercased, hyphenated. Used for human readability in file listings. The `id` field in frontmatter is the canonical identifier, not the filename.
- **Tag namespace collision** — tags are shared across concepts, design files, and Stack posts. This is intentional (enables unified search) but means tag conventions should be documented. A tag like `auth` should mean the same thing whether it's on a concept or a Stack post.

---

## Features Deferred

- **Hot/trending ranking** — rank posts by recent vote activity. Nice-to-have, not MVP.
- **Auto-search on error** — hook that automatically searches The Stack when an agent hits a test failure. Requires daemon integration (Phase 9).
- **Post templates by category** — different templates for bug reports, patterns, decisions. MVP uses a single template.
- **Merge posts** — combine duplicate posts. For now, mark as duplicate with pointer.
- **Post verification workflow** — periodic prompt for agents to verify flagged posts. For now, `lexi validate` flags them and agents handle ad hoc.

---

## Not In Scope

- **Graph traversal** — "What posts are 2 hops from this concept?" is a Phase 10 concern.
- **Reputation system** — all agent sessions are treated equally. No karma or badges.
- **Post editing** — body is append-only. Corrections come as new answers or comments, not edits.
- **Notification system** — no mechanism to alert agents about new answers to their posts. Agents discover updates via search.
- **LLM-generated posts** — posts are agent/human authored. No automated post creation.
