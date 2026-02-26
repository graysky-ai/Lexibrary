# Navigation Protocol -- Holistic Review

> **Status**: Split out from
> [`plans/start-here-reamagined.md`](start-here-reamagined.md) "Open Thread:
> Navigation Protocol -- Holistic Review" (lines 308-331). Lower priority than
> conventions and navigation-by-intent, but worth tracking because wording drift
> across 5+ delivery points is a real maintenance concern.

---

## The Protocol

"Navigation protocol" refers to the set of behavioural rules that agents must
follow when working in a Lexibrary-indexed project. These rules govern the
full edit lifecycle: how an agent orients itself at session start, what it does
before touching a file, and what it does after editing.

The protocol consists of these rules:

1. **Orient at session start** -- Read `.lexibrary/START_HERE.md` to understand
   the project structure, conventions, and navigation table.
2. **Check IWH signals** -- Run `lexi iwh list` to check for I Was Here signals
   left by a previous session; consume them with `lexi iwh read <directory>`.
3. **Lookup before editing** -- Run `lexi lookup <file>` before editing any
   source file to understand its role, dependencies, and conventions.
4. **Update design file after editing** -- Update the corresponding design file
   in `.lexibrary/` to reflect changes; set `updated_by: agent` in frontmatter.
5. **Validate after editing** -- Run `lexi validate` to check for broken
   wikilinks, stale design files, or other library health issues.
6. **Check conventions before architectural decisions** -- Run
   `lexi concepts <topic>` before making architectural decisions.
7. **Use Stack for debugging** -- Run `lexi stack search` before debugging;
   run `lexi stack post` after solving non-trivial bugs.
8. **Leave IWH on incomplete work** -- Run `lexi iwh write` when leaving work
   incomplete or blocked.
9. **Never run `lexictl`** -- These are maintenance-only commands reserved for
   project administrators.

For the purposes of this review, the "core navigation protocol" is rules 1-5,
which form the session-start and per-file-edit workflow. Rules 6-9 are
supplementary behaviours that appear less consistently across delivery points.

---

## Current Delivery Points

### 1. `base.py` `get_core_rules()` (lines 109-160)

**File**: `src/lexibrary/init/rules/base.py`
**Covers**: All 9 rules
**Maintenance**: Hand-maintained Python string template. Changed by editing source code and releasing.
**Consumers**: All agent environments -- this is the canonical source. `claude.py`, `cursor.py`, and `codex.py` all call `get_core_rules()` and inject the result into CLAUDE.md, `.cursor/rules/lexibrary.mdc`, and AGENTS.md respectively.
**Mechanism**: Generated into target files at `lexi init` / `lexictl setup` time.

**Exact wording (core rules 1-5):**

> **Session Start**
> 1. Read `.lexibrary/START_HERE.md` to understand the project structure and conventions.
> 2. Run `lexi iwh list` to check for IWH (I Was Here) signals left by a previous session.
>
> **Before Editing Files**
> - Run `lexi lookup <file>` before editing any source file to understand its role, dependencies, and conventions.
> - Read the corresponding design file in `.lexibrary/` if one exists.
>
> **After Editing Files**
> - Update the corresponding design file to reflect your changes. Set `updated_by: agent` in the frontmatter.
> - Run `lexi validate` to check for broken wikilinks, stale design files, or other library health issues introduced by your changes.

### 2. `claude.py` hook scripts (lines 97-175)

**File**: `src/lexibrary/init/rules/claude.py`
**Covers**: Rules 3 (lookup before editing) and 4 (update design file after editing)
**Maintenance**: Hand-maintained Python string template. Changed by editing source code and releasing.
**Consumers**: Claude Code only (hooks are a Claude Code feature).
**Mechanism**: Mechanical enforcement via PreToolUse and PostToolUse hooks. The pre-edit hook runs `lexi lookup` automatically before any Edit/Write tool use. The post-edit hook emits a `systemMessage` reminder.

**Exact wording (pre-edit hook):**
The pre-edit hook (`lexi-pre-edit.sh`, lines 97-133) does not contain instructional text. It silently runs `lexi lookup "$FILE_PATH"` and pipes the output as `additionalContext`. There is no human-readable rule statement -- the enforcement is purely mechanical.

**Exact wording (post-edit hook):**
The post-edit hook (`lexi-post-edit.sh`, lines 135-175) emits this system message (line 167-169):

