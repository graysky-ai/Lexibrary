# Topology Builder Improvement Plan

Revised plan for improving the topology-builder skill output quality and
trimming TOPOLOGY.md to its core structural-map purpose.

Supersedes the original topology-builder post-mortem. Retains all original
findings (entry point detection, signal-to-noise, template contradictions,
module selection guidance). Drops GUIDE.md and context-builder rename --
content that would have gone into GUIDE.md is already served by `lexi
concepts`, `lexi lookup`, and CLAUDE.md.

**Relationship to `topology-skill-plan.md`**: The topology-skill-plan has
been fully implemented (phases P1-P7 complete). This plan is a follow-on
that improves the quality of the topology-builder skill output based on
lessons learned from the initial implementation. It does not revisit any
decisions from the skill plan; it builds on the infrastructure that plan
delivered. The topology-skill-plan should be archived once this plan is
approved.

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Skill name | `topology-builder` (unchanged) | Single output artifact; rename not justified |
| GUIDE.md | Drop entirely | Conventions via `lexi concepts --tag convention`, dev commands via CLAUDE.md, extension points via `lexi lookup` |
| Key Architectural Insights | **Keep** in template | Non-obvious design decisions that agents genuinely need -- but skill must only include insights not derivable from CLAUDE.md, README, or `lexi concepts` |
| Test Structure | **Keep** in template | Agents need to know which test file covers which module, and whether to add tests to an existing file or create a new one |
| Exception hierarchy + key deps | Drop from TOPOLOGY.md | Derivable from `exceptions.py` and `pyproject.toml` |
| Coding Conventions | Drop from TOPOLOGY.md | Authoritative source is CLAUDE.md `## Constraints`; duplication causes drift |
| Common Workflows | Drop from TOPOLOGY.md | Already in CLAUDE.md verbatim |
| Key Entry Points for New Agents | Drop from TOPOLOGY.md | Already in CLAUDE.md `## Agent Rules` |
| .claude/skills/ mirror | **Required** (not conditional) | `.claude/skills/topology-builder/` confirmed to exist; must be updated in lockstep |
| Section markers in raw topology | HTML comments | Primary use: agent section navigation; secondary: future programmatic parsing |
| Phase ordering | Raw improvements -> templates + SKILL.md -> mirror -> code check -> dogfood | Phase 2 can run in parallel with Phase 1; Phase 3 depends on Phase 1 |
| Dogfood regeneration | Run skill fresh (not manual trim) | Manual trim drifts from what the skill would actually produce; end-to-end run validates the whole system |
| Directory detail filtering | Config allowlist (`topology.detail_dirs`) | Dominant source dir always gets full tables; optional config allowlist for additional dirs. Project-agnostic, user-controllable |
| Template-mirror lockstep | Automated test verification | A test asserts deployed mirror files match source templates; prevents drift |

---

## TOPOLOGY.md Sections

### Sections to keep (structural map + agent-navigable)

| Section | Purpose |
|---------|---------|
| Project description (1 line) | "What is this?" |
| Directory Tree Legend | Explains billboard fragment format |
| Entry Points | "What can I run?" |
| Project Config | "What toolchain is this?" |
| Directory Tree (annotated) | "Where do I look for X?" |
| Key Architectural Insights | "What will I get wrong without this?" (non-derivable only) |
| Core Modules (grouped by role) | "Which file do I open?" |
| Test Structure | "Which test file covers this module? Do I add to existing or create new?" |

### Sections removed

| Section | Why | Where to find it instead |
|---------|-----|--------------------------|
| Exception Hierarchy | Derivable | `src/**/exceptions.py` or `errors.py` |
| Key Dependencies | Derivable | `pyproject.toml` / `package.json` |
| Coding Conventions | Duplicates CLAUDE.md | CLAUDE.md `## Constraints` |
| Common Workflows | Duplicates CLAUDE.md | CLAUDE.md `## Commands` + Agent Rules |
| Key Entry Points for New Agents | Duplicates CLAUDE.md | CLAUDE.md `## Agent Rules` |

