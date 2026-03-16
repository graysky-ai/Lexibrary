# Playbooks — Design Idea

A proposal for a new Lexibrary artifact type that captures triggered, multi-step
procedures — the thing conventions are not quite designed to be.

---

## The Problem

A convention is a standing rule: _always_, _never_, _every time_. It's declarative.
An agent reads it as a constraint that applies to ongoing work.

A version bump procedure is something different: it's an imperative checklist that
runs when a specific event occurs. It has ordered steps, it touches multiple files
across the project, some steps are for humans and some are for agents, and it's
done when you've ticked everything off.

If you store a version bump procedure as a convention, several things break:

- The `rule` field extracts the first paragraph only — the checklist body is
  invisible to anything consuming conventions programmatically.
- Agents reading conventions treat them as always-on constraints. An agent asked
  "what are the coding conventions?" would surface it. An agent about to cut a
  release would not know to look for it.
- There's no trigger — conventions don't say "run this when X happens."
- There's no sequencing — a bulleted list in a convention body carries no
  guarantees about order or completeness.

The version bump use case exposes a missing artifact shape: **a playbook**.

---

## What a Playbook Is

A playbook is a named, triggered, ordered procedure that an agent or human follows
to complete a specific operation. It answers the question: _when [trigger], what
exactly do I do?_

| Property       | Convention          | Playbook                         |
|----------------|---------------------|----------------------------------|
| When active    | Always              | When triggered                   |
| Cardinality    | One rule per file   | Multiple ordered steps per file  |
| Voice          | Declarative         | Imperative                       |
| Lifecycle      | draft → active      | draft → active → deprecated      |
| Agent behavior | Follow this rule    | Execute these steps               |
| State          | Stateless           | Can be tracked per-execution     |

---

## Proposed Artifact Model

A playbook lives in `.lexibrary/playbooks/<slug>.md` and uses YAML frontmatter:

```yaml
---
title: Version Bump Procedure
trigger: version-bump
trigger_files:
  - pyproject.toml
  - package.json
  - Cargo.toml
tags: [release, versioning]
status: active          # draft | active | deprecated
source: user            # user | agent | config
actor: any              # human | agent | ci | any
estimated_minutes: 15
last_verified: "2026-01-15"
deprecated_at: null
superseded_by: null
---
```

### Field Notes

**`trigger`** — A semantic slug that agents and tooling use to match playbooks to
situations. Acts as the canonical name for the event (e.g., `version-bump`,
`db-migration`, `security-patch`, `onboarding`). Slugs should be stable; rename
only with `superseded_by`.

**`trigger_files`** — Optional list of file glob patterns. When an agent is about
to edit a file matching these patterns, the tooling can surface the playbook as a
suggestion. This is the mechanical complement to the semantic `trigger`.

**`actor`** — Who executes this playbook. `human` means a human must run it
interactively. `agent` means it's designed for autonomous execution. `ci` means it
belongs in a pipeline. `any` means it's designed to be followed by either.
Primarily informational in v1, but eventually used to gate autonomous execution.

**`last_verified`** — The date a human or agent confirmed the steps are still
accurate. The key staleness signal. Unset means never verified.

**`superseded_by`** — Slug of the playbook that replaces this one. Set on
deprecation so references to the old playbook can be redirected.

---

## Example Playbook Body

The body is freeform Markdown. Steps should be a numbered list with checkbox syntax
so both humans and agents can track completion. Wikilinks to related conventions,
concepts, and design files create validation targets for `lexi validate`.

