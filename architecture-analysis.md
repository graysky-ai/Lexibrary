# Analysis: matklad's ARCHITECTURE.md and Lexibrary

## The Proposal

matklad (Aleksey Kladov, rust-analyzer author) argues that projects between 10k-200k LOC
should ship an `ARCHITECTURE.md` alongside README and CONTRIBUTING. His core observation:
**writing a patch takes ~2x longer when you're unfamiliar with a codebase, but figuring out
*where* the patch belongs takes ~10x longer.** The document's purpose is to transfer the
mental map that core developers carry in their heads.

## What ARCHITECTURE.md Contains

1. **High-level overview** -- bird's-eye view of the problem the project solves
2. **Codemap** -- coarse-grained modules and their relationships ("a map of a country, not
   an atlas of maps of its states")
3. **Architectural invariants** -- constraints expressed through *absence* (e.g., "the model
   layer must never depend on views")
4. **Layer/system boundaries** -- where one subsystem ends and another begins
5. **Cross-cutting concerns** -- patterns that span multiple modules

## Maintenance Philosophy

The document's most interesting claim is about maintenance cost:

- **Name things, don't link them.** Mention important files/modules/types by name and tell
  the reader to use symbol search. Links rot; names are stable and require no upkeep.
- **Keep it short.** Recurring contributors will re-read it. Brevity also reduces the
  surface area for staleness.
- **Don't synchronize with code.** Revisit it "a couple of times a year." Only specify
  things unlikely to change frequently.
- **Use it as a structure smell test.** If it's hard to describe where something lives, the
  file tree may need reorganizing.

## Comparison with Lexibrary's Current Approach

Lexibrary already has a richer version of several of these ideas:

| matklad concept | Lexibrary equivalent | Difference |
|---|---|---|
| Codemap | `blueprints/START_HERE.md` Project Topology + Package Map | Lexibrary's is more detailed -- a full annotated tree rather than a paragraph-level overview |
| Architectural invariants | `CLAUDE.md` Key Constraints + Error Handling Conventions | Lexibrary's are prescriptive rules for agents, not just descriptive constraints |
| Navigation by intent | `START_HERE.md` "Navigation by Intent" table | Almost identical to what matklad envisions -- "I want to do X, read Y first" |
| Per-file documentation | `blueprints/src/` design files (one per source file) | matklad would consider this overkill for ARCHITECTURE.md -- he explicitly says it should be a country map, not an atlas |
| Cross-cutting concerns | Scattered across CLAUDE.md, conventions, concepts | Less centralized than matklad proposes |

### What Lexibrary Has That matklad Doesn't Propose

- **Per-file design files** with structured frontmatter (blueprints/)
- **Agent-specific rules** (CLAUDE.md, init/rules/) -- matklad targets human readers
- **Machine-queryable knowledge** -- `lexi lookup`, `lexi search`, linkgraph
- **Validation** -- `lexi validate` catches drift between docs and code
- **Stack posts** -- a living Q&A layer for debugging knowledge

### What matklad Proposes That Lexibrary Lacks

- **A single, short, human-readable architectural overview.** `START_HERE.md` is close but
  it's 240 lines and oriented toward agents navigating file-by-file. It doesn't tell a human
  "here's how the system works as a whole" in 2-3 paragraphs.
- **Explicit system boundaries.** Where does the crawl pipeline end and the archivist begin?
  Where's the boundary between indexer and linkgraph? These are implicit in the package map
  but never stated as boundaries.
- **Architectural invariants as negative space.** CLAUDE.md states positive rules ("use
  `from __future__ import annotations`") but doesn't capture the negative invariants
  ("the validator must never import from archivist", "CLI modules must never call LLM
  services directly"). These absence-constraints are the ones that are hardest to discover
  from code alone.

## Should Lexibrary Incorporate This?

**Yes, but not by adding another document.** Lexibrary already has the infrastructure to do
this better than a static markdown file. The question is how.

### Option 1: Add a literal ARCHITECTURE.md (simplest)

Write a ~100-line `ARCHITECTURE.md` in the repo root. Keep it human-readable, narrative,
and short. Revisit it quarterly.

**Pros:** Zero tooling needed. Familiar to OSS contributors. Works for humans and agents
alike.

**Cons:** Yet another document to maintain. Doesn't leverage Lexibrary's existing
machinery. Will drift from `START_HERE.md`.

### Option 2: Generate it from existing artifacts (dogfooding)

Lexibrary already has the data to produce an ARCHITECTURE.md-style document:

- The `.aindex` files know the module tree
- Design file frontmatter has the one-line `description` for each file
- The linkgraph knows dependency relationships
- Conventions capture invariants

A `lexictl generate architecture` command could assemble a codemap + invariants + boundaries
document procedurally, similar to how `archivist/topology.py` already generates
`TOPOLOGY.md`.

**Pros:** Self-maintaining. Dogfoods Lexibrary. Demonstrates value to potential users
("look what Lexibrary produces for your project").

**Cons:** Generated prose is usually worse than hand-written prose. The high-level narrative
("here's the *story* of how the system works") is hard to generate -- it requires editorial
judgment about what matters.

### Option 3: Hybrid -- hand-written overview + generated codemap (recommended)

Split the concerns:

1. **Hand-written section** (~30 lines): Problem statement, key insight, data flow through
   the system. This is the "country map" that matklad emphasizes. Reviewed quarterly.
2. **Generated section**: Package map, dependency boundaries, invariants pulled from
   conventions. Regenerated on `lexictl update`.
3. **Negative invariants**: Add a `boundary` or `invariant` artifact type (or a section in
   conventions) that captures "module X must never depend on module Y." The validator can
   then enforce these.

This approach:
- Gives humans the narrative overview they need
- Automates the parts that go stale fastest (codemap, boundaries)
- Creates a new artifact type that Lexibrary can offer to *other* projects
- Uses matklad's insight that negative constraints are the hardest to discover

### How It Would Be Maintained

| Component | Maintenance mechanism |
|---|---|
| Narrative overview | Human review, ~2x/year, same as matklad proposes |
| Codemap | Regenerated from `.aindex` + design frontmatter |
| Dependency boundaries | Declared in conventions or a new `boundary` artifact; enforced by validator |
| Negative invariants | Same as boundaries -- declared, then checked by import analysis in `ast_parser` |

### How It Would Be Created

For Lexibrary itself (dogfooding):
1. Write the 30-line narrative overview by hand
2. Add a `generate-architecture` command to the archivist pipeline
3. Add `boundary` declarations to conventions (e.g., "cli must not import llm")
4. Add a validator check that verifies boundary constraints via `ast_parser` imports

For other projects using Lexibrary:
1. `lexictl init` scaffolds an `ARCHITECTURE.md` stub with the hand-written section empty
2. `lexictl update` regenerates the codemap section
3. Users add boundary constraints as they discover them
4. `lexi validate` warns when boundaries are violated

## Key Takeaway

matklad's insight is about **the economics of contributor onboarding** -- the 10x cost of
finding *where* to work vs. *how* to work. Lexibrary already solves this for agents via
`lexi lookup` and the design file system. What's missing is the human-readable narrative
layer and the explicit declaration of negative architectural constraints. Both are worth
adding, and both can become features Lexibrary offers to other projects.