> Remember to update the corresponding design file after editing source files. Set updated_by: agent in the frontmatter.

Note: This wording is close but not identical to the `base.py` rule. `base.py` says "Update the corresponding design file to reflect your changes." The hook says "Remember to update the corresponding design file after editing source files." The hook omits "to reflect your changes" and adds "Remember to" framing.

### 3. `cursor.py` `lexibrary-editing.mdc` (lines 102-140)

**File**: `src/lexibrary/init/rules/cursor.py`
**Covers**: Rules 3 (lookup before editing), 4 (update design file), and 5 (validate)
**Maintenance**: Hand-maintained Python string template. Changed by editing source code and releasing.
**Consumers**: Cursor IDE only (scoped `.mdc` rules activated by glob pattern).
**Mechanism**: Text instruction via conditional rule (`alwaysApply: false`, triggered by `src/**` glob).

**Exact wording (lines 122-139):**

> **Before Editing**
> - Run `lexi lookup <file>` before editing any source file to understand its role, dependencies, and conventions.
> - Read the corresponding design file in `.lexibrary/` if one exists.
>
> **After Editing**
> - Update the corresponding design file to reflect your changes. Set `updated_by: agent` in the frontmatter.
> - Run `lexi validate` to check for broken wikilinks, stale design files, or other library health issues introduced by your changes.

This is a verbatim copy of the Before/After sections from `base.py` core rules. It is maintained as a separate string in `_build_editing_mdc_content()` rather than calling `get_core_rules()` and extracting the relevant section. This means a change to `base.py` will NOT automatically propagate to the Cursor editing rule -- both must be updated independently.

**Note**: Cursor also gets the full `get_core_rules()` output via `lexibrary.mdc` (the `alwaysApply: true` rule). So Cursor agents receive the Before/After editing rules **twice**: once in the always-on rule and once in the editing-scoped conditional rule. This is intentional (the conditional rule reinforces the instruction when the agent is actually editing source files) but creates a third copy to maintain.

### 4. `codex.py` AGENTS.md (lines 33-83)

**File**: `src/lexibrary/init/rules/codex.py`
**Covers**: All 9 rules (inherits from `get_core_rules()`)
**Maintenance**: Inherits directly from `base.py` via `get_core_rules()` call.
**Consumers**: OpenAI Codex.
**Mechanism**: Text instruction in AGENTS.md, wrapped in `<!-- lexibrary:start -->` / `<!-- lexibrary:end -->` markers for section management.

**Exact wording**: Identical to `base.py` -- `codex.py` calls `get_core_rules()` and embeds the result unchanged (line 77). No drift here.

### 5. `docs/agent/orientation.md` (lines 1-89)

**File**: `docs/agent/orientation.md`
**Covers**: Rules 1 (read START_HERE), 2 (check IWH), 3 (lookup before editing), 4 (update design file)
**Maintenance**: Manually maintained markdown documentation. NOT generated from code.
**Consumers**: Any agent or human reading the docs. Not injected into any agent environment automatically.
**Mechanism**: Explanatory documentation with narrative context and examples.

**Exact wording for rule 1 (line 6):**

> **Step 1: Read `.lexibrary/START_HERE.md`**
> This is the single most important file for orientation. Read it first.

Compare to `base.py`: "Read `.lexibrary/START_HERE.md` to understand the project structure and conventions."

The doc version is more emphatic ("single most important file") and adds narrative context. It then spends 20 lines explaining what START_HERE contains.

**Exact wording for rules 3-4 (lines 84-89, "After Orientation"):**

> Once oriented, you are ready to work. Before editing any file:
> 1. Run `lexi lookup <file>` to read its design file, conventions, and dependents (see [Lookup Workflow](lookup-workflow.md))
> 2. After editing, update the design file to reflect your changes (see [Update Workflow](update-workflow.md))

Compare to `base.py`:
- `base.py` says "to understand its role, dependencies, and conventions"; orientation.md says "to read its design file, conventions, and dependents". Different nouns: "role" vs "design file", "dependencies" vs "dependents".
- `base.py` says "Set `updated_by: agent` in the frontmatter."; orientation.md omits this detail entirely.
- orientation.md adds cross-references to workflow docs that `base.py` does not mention.