---

## Impact Map

Every file that references `TOPOLOGY.md`, `topology-builder`, or related
concepts. Grouped by change type.

### Skill files (template update)

| Path | Change |
|------|--------|
| `src/lexibrary/templates/rules/skills/topology-builder/assets/topology_template.md` | Trim to kept sections; update Key Architectural Insights and Test Structure guidance |
| `src/lexibrary/templates/rules/skills/topology-builder/SKILL.md` | Add section-marker usage, revised workflow, section mapping, Key Arch Insights guidance, Test Structure guidance |

### Dogfood skill mirror (must be updated in lockstep)

| Path | Change |
|------|--------|
| `.claude/skills/topology-builder/assets/topology_template.md` | Mirror of above |
| `.claude/skills/topology-builder/SKILL.md` | Mirror of above |

### Source code

| File | Lines | Change |
|------|-------|--------|
| `src/lexibrary/archivist/topology.py` | various | Section markers, entry point candidates list, collapsed test directories, configurable detail dir filtering |
| `src/lexibrary/config/schema.py` | new field | Add `topology.detail_dirs` optional list field |
| `src/lexibrary/init/rules/claude.py` | 310-342 | Verify file manifest still accurate after template changes |

### Tests

| File | Change |
|------|--------|
| `tests/test_archivist/test_topology.py` | Update for section markers, entry point candidates format, collapsed test directory format, detail_dirs filtering |
| `tests/test_config/test_schema.py` | Add test for `topology.detail_dirs` config field |
| `tests/test_init/test_rules/test_claude.py` | Update if file manifest in `claude.py` changes |
| New: test for template-mirror lockstep | Assert `src/.../templates/rules/skills/` files match `.claude/skills/` deployed copies |

### Dogfood artifact (regenerated by skill, not manually trimmed)

| File | Change |
|------|--------|
| `.lexibrary/TOPOLOGY.md` | Regenerated by running the updated topology-builder skill after `lexictl update` |

### Other references (verify -- no change expected)

These files are expected to need no changes, but each must be verified
during Phase 4 (not assumed).

| File | Expected | Verification |
|------|----------|--------------|
| `src/lexibrary/cli/lexi_app.py` | Orient reads TOPOLOGY.md generically; no section parsing | Grep for removed section names; confirm no parsing of specific sections |
| `src/lexibrary/archivist/pipeline.py` | Hint messages reference `/topology-builder` correctly | Grep for hint text; confirm no references to removed sections |
| `src/lexibrary/cli/lexictl_app.py` | Hint messages reference `/topology-builder` correctly | Grep for hint text; confirm no references to removed sections |

---

## Template Design

### topology_template.md (revised)