```markdown
## Overview

Run this procedure every time the application version is incremented — patch,
minor, or major. Ensures docs, metadata, and changelogs stay coherent.

## Steps

1. [ ] Decide the new version number following [[concept: semver]]
2. [ ] Update the version field in `pyproject.toml` (or `package.json` etc.)
3. [ ] Add a new section to `CHANGELOG.md` with the version header and date
4. [ ] Search for any hardcoded version strings in `docs/` and update them
5. [ ] Run the full test suite — no failures allowed before tagging
6. [ ] Run `lexi validate` — fix any broken wikilinks or stale design files
7. [ ] Commit with message: `chore: bump version to X.Y.Z`
8. [ ] Tag the commit: `git tag vX.Y.Z`
9. [ ] Push branch and open a release PR; request review from a maintainer
10. [ ] After merge, push the tag: `git push origin vX.Y.Z`

## Notes

- Follow [[convention: changelog-format]] when writing the CHANGELOG entry.
- If the version bump crosses a major boundary, also run the
  [[playbook: major-release-checklist]].
- Known gotcha: `docs/conf.py` has a separate version variable — see
  [[stack: sphinx-version-not-updating]].
```

---

## How Agents Find Playbooks

This is the hardest part to get right. A playbook sitting in
`.lexibrary/playbooks/` is useless if agents don't know when to look for it.
Three complementary mechanisms:

### 1. Lookup Integration (highest leverage)

`lexi lookup <file>` is already the prescribed hook agents run before editing.
Extending lookup to surface relevant playbooks creates zero-friction discovery:

```
$ lexi lookup pyproject.toml

  File: pyproject.toml
  Role: Python package metadata and dependency manifest
  ...

  ► Triggered playbooks:
    - version-bump  (trigger_files match: pyproject.toml)
      Run this before changing the version field.
```

Agents following CLAUDE.md already run lookup before editing. No new discipline
required — the information arrives in the right moment.

### 2. Orientation Surface (`lexi orient`)

`lexi orient` could include a playbooks section listing active playbooks and their
triggers. This gives agents and humans a full map at session start:

```
► Active playbooks (3):
  version-bump        pyproject.toml, package.json, Cargo.toml
  db-migration        migrations/
  onboarding          (manual trigger only)
```

This is particularly valuable for onboarding playbooks that have no specific file
trigger — they'd never surface via lookup but are critical for new contributors.

### 3. Explicit Search

`lexi playbook list` and `lexi search` should find playbooks by title, tags, or
trigger. An agent that recognizes it's about to do a release can proactively query:

```
$ lexi playbook list --trigger version-bump
```

This is the fallback when the automatic surface mechanisms miss the moment.

---

## How Playbooks Are Created

### Manual (`lexi playbook new`)

The primary creation path, analogous to `lexi convention new`:

```
$ lexi playbook new "Version Bump Procedure" --trigger version-bump
  Created: .lexibrary/playbooks/version-bump-procedure.md
```

Produces a scaffold with frontmatter and a step template. The author fills in the
steps and sets status to `active` when ready.

### Agent-Captured (retrospective)

If an agent successfully completes a complex multi-step procedure ad hoc, it could
offer to capture it as a playbook:

```
$ lexi playbook capture --from-iwh src/ --title "Version Bump Procedure"
```

IWH signals written during an operation contain a record of what was done. A
capture command could draft a playbook from that history for human review. This is
speculative for v1 but worth keeping in view.

### Config-Seeded

Like `convention_declarations`, a `playbook_declarations` key in `config.yaml`
could seed simple playbooks from config — useful for shared team conventions that
belong in source control rather than the library. Probably not needed in v1.

---

## Keeping Playbooks Up to Date

Playbooks decay faster than conventions because they reference specific files and
commands that change. Three staleness signals:

### `last_verified` + time decay

If `last_verified` is older than a configurable threshold (e.g., 90 days or 100
commits), `lexi validate` flags the playbook as potentially stale. The agent or
human runs through the steps, confirms accuracy, and updates `last_verified`.

### Wikilink validation

Every `[[wikilink]]` in a playbook body is a validation target. If the linked
concept is deprecated, the linked design file is deleted, or the linked stack post
is marked stale, `lexi validate` reports it as a broken reference. This creates a
live dependency graph between playbooks and the rest of the library.

### Referenced file changes

If any file listed in `trigger_files` has been significantly changed (new interface,
renamed, deleted) since `last_verified`, the playbook should be flagged. This
requires correlating git history with the `last_verified` date — plausible but
non-trivial.

### Stack post conflicts