**Missing**: Rule 5 (validate) is absent from orientation.md. Rule 6 (concepts) is absent. Step 3 in orientation.md mentions `lexi concepts` but as a library health check, not as a pre-architectural-decision step.

### 6. `docs/agent/quick-reference.md` (lines 1-157)

**File**: `docs/agent/quick-reference.md`
**Covers**: Rules 1 (read START_HERE), 2 (check IWH), 3 (lookup before editing), 4 (update design file)
**Maintenance**: Manually maintained markdown documentation. NOT generated from code.
**Consumers**: Any agent or human reading the docs.
**Mechanism**: Terse checklist format designed for quick scanning.

**Exact wording for session start (lines 9-11):**

> 1. Read `.lexibrary/START_HERE.md` -- get project topology, package map, navigation table, and key constraints
> 2. Check for `.iwh` files -- `ls .iwh 2>/dev/null` -- read, act on, and delete any signals from previous sessions
> 3. Run `lexi concepts` -- verify the library is accessible and review available project vocabulary

Compare to `base.py`:
- Rule 1 wording is similar but quick-reference adds an inline summary of what START_HERE contains.
- Rule 2 uses `ls .iwh 2>/dev/null` instead of `lexi iwh list`. This is a significant divergence -- it recommends a raw filesystem check instead of the CLI command. (The `lexi iwh list` command did not exist when quick-reference.md was first written, and the doc was never updated.)

**Exact wording for before/after editing (lines 16-25):**

> **Before Editing a File**
> 1. Run `lexi lookup <file>` -- read the design file, conventions, and dependents
> 2. Review conventions -- follow all listed rules from the `.aindex` hierarchy
>
> **After Editing a File**
> 1. Update the design file in `.lexibrary/` -- update description, summary, and interface contract
> 2. Set `updated_by: agent` in the design file frontmatter

Compare to `base.py`:
- Before-edit: quick-reference adds "Review conventions -- follow all listed rules from the `.aindex` hierarchy" which is not in `base.py` at all. This references a conventions system that does not currently produce output (`.aindex` `local_conventions` is hard-coded to `[]`).
- After-edit: quick-reference says "update description, summary, and interface contract" -- more specific than `base.py`'s "reflect your changes", but this specificity may not match all design file structures.
- Rule 5 (validate) is absent from quick-reference.md.

### 7. `docs/agent/README.md` (lines 1-100)

**File**: `docs/agent/README.md`
**Covers**: Rules 1 (read START_HERE), 3 (lookup before editing -- implied)
**Maintenance**: Manually maintained markdown documentation.
**Consumers**: Any agent or human reading the docs.
**Mechanism**: High-level overview document; mentions the protocol in passing.

**Exact wording (lines 38-39):**

> Read this file at the start of every session.

(Referring to START_HERE.md.)

**Exact wording (lines 77-79):**

> 2. **Fewer mistakes.** Running `lexi lookup` before editing shows you the file's conventions, dependents, and design context -- so you know what will break and what patterns to follow.

This is framed as a benefit explanation, not an instruction. It covers rule 3 implicitly but not prescriptively. The design-file-update rule (rule 4) appears only in the "What You Must Not Do" section in negated form (line 91: "Never delete files from `.lexibrary/` directly").

### 8. START_HERE.md (LLM-generated -- being removed)

**File**: `.lexibrary/START_HERE.md` (generated at runtime)
**Covers**: Rules 3-4 (lookup and design file update), variable other rules
**Maintenance**: LLM-regenerated on each `lexictl update`. Wording varies between regenerations.
**Consumers**: All agents that read START_HERE.md at session start.
**Mechanism**: LLM-generated prose; exact wording is non-deterministic.

**Decision**: Being removed per `start-here-reamagined.md`. Not analysed further here.

---

## Delivery Point Matrix

Rows = protocol rules. Columns = delivery points. Cells indicate coverage.