```markdown
# Project Topology

*One-sentence description of the project's purpose and primary output artifact.*

**{{PROJECT_NAME}}** is {{ONE_SENTENCE_PURPOSE}}.

## Directory Tree Legend

Directory descriptions in the tree below are synthesised keyword fragments
drawn from the individual file descriptions within that directory. Fragments
are separated by `;` -- each fragment describes a **different file** in that
directory, not multiple aspects of the same file. Use these fragments to
decide which directory to explore next without opening every file.

## Entry Points

*List every executable surface: CLIs, HTTP servers, task runners, importable
top-level modules. Verify against the project's build config.*

| Command / Import | Role | Entry File |
|-----------------|------|-----------|
| `{{command_1}}` | {{role_1}} | `{{path/to/entry_1.py}}` |

*Note any registration mechanism (pyproject.toml scripts, Dockerfile CMD,
package.json scripts).*

## Project Config

| Property | Value |
|----------|-------|
| Language / runtime | `{{Python X.Y}}` |
| Build system | `{{hatchling / setuptools / ...}}` |
| Package manager | `{{uv / pip / poetry / ...}}` |
| Type checker | `{{mypy / pyright / none}}` |
| Linter / formatter | `{{ruff / flake8 / eslint / ...}}` |
| Test runner | `{{pytest / jest / ...}}` |

## Directory Tree

*Synthesise a directory tree with concise, complete annotations for each
directory. Use the billboard fragments from the raw topology as starting
points, but rewrite them into clear navigation hints.*

## Key Architectural Insights

*Non-obvious design decisions that a new agent is most likely to get wrong.
Each subsection answers "why does it work this way?" not "what does it do?"*

*Only include insights that cannot be derived from CLAUDE.md, the project
README, or `lexi concepts`. Review any existing insights from the previous
TOPOLOGY.md: keep those that are still accurate, remove those that are
outdated or now covered by other sources.*

### {{Insight Title 1}}

{{Explanation of the design decision and its consequences for editing code.}}

## Core Modules

*Group modules by functional role. Include a file if an agent working on a
typical task would need to open it, call into it, or understand its API.
Omit re-export files, internal-only helpers, and files self-explanatory
from their name and location.*

### {{Category -- e.g. "CLI Layer"}}

*{{Brief description of what files in this category share.}}*

| Module | Purpose |
|--------|---------|
| `{{path/to/module.py}}` | {{One-sentence role.}} |

## Test Structure

*Maps each test directory to the source it covers. Helps agents find the
right test file and decide whether to add tests to an existing file or
create a new one.*

| Test directory / file | Covers |
|----------------------|--------|
| `tests/{{test_subdir}}/` | `src/{{subdir}}/` |

*New tests for an existing module: add to the existing `test_<module>.py`
file. New tests for a new submodule: create a new `test_<module>.py` file
in the matching `test_<subdir>/` directory.*

*Test fixtures live in `{{tests/fixtures/}}`. Shared helpers are in
`{{tests/conftest.py}}`.*
```

---

## Skill Update (topology-builder SKILL.md)

Key changes from the current skill.

### Revised Workflow

1. Read `.lexibrary/tmp/raw-topology.md`. Use `<!-- section: NAME -->` /
   `<!-- end: NAME -->` markers to locate each section efficiently.
2. Read `assets/topology_template.md` (relative to this skill directory)
   for the required section structure.
3. Read `pyproject.toml` to verify entry points and extract build config.
4. For Key Architectural Insights: read the existing `.lexibrary/TOPOLOGY.md`
   (if present) and **review** each existing insight:
   - Read the relevant source files to confirm the insight is still accurate.
   - Check whether the insight is now covered by CLAUDE.md, the README, or
     `lexi concepts`. If so, remove it.
   - Keep insights that are still accurate and not served by those sources.
   - Add new insights only if they meet the bar: an agent would plausibly
     make the wrong assumption without it.
5. Synthesise and write `.lexibrary/TOPOLOGY.md`.

### Section mapping

| Raw topology section | TOPOLOGY.md section | Action |
|---------------------|---------------------|--------|
| `header` | Project description | One-sentence purpose |
| `entry-point-candidates` | Entry Points | Verify against pyproject.toml; include all confirmed entries |
| `config` | Project Config | Extract key properties |
| `tree` | Directory Tree | Synthesise with rewritten annotations (not raw billboard fragments) |
| (source + existing TOPOLOGY.md) | Key Architectural Insights | Review existing insights for accuracy; add new only if non-derivable |
| `source-modules` | Core Modules | Select and group by functional role |
| `test-layout` | Test Structure | Directory-level summaries; note add-to-existing vs create-new convention |

### Section marker usage (new)

The raw topology wraps each section in HTML comments visible in plain-text:

```
<!-- section: entry-point-candidates -->
...content...
<!-- end: entry-point-candidates -->
```