If a stack post is filed that contradicts a playbook step (e.g., "step 4 doesn't
work anymore because X"), `lexi validate` could surface that conflict. This requires
some semantic linking between stack posts and playbooks, probably via tags.

---

## Deprecation Lifecycle

Same shape as conventions:

```
draft → active → deprecated
```

**Triggering deprecation:**

```
$ lexi playbook deprecate version-bump --reason "replaced by CI pipeline"
  --superseded-by automated-release
```

This sets `status: deprecated`, `deprecated_at`, and `superseded_by` in
frontmatter. The deprecated playbook is retained (not deleted) for a TTL window —
same logic as convention deprecation — so in-flight references don't immediately
break.

**Conditions that should prompt deprecation:**

- The trigger event no longer exists (e.g., a manual release process was replaced
  by CI)
- The playbook has been superseded by a newer version with different steps
- The underlying system the playbook governs has been removed
- `last_verified` has never been set and the playbook is very old (draft rot)

**TTL:** After deprecation, a configurable TTL in commits (e.g., 50 commits) before
`lexi validate` suggests removal. Aligns with the existing deprecation TTL logic
for conventions.

---

## Integration with Existing Tooling

| Tool | Current behavior | With playbooks |
|------|-----------------|----------------|
| `lexi orient` | Lists concepts, conventions, IWH | + Active playbooks and triggers |
| `lexi lookup <file>` | File role, deps, conventions | + Triggered playbooks |
| `lexi validate` | Broken wikilinks, stale designs | + Stale playbooks, broken step refs |
| `lexi search <query>` | Concepts, conventions, stack | + Playbook titles, bodies, triggers |
| `lexi convention new` | Creates convention scaffold | Sibling: `lexi playbook new` |

The playbook directory also needs to be excluded from the crawler's source indexing
(alongside `.lexibrary/conventions/`, `.lexibrary/concepts/` etc.) so playbooks
don't become design-file candidates.

---

## `.lexibrary/` Directory Shape

```
.lexibrary/
  concepts/           # what things are
  conventions/        # standing rules
  playbooks/          # triggered procedures   ← new
  stack/              # solved problems
  designs/            # source-file mirrors
  TOPOLOGY.md
  config.yaml
  index.db
```

The four peer directories form a complete knowledge quadrant:
- `concepts` answers _what is X?_
- `conventions` answers _what are the rules?_
- `playbooks` answers _how do I do X?_
- `stack` answers _what went wrong / right before?_

---

## Implementation Scope (rough)

For a v1 that delivers the core value:

1. **Artifact model** — `PlaybookFileFrontmatter` and `PlaybookFile` Pydantic models
   in `src/lexibrary/artifacts/playbook.py`
2. **Parser + serializer** — Reading/writing `.md` files, analogous to
   `conventions/parser.py` and `conventions/serializer.py`
3. **CLI commands** — `lexi playbook new | list | show | verify | deprecate | comment`
4. **Lookup integration** — Surface triggered playbooks in `lexi lookup` output
5. **Orient integration** — List active playbooks in `lexi orient`
6. **Validate integration** — Check wikilinks in bodies, `last_verified` staleness

Explicitly deferred to later:
- `actor`-gated autonomous execution
- Config-seeded `playbook_declarations`
- Agent-capture from IWH history
- Referenced-file change detection via git

---

## Open Questions

### Q1 — Trigger design: semantic slug vs. file patterns vs. tags

**Decision needed:** Should triggers be a single semantic slug (`trigger: version-bump`),
a list of file glob patterns (`trigger_files: [pyproject.toml]`), both, or a free-form
tags approach?

**Recommendation:** Both, as proposed. The semantic slug (`trigger`) gives stable
naming for cross-references and search. The `trigger_files` list gives mechanical
discovery without requiring agents to know the semantic name in advance. They
complement rather than duplicate each other.

---

### Q2 — Step format: checkboxes vs. custom syntax vs. unstructured Markdown

**Decision needed:** Should steps have enforced syntax (numbered list + `[ ]`
checkboxes), or is the body completely freeform?

**Recommendation:** Encourage numbered list + checkboxes by convention and scaffold,
but don't validate the body structure in v1. Enforcing syntax creates friction
during authoring and the parser would need to handle many edge cases. A style
convention is enough to start.

---

### Q3 — `actor` field: is the human/agent/ci distinction worth the complexity?

**Decision needed:** Is `actor` metadata useful enough to include in the model,
or is it overengineering for v1?

**Recommendation:** Include it as an informational field with no enforcement in v1.
It costs nothing to store, is genuinely useful to human readers, and future
autonomous execution gating will need it. Defaulting to `any` means the field
is optional in practice.

---

### Q4 — Can playbooks live outside `.lexibrary/`?

**Decision needed:** Should playbooks always live in `.lexibrary/playbooks/`, or
could a team place a playbook adjacent to the code it governs
(e.g., `src/db/migrations/playbook.md`)?

**Recommendation:** Keep them in `.lexibrary/playbooks/` for v1. Distributed
playbooks create a discovery problem — the tooling would need to crawl for
them. A single canonical location makes indexing and search simple. If there's
a real demand for co-location later, a `scan_paths` config key could extend it.

---

### Q5 — Execution tracking: should there be a log of playbook runs?

**Decision needed:** Should `lexi playbook run <name>` exist? Should completed
runs leave a record (stack post, log entry, IWH signal)?

**Recommendation:** No `run` command in v1. The playbook is a reference document,
not an orchestrator. Agents following the steps can optionally file a stack post
if they encounter something noteworthy. Requiring a formal run record adds
ceremony without clear payoff at this stage. Revisit when there's evidence that
execution history is needed for staleness tracking.

---

### Q6 — `last_verified` staleness threshold: time-based or commit-based?

**Decision needed:** Should the staleness threshold for `last_verified` use calendar
time (e.g., 90 days) or commit count (e.g., 100 commits), or both?

**Recommendation:** Commit-based as the primary signal (consistent with how stack
posts and convention deprecation work), with calendar time as a fallback for repos
with very slow commit rates. A sensible default: flag if >100 commits since
`last_verified`, or >180 days if commit count is unavailable.

---

### Q7 — Should `lexi orient` show all active playbooks or only contextually relevant ones?

**Decision needed:** `lexi orient` is run at session start. If a project has 20
playbooks, listing all of them adds noise. Should it show all, or only ones whose
`trigger_files` overlap with recently changed files?

**Recommendation:** Show all in `--verbose` mode; in normal mode show only playbooks
with trigger_files matching files changed in the last N commits (e.g., 10). This
keeps orientation output concise while surfacing the most relevant playbooks.
Playbooks with no `trigger_files` (manual-trigger only) should always be listed
since there's no other surface mechanism for them.

---

### Q8 — Index integration: should playbooks be in `index.db`?

**Decision needed:** Should playbooks be indexed in the SQLite index alongside
concepts, conventions, and stack posts, or kept as filesystem-only artifacts?

**Recommendation:** Yes, index them. The search and lookup integrations depend on
fast querying, and the index is already the right layer for that. The playbook
parser needs to feed into the indexer pipeline the same way conventions do.

---

### Q9 — Playbook-to-playbook references: nested playbooks?

**Decision needed:** A major release might call the version-bump playbook and
several others. Should playbooks support `[[playbook: name]]` wikilinks that
create validated cross-references?

**Recommendation:** Yes. Wikilink syntax is already the convention for
cross-artifact references across the library. Adding `[[playbook: slug]]` as
a recognized link type is a small parser extension with high value — it makes
the dependency graph explicit and gives `lexi validate` something to check.

---

### Q10 — Migration path: what happens to procedures currently stored as conventions?

**Decision needed:** Some teams may already have procedure-style content in
conventions. Should there be a migration command?

**Recommendation:** Not in v1. Document in the playbook guide that procedure-style
conventions should be moved to playbooks, and provide `lexi playbook new` as the
creation path. A `lexi playbook migrate --from-convention <slug>` command would be
a nice v2 addition once the artifact model is stable.