| Rule | base.py (CLAUDE.md / .cursor/rules / AGENTS.md) | claude.py hooks | cursor.py editing.mdc | orientation.md | quick-reference.md | README.md |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| 1. Read START_HERE | Present | -- | -- | Present (narrative) | Present (checklist) | Present (brief) |
| 2. Check IWH | Present | -- | -- | Present (narrative) | Present (DIVERGENT: `ls .iwh` not `lexi iwh list`) | -- |
| 3. Lookup before edit | Present | **Enforced** (auto-runs) | Present (verbatim copy) | Present (different nouns) | Present (terse) | Present (implied) |
| 4. Update design file | Present | **Reminded** (systemMessage) | Present (verbatim copy) | Present (omits `updated_by`) | Present (more specific) | -- |
| 5. Validate after edit | Present | -- | Present (verbatim copy) | -- | -- | -- |
| 6. Concepts before decisions | Present | -- | -- | -- | -- | -- |
| 7. Stack for debugging | Present | -- | -- | -- | -- | -- |
| 8. IWH on incomplete work | Present | -- | -- | -- | Present (DIVERGENT: manual file creation) | -- |
| 9. Never run lexictl | Present | -- | -- | -- | Present | Present |

**Legend**:
- "Present" = stated as a text instruction
- "**Enforced**" = mechanically executed regardless of agent compliance
- "**Reminded**" = system message emitted but not blocking
- "DIVERGENT" = semantically same rule but recommends a different mechanism
- "--" = absent

---

## The Drift Problem

### Concrete drift examples

**Drift 1: IWH check mechanism**

| Delivery point | Wording |
|----------------|---------|
| `base.py` (line 115-116) | "Run `lexi iwh list` to check for IWH (I Was Here) signals left by a previous session." |
| `orientation.md` (lines 43-46) | "Check for IWH signals across the project: `lexi iwh list`" |
| `quick-reference.md` (line 10) | "Check for `.iwh` files -- `ls .iwh 2>/dev/null`" |

Quick-reference recommends a raw filesystem operation instead of the CLI command. An agent following quick-reference would use `ls` and miss signals in subdirectories. This is not a cosmetic difference -- it produces different behaviour.

**Drift 2: Lookup purpose description**

| Delivery point | Wording |
|----------------|---------|
| `base.py` (line 123) | "to understand its role, dependencies, and conventions" |
| `orientation.md` (line 86) | "to read its design file, conventions, and dependents" |
| `quick-reference.md` (line 17) | "read the design file, conventions, and dependents" |
| `README.md` (line 78) | "shows you the file's conventions, dependents, and design context" |

Four different formulations. "dependencies" vs "dependents" is a semantic distinction (what a file depends on vs what depends on it). "role" (base.py) vs "design file" (orientation.md) vs "design context" (README.md) describe different aspects of what lookup returns.

**Drift 3: Design file update instruction**

| Delivery point | Wording |
|----------------|---------|
| `base.py` (lines 129-130) | "Update the corresponding design file to reflect your changes. Set `updated_by: agent` in the frontmatter." |
| `claude.py` post-edit hook (lines 167-169) | "Remember to update the corresponding design file after editing source files. Set updated_by: agent in the frontmatter." |
| `orientation.md` (line 88) | "After editing, update the design file to reflect your changes" |
| `quick-reference.md` (lines 24-25) | "Update the design file in `.lexibrary/` -- update description, summary, and interface contract. Set `updated_by: agent` in the design file frontmatter" |

Orientation.md omits the `updated_by: agent` instruction entirely. Quick-reference adds specific fields to update ("description, summary, and interface contract") that no other delivery point mentions. The hook uses "Remember to" framing.

**Drift 4: IWH write mechanism (leaving work incomplete)**

| Delivery point | Wording |
|----------------|---------|
| `base.py` (lines 148-151) | "run: `lexi iwh write <directory> --scope incomplete --body \"description of what remains\"`" |
| `quick-reference.md` (lines 104-117) | Shows manual file creation: "File: src/lexibrary/config/.iwh" with YAML frontmatter, no mention of `lexi iwh write` |

Quick-reference instructs agents to create IWH files manually with `cat`-style examples. `base.py` instructs use of the CLI command. These are fundamentally different mechanisms.

### What changes propagate where?

| Source | Changes propagate to... | ...automatically? |
|--------|------------------------|-------------------|
| `base.py` `_CORE_RULES` | CLAUDE.md, `.cursor/rules/lexibrary.mdc`, AGENTS.md | Yes, on next `lexi init` / `lexictl setup` |
| `base.py` `_CORE_RULES` | `.cursor/rules/lexibrary-editing.mdc` | **No** -- `cursor.py` has its own copy of the Before/After wording |
| `base.py` `_CORE_RULES` | `docs/agent/orientation.md` | **No** -- manually maintained |
| `base.py` `_CORE_RULES` | `docs/agent/quick-reference.md` | **No** -- manually maintained |
| `base.py` `_CORE_RULES` | `docs/agent/README.md` | **No** -- manually maintained |
| `claude.py` hook wording | hook scripts on disk | Yes, on next `lexi init` / `lexictl setup` |