Use these markers to jump directly to the relevant section when synthesising
a specific output section. Do not rely on line numbers or string matching.
The markers are also available for any future programmatic parsing tools.

### Entry point candidates format (new)

The `entry-point-candidates` section lists ALL files matching entry-point
keywords, with confidence signals:

```markdown
<!-- section: entry-point-candidates -->
## Entry Point Candidates

*Heuristic matches -- verify against pyproject.toml before including.*

| File | Directory | Signal | Confidence |
|------|-----------|--------|------------|
| `src/lexibrary/cli/lexi_app.py` | cli | preferred_dir + keyword | high |
| `src/lexibrary/cli/lexictl_app.py` | cli | preferred_dir + keyword | high |
| `src/lexibrary/__main__.py` | lexibrary | keyword | medium |

**Confidence key**: `preferred_dir` = file is in a CLI/app/cmd/main/bin
directory; `keyword` = description contains entry-point keywords.
<!-- end: entry-point-candidates -->
```

The skill must still verify each candidate against `pyproject.toml`
`[project.scripts]` (or equivalent) before including it in the Entry
Points table.

### Core Modules guidance (new)

> Include a file in Core Modules if an agent working on a typical task
> would need to open it, call into it, or understand its API. Omit
> re-export files (e.g. `__init__.py`, `index.ts`, `mod.rs`) whose role
> is implied by the package. Omit internal helpers only called from one
> place. Omit files that are self-explanatory from name and location.
> Group by functional role (e.g. "CLI Layer", "Data Models", "Services"),
> not by directory path.

### Key Architectural Insights guidance (new)

> Include an insight only if an agent would plausibly make the wrong
> assumption without it. Before writing a new insight, check whether the
> information already appears in CLAUDE.md, the project README, or
> `lexi concepts`. If it does, omit it.
>
> Review each existing insight from the previous TOPOLOGY.md individually:
> read the relevant source files to confirm it is still accurate, and
> check whether it is now served by CLAUDE.md, README, or `lexi concepts`.
> Remove insights that are outdated or redundant. Keep insights that are
> still accurate and non-derivable. This is a review-and-prune process,
> not an accumulation process.

### Test Structure guidance (new)

> Write directory-level summaries mapping `tests/test_<subdir>/` to
> `src/<subdir>/`. For top-level test files, list them individually.
> Note where fixtures and shared conftest helpers live.
>
> Always include the convention for adding tests: add to the existing
> `test_<module>.py` file if the module already has one; create a new
> `test_<module>.py` in the matching `test_<subdir>/` directory only when
> adding coverage for a new submodule.

### Writing rules to keep (unchanged)

- **Treat raw data as signals, not copy** -- keyword fragments are inputs,
  not paste targets. Rewrite into navigation prose.
- **Accuracy over completeness** -- read source files to resolve ambiguities;
  omit rather than guess.
- **Entry points require verification** -- always confirm from `pyproject.toml`.
- **Agent-navigable means navigation-first** -- every section answers
  "where do I look for X?" not "this project has X."
  - "Where is the CLI code?" not "This project has a CLI."
  - "To add a new command, edit `src/.../commands/` and register in X."
    not "Commands are registered in the command registry."
- **Absolute paths** -- anchor from repo root (e.g. `src/lexibrary/`).
- **Flag uncovered layouts** -- note in a final "Uncovered Layouts" section
  if the template does not adequately cover the project structure.

---

## Raw Topology Improvements

Changes to `src/lexibrary/archivist/topology.py` that improve the input
consumed by the topology-builder skill. These are implemented in Phase 1,
before the SKILL.md update, so the SKILL.md can reference the new format.

### 1. Section markers

Wrap each section in `<!-- section: NAME -->` / `<!-- end: NAME -->` pairs.
Sections: `header`, `entry-point-candidates`, `tree`, `source-modules`,
`test-layout`, `config`, `stats`.

These markers are plain text visible to agents reading the file. Primary
purpose: agent section navigation. Secondary purpose: future programmatic
parsing.

