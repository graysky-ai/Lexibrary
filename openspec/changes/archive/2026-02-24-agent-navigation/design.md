## Context

Coding agents interact with Lexibrary exclusively through the `lexi` CLI. Currently, an agent entering a project must rely on `lexi --help` (terse flag descriptions) or external docs to understand available workflows. The `lexi concepts` command supports only a positional `topic` search with no filtering — all concepts (including deprecated ones) are returned in a flat table, wasting agent context.

The `ConceptIndex` class already implements `by_tag(tag)` and stores `status` in frontmatter, but these capabilities have no CLI surface. This change wires existing backend support into the CLI and adds a new `lexi help` command for agent self-orientation.

## Goals / Non-Goals

**Goals:**
- Give agents a single command (`lexi help`) to understand how to use the library
- Let agents filter concepts by tag and status to reduce noise
- Establish a sensible default (hide deprecated) while preserving full access via `--all`

**Non-Goals:**
- Interactive TUI / browse mode (separate backlog item `lexi browse`)
- Help for operators (`lexictl help` is a separate backlog item)
- Changes to `ConceptIndex` internals — the backend already supports everything needed
- Dynamic help content that queries project state (e.g., "you have 12 concepts") — static guidance only for v1

## Decisions

### D-1: `lexi help` output format — Rich panels with sections

The help command will output structured Rich panels covering: available commands grouped by purpose, common workflows (e.g., "find a design file", "explore concepts"), and tips for navigating the library. This is static content rendered via Rich, not a dynamic query.

**Alternatives considered:**
- Plain markdown printed to stdout — less readable in terminals, no colour
- Dynamic content querying project state — over-engineered for v1; agents need workflow patterns, not dashboards

### D-2: `lexi help` implemented as a Typer command, not a callback override

Register `help` as a regular `@lexi_app.command()`. This avoids interfering with Typer's built-in `--help` flag behaviour and keeps the implementation simple.

**Alternatives considered:**
- Override Typer's help callback — fragile, conflicts with `--help` flag
- Separate `lexi-help` binary — unnecessary complexity

### D-3: Default `lexi concepts` hides deprecated; `--all` includes them

Currently, bare `lexi concepts` shows everything including deprecated concepts. Change the default to show only `active` and `draft` concepts. The `--all` flag overrides this to include deprecated.

This reduces noise for agents — deprecated concepts are rarely useful and clutter the listing. The `--status deprecated` filter remains available for explicit lookups.

**Alternatives considered:**
- Keep current "show everything" default — agents waste context on deprecated noise
- Hide both draft and deprecated by default — too aggressive; draft concepts are often work-in-progress that agents should see

### D-4: Filter combination semantics — AND logic

When `--tag`, `--status`, and positional `topic` are combined, they apply as AND filters (narrowing). For example, `lexi concepts auth --tag security --status active` returns concepts matching "auth" AND tagged "security" AND status "active".

**Alternatives considered:**
- OR logic — would broaden results, defeating the purpose of filtering
- Separate filter-then-search pipeline — same result with more complexity

### D-5: `by_status()` filtering done at the CLI layer, not in ConceptIndex

Status filtering is simple enough (`concept.frontmatter.status == value`) that it doesn't warrant a new `ConceptIndex` method. The CLI command will filter the result list inline. This keeps the index class focused and avoids adding a method for a trivial predicate.

**Alternatives considered:**
- Add `ConceptIndex.by_status()` method — overkill for a one-line filter; the index already provides `by_tag()` because tag matching involves case-insensitive comparison across a list

## Risks / Trade-offs

- **Minor breaking change**: `lexi concepts` will no longer show deprecated concepts by default → Mitigated by `--all` flag. Deprecated concepts are rare in practice and agents seldom need them.
- **Static help content goes stale**: If commands are added/removed, `lexi help` text must be manually updated → Acceptable for v1. Help text lives in one function, easy to grep for. A future enhancement could auto-generate from registered commands.