**The propagation gap**: When `base.py` is updated, 3 out of 6 delivery points
(orientation.md, quick-reference.md, README.md) require manual updates that are
easy to forget. Additionally, `cursor.py`'s `_build_editing_mdc_content()` has
its own inline copy of the Before/After rules that must be updated separately
from `base.py`, even though both are in the same codebase.

### Risk assessment

How bad is wording drift in practice?

**Low risk (cosmetic drift)**: Minor wording differences like "role" vs "design
file" vs "design context" are unlikely to cause behavioural problems. LLMs
understand synonyms and paraphrases. An agent that reads "understand its role"
and "read its design file" will likely do the same thing.

**Medium risk (instruction specificity drift)**: Quick-reference telling agents
to "update description, summary, and interface contract" when other sources just
say "reflect your changes" could cause agents to focus narrowly on those three
fields. Orientation.md omitting `updated_by: agent` means an agent relying only
on that doc will skip the frontmatter update.

**High risk (mechanism drift)**: Quick-reference recommending `ls .iwh` instead
of `lexi iwh list` and manual IWH file creation instead of `lexi iwh write` are
genuine behavioural divergences. An agent following quick-reference would use
the wrong commands. This is the most serious drift -- it gives agents incorrect
instructions.

---

## Enforcement Layers

The navigation protocol is delivered through three distinct mechanisms, each
with different enforcement strength:

### 1. Text Instructions (agent reads and chooses to comply)

**Where**: CLAUDE.md, `.cursor/rules/lexibrary.mdc`, `.cursor/rules/lexibrary-editing.mdc`, AGENTS.md

**How it works**: Agent rules files are loaded into the agent's system prompt or
context. The agent reads them and is expected to follow the instructions. There
is no verification that the agent actually complies.

**Strength**: Moderate. Agents generally follow system prompt instructions, but
under pressure (long context, complex task, user urgency) they may skip steps.
The "read START_HERE first" instruction is particularly vulnerable -- agents
frequently jump straight to the user's request.

**Covers**: All 9 rules.

### 2. Mechanical Enforcement (hooks that auto-run regardless of compliance)

**Where**: `.claude/hooks/lexi-pre-edit.sh` (PreToolUse), `.claude/hooks/lexi-post-edit.sh` (PostToolUse)

**How it works**: Claude Code hooks fire automatically when the agent uses Edit
or Write tools. The pre-edit hook runs `lexi lookup` and injects the result as
`additionalContext` -- the agent receives design file context whether it asked
for it or not. The post-edit hook emits a `systemMessage` reminding the agent to
update the design file.

**Strength**: Strong for rule 3 (lookup). The agent cannot edit a file without
receiving lookup context. Moderate for rule 4 (design file update) -- the
reminder is a system message, not a blocking gate; the agent can still ignore
it.

**Covers**: Rules 3 and 4 only. Does not enforce rules 1, 2, 5, 6, 7, 8, or 9.

**Limitation**: Claude Code only. Cursor and Codex have no hook mechanism, so
agents in those environments rely entirely on text instructions.

### 3. Documentation (explains the "why" for agents that want context)

**Where**: `docs/agent/orientation.md`, `docs/agent/quick-reference.md`, `docs/agent/README.md`

**How it works**: These documents explain the protocol with narrative context,
examples, and cross-references. They are not injected into agent environments
automatically -- an agent would need to read them voluntarily, or an operator
would need to configure them as additional context.

**Strength**: Weak for enforcement, strong for understanding. An agent that
reads orientation.md will understand *why* it should run `lexi lookup` (not just
that it should). But most agents never read these docs unless specifically
directed to.

**Covers**: Rules 1-4 with narrative depth. Minimal coverage of rules 5-9.

### Are the three layers complementary or redundant?

**Complementary (belt + suspenders + explanation)**:
- Text instructions tell the agent *what* to do and *when*
- Hooks ensure the most critical steps happen even if the agent forgets
- Docs explain *why*, which helps agents make better judgement calls in edge cases