### 2. Entry point candidates (replaces single-entry-point header)

List ALL entries matching `_ENTRY_POINT_KEYWORDS`, not just the top one.
Include the confidence signal (preferred dir, keyword match type). Label
as "candidates" needing verification against pyproject.toml. Output as a
markdown table with columns: File, Directory, Signal, Confidence. See
"Entry point candidates format" in the Skill Update section for the
concrete format.

### 3. Collapse test directories

Replace per-file tables in test dirs with one-line summaries:
`test_archivist/ -- 4 files covering archivist/`. This reduces raw
topology size; the Test Structure section in TOPOLOGY.md provides the
agent-navigable view.

### 4. Configurable directory detail filtering

Filter `_generate_directory_details()` to emit full file tables for:
- Directories under the dominant source dir (auto-detected, always on)
- Directories matching patterns in `topology.detail_dirs` config (optional)

Everything else gets a one-line summary.

**Config schema addition** (`src/lexibrary/config/schema.py`):

```python
class TopologyConfig(BaseModel):
    detail_dirs: list[str] = Field(
        default_factory=list,
        description="Glob patterns for directories that get full file tables in raw topology (in addition to the auto-detected source dir).",
    )
```

**Scaffolded config** (commented-out example in generated `config.yaml`):

```yaml
# topology:
#   detail_dirs:
#     - "baml_src/**"
#     - "docs/agent/**"
```

**Note**: After implementing this change, review `_apply_token_sentinel()`
to ensure its trimming strategy (largest-directory-first) still makes sense
with the new content shape. The size reductions from collapsed test dirs
and filtered detail tables may change which directories the sentinel
targets. Add a `# TODO: review sentinel strategy after detail_dirs` comment
in the sentinel function.

---

## Implementation Phases

### Phase 1: Raw topology improvements + tests

**Implement improvements to `topology.py` and config schema. Update tests
immediately so they pass before moving on.**

**Phase 2 (template update) can run in parallel with Phase 1 since it has
no dependency on the raw topology format.**

1. `src/lexibrary/archivist/topology.py`: Add section markers, entry point
   candidates list, collapsed test directories, configurable detail dir
   filtering
2. `src/lexibrary/config/schema.py`: Add `topology.detail_dirs` field
3. `tests/test_archivist/test_topology.py`: Update for section markers,
   entry point candidates format, collapsed test directory format,
   detail_dirs filtering
4. `tests/test_config/test_schema.py`: Add test for `topology.detail_dirs`
   config field

### Phase 2: Template update + tests

**Trim `topology_template.md` to the kept sections. Can run in parallel
with Phase 1.**

1. `src/lexibrary/templates/rules/skills/topology-builder/assets/topology_template.md`:
   Remove Key Dependencies, Exception Hierarchy, Coding Conventions,
   Common Workflows, Key Entry Points for New Agents. Update Key
   Architectural Insights and Test Structure guidance comments in the
   template.

### Phase 3: SKILL.md update

**Depends on Phase 1 (SKILL.md references section markers).**

1. `src/lexibrary/templates/rules/skills/topology-builder/SKILL.md`:
   - Add revised workflow (steps 1-5 above)
   - Add section mapping table
   - Add section marker usage guidance
   - Add entry point candidates format documentation
   - Add Core Modules guidance
   - Add Key Architectural Insights guidance (review-and-prune, not accumulate)
   - Add Test Structure guidance
   - Confirm existing writing rules are retained

### Phase 4: Mirror updates + verification

**`.claude/skills/topology-builder/` is confirmed to exist. Update in
lockstep -- it is not conditional.**

> **Dogfood boundary warning**: Always edit the source templates
> (`src/lexibrary/templates/rules/skills/topology-builder/`) first, then
> copy to `.claude/skills/topology-builder/`. Never edit the mirror
> directly. If a fix is needed, trace it back to the source template.