This layering is sound in principle. The hook for rule 3 (lookup) is the
strongest argument: even if the text instruction is ignored, the agent still
gets design context injected. This is genuine defence in depth.

**Partially redundant**:
- The Cursor editing rule (`lexibrary-editing.mdc`) is a verbatim copy of the
  Before/After sections already present in the always-on rule (`lexibrary.mdc`).
  Cursor agents get the same text twice, from two files that must be maintained
  separately.
- Claude Code agents get rule 3 from text (CLAUDE.md), from the hook
  (pre-edit auto-lookup), AND from the `/lexi-lookup` skill command. Three
  delivery mechanisms for one rule.

**The real question**: Is the redundancy worth the maintenance cost? Currently
the answer is "probably yes" because the rules are stable and rarely change.
If the protocol evolves (e.g., conventions become a real feature and rule 6
gains a hook), the maintenance burden of keeping 6+ delivery points in sync
increases.

---

## Design Options

### Option 1: Status Quo Minus START_HERE

Remove navigation protocol from START_HERE (already decided). Accept remaining
drift across the other 5+ delivery points. Do nothing else.

| Factor | Assessment |
|--------|------------|
| Maintenance burden | Low -- no new work. Drift continues but is not actively harmful. |
| Consistency guarantee | None. Drift accumulates over time. Mechanism drift in quick-reference.md remains unfixed. |
| Implementation effort | Zero. |
| Risk | The mechanism drift in quick-reference.md (`ls .iwh` instead of `lexi iwh list`, manual IWH creation) should be fixed regardless of which option is chosen. |

### Option 2: Single Source of Truth

All delivery points derive their protocol wording from `base.py` `_CORE_RULES`.
Docs are generated, not hand-written.

Implementation:
- `orientation.md` generation: extract and expand core rules into narrative form
  (could be a simple template with `get_core_rules()` sections embedded, plus
  hand-written explanatory paragraphs around them)
- `quick-reference.md` generation: extract core rules into checklist format
- `cursor.py` `_build_editing_mdc_content()`: refactor to extract Before/After
  sections from `get_core_rules()` instead of maintaining an inline copy
- `README.md`: keep as hand-written overview with a pointer to generated docs

| Factor | Assessment |
|--------|------------|
| Maintenance burden | Medium upfront (build generation), low ongoing (change one place). |
| Consistency guarantee | Strong. All delivery points derive from one source. |
| Implementation effort | Medium. Generating narrative docs from terse rules requires templating. The narrative value of orientation.md (examples, context, cross-references) is hard to generate from a rules list. |
| Risk | Generated docs may lose the explanatory quality of hand-written docs. The "why" layer becomes thinner. |

### Option 3: Layered by Purpose

Accept that rules, hooks, and docs serve different purposes and should have
different wording. Enforce **semantic consistency** (same rules, same
mechanisms) without requiring **textual identity** (same words).

Implementation:
- Define the protocol as a numbered list of rules (this document's "The Protocol"
  section) as the semantic specification
- Each delivery point is free to express rules in its own style (terse for
  checklists, narrative for docs, imperative for agent rules)
- Add a manual review step: when `base.py` changes, a checklist reminds the
  developer to review each delivery point for semantic consistency
- Fix existing mechanism drift (quick-reference.md IWH commands)

| Factor | Assessment |
|--------|------------|
| Maintenance burden | Low-medium. No generation infrastructure, but requires discipline on manual review. |
| Consistency guarantee | Moderate. Semantic consistency maintained by process, not automation. |
| Implementation effort | Low. Fix quick-reference.md drift, write the review checklist. |
| Risk | Process-based consistency degrades over time if not enforced. New contributors may not know about the checklist. |

### Option 4: Consolidate

Reduce the number of delivery points. If hooks mechanically enforce a rule,
remove the text instruction for that rule. If docs duplicate agent rules,
remove the docs or convert them to pointers.

Implementation:
- Remove Before/After editing rules from text instructions where hooks exist
  (Claude Code only -- keep them for Cursor and Codex which lack hooks)
- Remove `lexibrary-editing.mdc` entirely (Cursor already gets these rules from
  `lexibrary.mdc`)
- Convert orientation.md and quick-reference.md to pointers: "See your agent
  rules file for the editing protocol" instead of restating the rules