1. `.claude/skills/topology-builder/assets/topology_template.md`:
   Mirror of Phase 2 changes
2. `.claude/skills/topology-builder/SKILL.md`:
   Mirror of Phase 3 changes
3. Add template-mirror lockstep test: assert that each file under
   `src/lexibrary/templates/rules/skills/` has an identical deployed copy
   under `.claude/skills/`. This test should cover ALL skill templates,
   not just topology-builder. Place in `tests/test_init/test_rules/` or
   a new `tests/test_skills_mirror.py`.

**Convention**: Any time a new skill template is created under
`src/lexibrary/templates/rules/skills/`, a corresponding mirror must exist
under `.claude/skills/`, and the lockstep test automatically covers it.
Document this as a playbook or convention artifact.

### Phase 5: Source code verification

**Verify no code references removed TOPOLOGY.md sections or has stale
file manifests.**

1. `src/lexibrary/init/rules/claude.py` (lines 310-342): Confirm file
   manifest is still accurate after template file changes. Update if needed.
2. Grep for any code that parses specific removed sections from TOPOLOGY.md
   (e.g., "Exception Hierarchy", "Key Dependencies", "Coding Conventions",
   "Common Workflows", "Key Entry Points").
3. Verify `src/lexibrary/cli/lexi_app.py`: grep for removed section names;
   confirm orient reads TOPOLOGY.md generically with no section parsing.
4. Verify `src/lexibrary/archivist/pipeline.py`: grep for hint text;
   confirm no references to removed sections.
5. Verify `src/lexibrary/cli/lexictl_app.py`: grep for hint text; confirm
   no references to removed sections.
6. Update tests if any changes were needed:
   - `tests/test_init/test_rules/test_claude.py` if file manifest changed

### Phase 6: Dogfood regeneration (requires user action)

**Do not manually trim `.lexibrary/TOPOLOGY.md`. Run the updated skill to
produce the fresh output -- this validates the whole system end-to-end.**

> **Dogfood boundary warning**: In this phase you are acting as a **user**
> of the product, not a developer. If the generated TOPOLOGY.md has issues,
> do not patch `.lexibrary/TOPOLOGY.md` by hand. Trace the fix back to
> product code (Phases 1-3), update the source templates, mirror to
> `.claude/skills/` (Phase 4), and re-run.

1. Ask the user to run `lexictl update` to regenerate
   `.lexibrary/tmp/raw-topology.md` with the Phase 1 improvements
   (section markers, entry point candidates, collapsed test dirs)
2. Run the topology-builder skill to produce a fresh `.lexibrary/TOPOLOGY.md`
3. Verify the output matches the structural-map-only design (success
   criteria below)

---

## Risks

### Dogfood loop confusion

This plan touches both sides of the product/instance boundary:

| Phase | Context | What you're doing |
|-------|---------|-------------------|
| Phases 1-3, 5 | **Developer** (lexi-as-subject) | Editing product code under `src/` and `tests/` |
| Phase 4 | **Both** | Copying from `src/.../templates/` (product) to `.claude/skills/` (instance) |
| Phase 6 | **User** (lexi-as-user) | Running `lexictl update` + `/topology-builder` skill against the live `.lexibrary/` instance |

**Where it gets dangerous**:

1. **Phase 4 is a bridge phase.** The implementing agent reads from
   `src/lexibrary/templates/rules/skills/topology-builder/` (product code)
   and writes to `.claude/skills/topology-builder/` (dogfood instance). The
   files look nearly identical in path and content; only the root prefix
   differs. If the agent edits the wrong copy, the lockstep invariant
   breaks silently.

2. **Phase 6 requires a context switch.** The agent has been working as a
   developer for Phases 1-5. In Phase 6, it must switch to acting as a
   user of the product. If the skill produces bad output, the instinct
   will be to fix the output file -- but the correct action is to go back
   and fix the product code (template or SKILL.md) and regenerate.

3. **Debugging loops cross the boundary.** If the skill produces bad output,
   the cause could be in the raw topology code (product), the deployed
   SKILL.md (instance), the source template (product), or the raw data
   (instance artifact). An agent chasing a bug might edit the wrong layer.

**Mitigation**: Dogfood boundary warnings are placed in Phase 4 and Phase 6
instructions above.

---

## Success Criteria

The implementation is complete when:

**Structure**
- [ ] TOPOLOGY.md contains exactly the 7 kept sections and no removed sections
- [ ] No Coding Conventions, Common Workflows, Key Entry Points, Key
  Dependencies, or Exception Hierarchy sections present

**Key Architectural Insights**
- [ ] Every insight in the section would genuinely mislead an agent if absent
- [ ] No insight is a verbatim restatement of content in CLAUDE.md or README
- [ ] Existing insights from the previous TOPOLOGY.md have been individually
  reviewed: kept if still accurate and non-derivable, removed if outdated
  or redundant

**Test Structure**
- [ ] Each `tests/test_<subdir>/` is mapped to its `src/<subdir>/`
- [ ] The add-to-existing vs create-new convention is documented

**Directory Tree**
- [ ] Annotations are complete phrases, not raw billboard keyword fragments

**Raw topology**
- [ ] `raw-topology.md` contains `<!-- section: NAME -->` markers for all
  7 sections
- [ ] Entry point candidates section lists all matches as a table with
  File, Directory, Signal, and Confidence columns
- [ ] Test directories are collapsed to one-line summaries
- [ ] Full file tables only appear for dominant source dir + configured
  `detail_dirs`

**Tests**
- [ ] All existing tests pass
- [ ] Template-mirror lockstep test covers all skill templates (not just
  topology-builder)
- [ ] Tests updated alongside each phase (not batched)

**Dogfood**
- [ ] `.lexibrary/TOPOLOGY.md` was generated by running the skill, not
  manually edited
- [ ] Both `src/lexibrary/templates/rules/skills/topology-builder/` and
  `.claude/skills/topology-builder/` have identical SKILL.md and
  topology_template.md (verified by automated test)

---

## File Inventory

### Phase 1 (raw topology improvements + tests)

- `src/lexibrary/archivist/topology.py`
- `src/lexibrary/config/schema.py`
- `tests/test_archivist/test_topology.py`
- `tests/test_config/test_schema.py`

### Phase 2 (template update -- can parallel Phase 1)

- `src/lexibrary/templates/rules/skills/topology-builder/assets/topology_template.md`

### Phase 3 (SKILL.md update -- depends on Phase 1)

- `src/lexibrary/templates/rules/skills/topology-builder/SKILL.md`

### Phase 4 (mirror + lockstep test)

- `.claude/skills/topology-builder/assets/topology_template.md`
- `.claude/skills/topology-builder/SKILL.md`
- New: `tests/test_skills_mirror.py` (or in `tests/test_init/test_rules/`)

### Phase 5 (source code verification + any test updates)

- `src/lexibrary/init/rules/claude.py` (verify/update file manifest)
- `src/lexibrary/cli/lexi_app.py` (verify only)
- `src/lexibrary/archivist/pipeline.py` (verify only)
- `src/lexibrary/cli/lexictl_app.py` (verify only)
- `tests/test_init/test_rules/test_claude.py` (if manifest changed)

### Phase 6 (dogfood -- user runs lexictl, agent runs skill)

- `.lexibrary/TOPOLOGY.md` (generated output, not manually edited)

---

## User Action Required at End

After all phases are implemented and tests pass:

> Please run `lexictl update` to regenerate `.lexibrary/tmp/raw-topology.md`
> with the new section markers and entry point candidates format. Once that
> is done, run the `/topology-builder` skill to produce a fresh
> `.lexibrary/TOPOLOGY.md`.