- Keep README.md as a high-level overview (already minimal)

| Factor | Assessment |
|--------|------------|
| Maintenance burden | Low. Fewer delivery points = fewer things to keep in sync. |
| Consistency guarantee | Strong by elimination. |
| Implementation effort | Low-medium. Need to audit what each delivery point adds beyond the others. |
| Risk | Loss of defence in depth. If a hook fails or is not configured, the agent has no text instruction to fall back on. Loss of the "why" layer if docs are reduced to pointers. Cursor loses the contextual reinforcement of the editing-scoped rule. |

---

## Open Questions

1. **If hooks mechanically enforce lookup-before-edit, should the text rule be
   removed to reduce noise?**
   The hook guarantees the agent receives design context. The text rule adds
   cognitive overhead ("I was told to do this AND it happened automatically").
   But removing the text rule means agents in non-Claude-Code environments
   (Cursor, Codex) have less guidance. A possible middle ground: keep the text
   rule but annotate it as "automatically enforced in Claude Code via hooks."

2. **Should `orientation.md` and `quick-reference.md` be auto-generated from
   `base.py` core rules?**
   Generation guarantees consistency but may sacrifice the narrative quality and
   examples that make docs useful. A hybrid approach (generated rule excerpts
   embedded in hand-written narrative) might be best, but adds templating
   complexity.

3. **What is the real cost of drift? Does slightly different wording cause
   actual agent behaviour problems, or is it just aesthetically unsatisfying?**
   Cosmetic drift (synonym variation) is probably harmless. Mechanism drift
   (`ls .iwh` vs `lexi iwh list`) is demonstrably harmful. The answer likely
   depends on the type of drift, not the quantity.

4. **Should there be a validator check for protocol consistency across delivery
   points?**
   A CI check that parses core rules from `base.py` and verifies that key
   phrases (command names, frontmatter field names) appear in all delivery
   points would catch mechanism drift automatically. But it would be fragile
   and could produce false positives on intentional wording variation.

5. **Should `cursor.py` `_build_editing_mdc_content()` extract its wording from
   `get_core_rules()` instead of maintaining an inline copy?**
   This is a straightforward code change that eliminates one source of drift
   within the codebase itself. The inline copy exists because the editing rule
   needs only the Before/After sections, not the full core rules. A helper
   function like `get_editing_rules()` in `base.py` would solve this cleanly.

6. **Does the post-edit hook's "Remember to" framing actually work?**
   The hook emits a `systemMessage`, which is weaker than `additionalContext`
   or a blocking response. If agents frequently ignore the reminder, the hook
   is providing false assurance. Measuring compliance would require logging
   whether agents actually update design files after receiving the reminder.

7. **Should the post-edit hook be upgraded to a blocking gate?**
   Instead of a reminder, the hook could check whether the design file was
   already updated and block the edit if not. This would be stronger enforcement
   but could be annoying for rapid iteration. This is a design question, not a
   drift question, but it is related to the overall enforcement architecture.

---

## Relationship to Other Plans

- **[`plans/start-here-reamagined.md`](start-here-reamagined.md)** -- Parent
  document. The "Open Thread: Navigation Protocol -- Holistic Review" (lines
  308-331) identified this problem and decided to remove navigation protocol
  from START_HERE. This document analyses the remaining delivery points.

- **[`plans/agent-start-plan.md`](agent-start-plan.md)** -- Related mechanism.
  The hook-based agent onboarding plan proposes SessionStart/SubagentStart hooks
  to inject blueprints context deterministically. Its section on "Removing
  redundant CLAUDE.md instructions" (lines 104-115) is an instance of the same
  consolidation question: when hooks enforce something, do text instructions
  become redundant? That plan also includes its own navigation protocol wording
  (line 54-56): "Before editing any source file in src/, read its design file
  in blueprints/src/. The source file is truth; the design file is the
  explanation. Keep design files updated when you change source files." -- yet
  another wording variant, using "blueprints" terminology instead of
  ".lexibrary" (because that plan is for this project's own blueprints, not
  the Lexibrary product).

- **Priority**: This review is lower priority than the conventions-as-artifact
  workstream and the navigation-by-intent investigation. The most actionable
  items (fixing mechanism drift in quick-reference.md, refactoring cursor.py to
  share wording with base.py) can be done independently as small PRs without
  waiting for a full architectural decision.
