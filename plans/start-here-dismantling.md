# Dismantling START_HERE Safely

> Step-by-step restructuring plan for `.lexibrary/START_HERE.md`, based on the
> decisions in [`plans/start-here-reamagined.md`](start-here-reamagined.md).
>
> **Goal**: Restructure START_HERE from 5 LLM-generated sections to 1 procedural
> (topology) + 1 LLM (navigation by intent) + 1 static pointer block. Each
> phase is independently deployable and backwards-compatible.
>
> **Status**: Ready for implementation (Phases 1-3). Phases 4-5 are blocked on
> upstream analysis.

---

## Relationship to `plans/agent-start-plan.md`

**Recommendation: Supersede `agent-start-plan.md`.**

The agent-start-plan proposes hook-based injection of blueprints context into
agent sessions via `SessionStart` and `SubagentStart` hooks. The dismantling
plan restructures what START_HERE *contains*. After analysis (see
[Reconciliation](#reconciliation-with-agent-start-planmd) below), the two plans
are complementary in theory but the hook injection plan is:

1. **Lexibrary-specific** -- it injects `blueprints/HANDOFF.md`, a concept that
   only exists in Lexibrary's own hand-maintained blueprints, not in generated
   `.lexibrary/` output for arbitrary projects.
2. **Partially subsumed** -- the "inject Navigation by Intent table" idea
   (option 2 in agent-start-plan.md) becomes moot once START_HERE is slim
   enough that agents can read it directly without a hook.
3. **Still valuable as a pattern** -- the SessionStart/SubagentStart hook
   mechanism is sound and worth extracting into the agent rules template system
   (`base.py`), but that is a separate concern from START_HERE restructuring.

Mark `plans/agent-start-plan.md` as superseded. Extract the hook mechanism
pattern into a future `plans/hook-based-context-injection.md` if needed.

---

## What We're Removing and Why

| Section | Action | Reason |
|---------|--------|--------|
| **Navigation Protocol** | Remove entirely | Already in 6+ places (agent rules, hooks, docs). LLM regeneration causes wording drift. |
| **Ontology** | Replace with static pointer | Concepts wiki (`lexi concepts`) is the authoritative glossary. LLM guessing from directory names is inferior. |
| **Topology** | Keep, but make procedural | LLM re-synthesises what `.aindex` already provides. Adaptive depth from `.aindex` entries is cheaper and more accurate. |
| **Convention Index** | Remove entirely (blocked) | Only conventions source in the system; currently hallucinated. Needs systemic fix (conventions as first-class artifact). |
| **Navigation by Intent** | Keep as sole LLM section (blocked) | Most valuable section. Needs richer inputs before changing. |

---

## Dependencies and Ordering

```
Phase 1: Remove Navigation Protocol  ──> no dependencies, safe now
Phase 2: Replace Ontology with Pointer ──> no dependencies, safe now
Phase 3: Make Topology Procedural ────> depends on .aindex files existing
                                         (they do after any `lexictl update`)
Phase 4: Enrich Navigation by Intent ──> blocked on plans/navigation-by-intent.md
Phase 5: Remove Convention Index ─────> blocked on plans/conventions-artifact.md
```

Phases 1, 2, and 3 can be done in any order. Phase 3 is the largest.
Phases 4 and 5 are blocked on upstream analysis and cannot proceed yet.

---

## Phase 1: Remove Navigation Protocol

**Risk**: None. Content is duplicated in 6+ other locations.
**Effort**: Small. Remove one field from BAML, service, assembly, tests.

### Files to Change

#### 1. `baml_src/types.baml` (line 35-41)

Remove `navigation_protocol` from `StartHereOutput`:

```diff
 class StartHereOutput {
   topology string
   ontology string
   navigation_by_intent string
   convention_index string
-  navigation_protocol string
 }
```

#### 2. `baml_src/archivist_start_here.baml` (line 46-48)

Remove instruction block 5 from the prompt:

```diff
     4. **convention_index**: A compact bulleted list of naming conventions,
        patterns, or rules observed in the project. 3-8 items.

-    5. **navigation_protocol**: 3-5 bullet instructions telling a reader
-       how to use the .lexibrary knowledge layer effectively (e.g. "read
-       the design file before editing a source file").
-
     Keep total output under 500-800 tokens. Be specific to this project --
```

Update the token guidance (navigation_protocol was ~75 tokens):

```diff
-    Keep total output under 500-800 tokens. Be specific to this project --
+    Keep total output under 400-700 tokens. Be specific to this project --
```

#### 3. Run `baml-cli generate` to regenerate Python client

After editing BAML files, regenerate:
```bash
uv run baml-cli generate
```

This updates `src/lexibrary/baml_client/types.py` -- the `StartHereOutput`
class will lose its `navigation_protocol` field.

#### 4. `src/lexibrary/archivist/start_here.py`

**`_assemble_start_here()` (line 87-119)**: Remove `navigation_protocol` parameter
and its section from assembly:

```diff
 def _assemble_start_here(
     topology: str,
     ontology: str,
     navigation_by_intent: str,
     convention_index: str,
-    navigation_protocol: str,
 ) -> str:
     """Assemble final START_HERE.md markdown from StartHereOutput sections."""
     sections = [
         "# START HERE",
         "",
         "## Project Topology",
         "",
         topology,
         "",
         "## Ontology",
         "",
         ontology,
         "",
         "## Navigation by Intent",
         "",
         navigation_by_intent,
         "",
         "## Convention Index",
         "",
         convention_index,
         "",
-        "## Navigation Protocol",
-        "",
-        navigation_protocol,
-        "",
     ]
     return "\n".join(sections)
```

**`generate_start_here()` (line 195-201)**: Remove `navigation_protocol` from the
call to `_assemble_start_here()`:

```diff
     content = _assemble_start_here(
         topology=output.topology,
         ontology=output.ontology,
         navigation_by_intent=output.navigation_by_intent,
         convention_index=output.convention_index,
-        navigation_protocol=output.navigation_protocol,
     )
```

#### 5. `tests/test_archivist/test_start_here.py`

**`_make_sample_output()` (line 52-60)**: Remove `navigation_protocol` field:

```diff
 def _make_sample_output() -> StartHereOutput:
     return StartHereOutput(
         topology="src/\n  core/\n  utils/",
         ontology="**design file** -- per-file documentation artifact",
         navigation_by_intent="| Task | Read first |\n| --- | --- |\n| Config | src/config/ |",
         convention_index="- snake_case for all modules",
-        navigation_protocol="- Read the design file before editing any source file",
     )
```

**`test_generates_start_here` (line 202-224)**: Remove assertion for Navigation Protocol section:

```diff
         assert "## Navigation by Intent" in content
         assert "## Convention Index" in content
-        assert "## Navigation Protocol" in content
```

#### 6. `openspec/specs/start-here-generation/spec.md` (line 20)

Update the scenario to remove "protocol" from the section list:

```diff
-- **THEN** `.lexibrary/START_HERE.md` SHALL be written with topology, ontology,
-  navigation, conventions, and protocol sections
+- **THEN** `.lexibrary/START_HERE.md` SHALL be written with topology, ontology,
+  navigation, and conventions sections
```

#### 7. `docs/agent/orientation.md` (line 19)

Remove the navigation protocol bullet:

```diff
 - **Navigation by intent** -- a lookup table that maps common tasks...
 - **Key constraints** -- project-wide coding rules...
-- **Navigation protocol** -- instructions to read design files before editing source files
```

### Verification

```bash
uv run baml-cli generate                    # regenerate BAML client
uv run pytest tests/test_archivist/test_start_here.py -v  # tests pass
uv run ruff check src/ tests/               # no lint errors
uv run mypy src/                            # type check passes
```

Manually verify: run `lexictl update --start-here` on a test project and
confirm the output has no "Navigation Protocol" section.

---

## Phase 2: Replace Ontology with Pointer

**Risk**: None. Concepts wiki is the authoritative source.
**Effort**: Small. Replace LLM field with static text injection.

### Files to Change

#### 1. `baml_src/types.baml` (line 35-41)

Remove `ontology` from `StartHereOutput`:

```diff
 class StartHereOutput {
   topology string
-  ontology string
   navigation_by_intent string
   convention_index string
 }
```

#### 2. `baml_src/archivist_start_here.baml` (line 31-33)

Remove instruction block 2 from the prompt:

```diff
     1. **topology**: An ASCII tree or Mermaid diagram showing the top-level
        project structure...

-    2. **ontology**: Define 5-15 key domain terms used in this project. One
-       line per term: `**term** -- definition`. Focus on terms a newcomer
-       would not immediately understand.
-
-    3. **navigation_by_intent**: A markdown table mapping common tasks to
+    2. **navigation_by_intent**: A markdown table mapping common tasks to
```

Renumber subsequent sections. Update token guidance:

```diff
-    Keep total output under 400-700 tokens. Be specific to this project --
+    Keep total output under 300-600 tokens. Be specific to this project --
```

#### 3. Run `baml-cli generate`

#### 4. `src/lexibrary/archivist/start_here.py`

**`_assemble_start_here()` (line 87-119)**: Replace `ontology` parameter with
static pointer text:

```diff
 def _assemble_start_here(
     topology: str,
-    ontology: str,
     navigation_by_intent: str,
     convention_index: str,
 ) -> str:
     """Assemble final START_HERE.md markdown from StartHereOutput sections."""
+    # Static pointer block -- replaces LLM-generated ontology
+    pointers = (
+        "## Quick Links\n"
+        "\n"
+        "- **Domain vocabulary**: run `lexi concepts` or browse "
+        "`.lexibrary/concepts/`\n"
+    )
+
     sections = [
         "# START HERE",
         "",
         "## Project Topology",
         "",
         topology,
         "",
-        "## Ontology",
-        "",
-        ontology,
-        "",
         "## Navigation by Intent",
         "",
         navigation_by_intent,
         "",
         "## Convention Index",
         "",
         convention_index,
         "",
+        pointers,
     ]
     return "\n".join(sections)
```

**`generate_start_here()` (line 195-201)**: Remove `ontology` from the call:

```diff
     content = _assemble_start_here(
         topology=output.topology,
-        ontology=output.ontology,
         navigation_by_intent=output.navigation_by_intent,
         convention_index=output.convention_index,
     )
```

#### 5. `tests/test_archivist/test_start_here.py`

**`_make_sample_output()`**: Remove `ontology` field:

```diff
 def _make_sample_output() -> StartHereOutput:
     return StartHereOutput(
         topology="src/\n  core/\n  utils/",
-        ontology="**design file** -- per-file documentation artifact",
         navigation_by_intent="| Task | Read first |\n| --- | --- |\n| Config | src/config/ |",
         convention_index="- snake_case for all modules",
     )
```

**`test_generates_start_here`**: Replace ontology assertion with pointer assertion:

```diff
         assert "## Project Topology" in content
-        assert "## Ontology" in content
+        assert "## Quick Links" in content
+        assert "lexi concepts" in content
         assert "## Navigation by Intent" in content
```

#### 6. `openspec/specs/start-here-generation/spec.md` (line 20)

```diff
-- **THEN** `.lexibrary/START_HERE.md` SHALL be written with topology, ontology,
-  navigation, and conventions sections
+- **THEN** `.lexibrary/START_HERE.md` SHALL be written with topology,
+  navigation, conventions sections, and a quick-links pointer block
```

#### 7. `docs/agent/orientation.md`

Replace the package map bullet (which describes the old ontology) with a pointer note:

```diff
-- **Package map** -- a table listing each package and its role...
+- **Quick links** -- pointers to domain vocabulary (`lexi concepts`) and other resources
```

### Verification

Same as Phase 1 -- run BAML generate, tests, lint, type check, and manual
`lexictl update --start-here`.

---

## Phase 3: Make Topology Procedural

**Risk**: Low. Depends on `.aindex` files existing (they do after `lexictl update`).
**Effort**: Medium. New helper function, changes to assembly, BAML prompt changes.

This is the largest phase. Topology stops being LLM-generated and becomes a
procedural function that reads `.aindex` files and builds an adaptive-depth
annotated tree.

### New Helper Function: `_build_procedural_topology()`

Add to `src/lexibrary/archivist/start_here.py`:

```python
def _build_procedural_topology(project_root: Path) -> str:
    """Build an annotated project topology from .aindex billboard summaries.

    Reads all .aindex files in the mirror tree and builds a depth-adaptive
    indented tree with billboard annotations. Depth adapts to project scale:
    - Small (<=10 dirs): full tree
    - Medium (11-40 dirs): depth <= 2 + hotspots (>5 child entries)
    - Large (41+ dirs): depth <= 1 + hotspots + top-N by child count

    Returns an indented tree string suitable for START_HERE.md.
    """
    lexibrary_root = project_root / LEXIBRARY_DIR
    if not lexibrary_root.is_dir():
        return "(no .lexibrary directory found)"

    # 1. Collect all .aindex files and parse them
    aindex_data: dict[str, tuple[str, int]] = {}  # rel_path -> (billboard, child_count)
    for aindex_path in sorted(lexibrary_root.rglob(".aindex")):
        parsed = parse_aindex(aindex_path)
        if parsed is None:
            continue
        child_count = len(parsed.entries)
        aindex_data[parsed.directory_path] = (parsed.billboard, child_count)

    if not aindex_data:
        return "(no .aindex files found -- run `lexictl update` first)"

    # 2. Calculate adaptive depth
    nodes = len(aindex_data)
    max_depth = max((p.count("/") for p in aindex_data), default=0)

    if nodes <= 10:
        display_depth = max_depth  # show everything
        hotspot_threshold = 0      # no filtering
    elif nodes <= 40:
        display_depth = 2
        hotspot_threshold = 5
    else:
        display_depth = 1
        hotspot_threshold = 5

    # 3. Build display set
    display_paths: set[str] = set()
    for rel_path, (billboard, child_count) in aindex_data.items():
        depth = rel_path.count("/")
        if depth <= display_depth:
            display_paths.add(rel_path)
        elif child_count > hotspot_threshold:
            display_paths.add(rel_path)

    # 4. Render tree
    # Use root .aindex billboard as header if available
    root_key = next(
        (k for k in aindex_data if "/" not in k and k != "."),
        None,
    )
    root_billboard = aindex_data.get(".", ("", 0))[0]

    lines: list[str] = []
    if root_billboard:
        lines.append(f"{project_root.name}/ -- {root_billboard}")
    else:
        lines.append(f"{project_root.name}/")

    # Sort paths for stable output, render with indentation
    for rel_path in sorted(display_paths):
        if rel_path == ".":
            continue
        billboard, child_count = aindex_data[rel_path]
        depth = rel_path.count("/")
        indent = "  " * (depth + 1)
        dir_name = rel_path.rsplit("/", 1)[-1] if "/" in rel_path else rel_path

        # Count hidden children
        hidden_children = sum(
            1 for p in aindex_data
            if p.startswith(rel_path + "/")
            and p.count("/") == rel_path.count("/") + 1
            and p not in display_paths
        )
        suffix = f" ({hidden_children} subdirs)" if hidden_children > 0 else ""
        lines.append(f"{indent}{dir_name}/ -- {billboard}{suffix}")

    return "\n".join(lines)
```

### Changes to `_assemble_start_here()`

The `topology` parameter no longer comes from the LLM. Instead, the caller
passes in the procedurally-generated topology:

```diff
-def _assemble_start_here(
-    topology: str,
-    navigation_by_intent: str,
-    convention_index: str,
-) -> str:
+def _assemble_start_here(
+    procedural_topology: str,
+    navigation_by_intent: str,
+    convention_index: str,
+) -> str:
     """Assemble final START_HERE.md markdown from mixed procedural/LLM sections."""
     pointers = (
         "## Quick Links\n"
         "\n"
         "- **Domain vocabulary**: run `lexi concepts` or browse "
         "`.lexibrary/concepts/`\n"
     )

     sections = [
         "# START HERE",
         "",
         "## Project Topology",
         "",
-        topology,
+        procedural_topology,
         "",
         "## Navigation by Intent",
         "",
```

### Changes to `generate_start_here()`

The function now builds topology procedurally and only sends the remaining
sections to the LLM:

```diff
 async def generate_start_here(
     project_root: Path,
     config: LexibraryConfig,
     archivist: ArchivistService,
 ) -> Path:
-    # 1. Build directory tree
-    directory_tree = _build_directory_tree(project_root, config)
+    # 1. Build procedural topology from .aindex files
+    procedural_topology = _build_procedural_topology(project_root)

-    # 2. Collect .aindex summaries
+    # 2. Collect .aindex summaries (still needed as LLM input for nav-by-intent)
     aindex_summaries = _collect_aindex_summaries(project_root)

     # 3. Read existing START_HERE.md if present
     ...

-    # 4. Call LLM via archivist service
+    # 4. Build directory tree for LLM (nav-by-intent still needs structural context)
+    directory_tree = _build_directory_tree(project_root, config)
+
+    # 5. Call LLM via archivist service (only nav-by-intent + convention_index)
     request = StartHereRequest(
         project_name=project_name,
         directory_tree=directory_tree,
         aindex_summaries=aindex_summaries or "(no .aindex files found)",
         existing_start_here=existing_start_here,
     )
     result = await archivist.generate_start_here(request)
     ...

-    # 5. Assemble final markdown
+    # 6. Assemble final markdown (procedural topology + LLM sections)
     content = _assemble_start_here(
-        topology=output.topology,
+        procedural_topology=procedural_topology,
         navigation_by_intent=output.navigation_by_intent,
         convention_index=output.convention_index,
     )
```

### BAML Changes

#### `baml_src/types.baml`

Remove `topology` from `StartHereOutput`:

```diff
 class StartHereOutput {
-  topology string
   navigation_by_intent string
   convention_index string
 }
```

#### `baml_src/archivist_start_here.baml`

Remove topology instruction from the prompt. The LLM now only generates
navigation_by_intent and convention_index:

```diff
     INSTRUCTIONS -- produce each section concisely:

-    1. **topology**: An ASCII tree or Mermaid diagram showing the top-level
-       project structure. Include only directories and key files -- not every
-       leaf file. Aim for 10-20 lines.
-
-    2. **navigation_by_intent**: A markdown table mapping common tasks to
+    1. **navigation_by_intent**: A markdown table mapping common tasks to
        the file or directory to read first. Format:
        ...

-    3. **convention_index**: A compact bulleted list of naming conventions,
+    2. **convention_index**: A compact bulleted list of naming conventions,
```

Update token guidance:

```diff
-    Keep total output under 300-600 tokens. Be specific to this project --
+    Keep total output under 200-400 tokens. Be specific to this project --
```

#### Run `baml-cli generate`

### Test Changes

**`_make_sample_output()`**: Remove `topology`:

```diff
 def _make_sample_output() -> StartHereOutput:
     return StartHereOutput(
-        topology="src/\n  core/\n  utils/",
         navigation_by_intent="| Task | Read first |\n| --- | --- |\n| Config | src/config/ |",
         convention_index="- snake_case for all modules",
     )
```

**New test class: `TestBuildProceduralTopology`**: Add tests for the new helper:

```python
class TestBuildProceduralTopology:
    """Verify procedural topology generation from .aindex files."""

    def test_small_project_shows_all(self, project_with_aindex: Path) -> None:
        topology = _build_procedural_topology(project_with_aindex)
        assert "src/" in topology
        assert "core/" in topology
        assert "utils/" in topology
        assert "Main source code directory" in topology

    def test_no_lexibrary_dir(self, tmp_path: Path) -> None:
        topology = _build_procedural_topology(tmp_path)
        assert "no .lexibrary directory" in topology

    def test_no_aindex_files(self, project_dir: Path) -> None:
        topology = _build_procedural_topology(project_dir)
        assert "no .aindex files" in topology

    def test_billboard_annotations(self, project_with_aindex: Path) -> None:
        topology = _build_procedural_topology(project_with_aindex)
        assert "Core business logic" in topology
        assert "Shared utility functions" in topology
```

**Update `test_generates_start_here`**: Replace topology assertion:

```diff
         assert "## Project Topology" in content
-        assert sample_output.topology in content
+        # Topology is now procedural, not from LLM output
+        assert "src/" in content or "Main source code" in content
```

**`_build_directory_tree` tests**: These tests remain valid -- the function is
still used to provide structural context to the LLM for navigation_by_intent.

### `src/lexibrary/config/schema.py`

Consider lowering the default `start_here_tokens` budget from 800 since half
the content is now procedural:

```diff
-    start_here_tokens: int = 800
+    start_here_tokens: int = 600
```

### Verification

```bash
uv run baml-cli generate
uv run pytest tests/test_archivist/test_start_here.py -v
uv run ruff check src/ tests/
uv run mypy src/
```

Manual test: run `lexictl update` on a project with `.aindex` files, confirm
topology section shows annotated tree from `.aindex` data, not LLM-generated
prose.

---

## Phase 4: Enrich Navigation by Intent

**Status**: Blocked on `plans/navigation-by-intent.md` (does not exist yet).

### What's Known Now

- Navigation by Intent is the most valuable START_HERE section.
- Current quality is limited because the LLM only sees billboard summaries.
- Richer inputs would improve quality: design file frontmatter descriptions,
  concept tags, link graph edge counts, Stack post titles.
- The section should remain LLM-generated -- the editorial judgement of "what
  are the 5-10 most common tasks?" is hard to do procedurally.

### What's Blocked

- Need to decide what additional inputs to pass to the LLM.
- Need to update `StartHereRequest` with new fields (design file summaries,
  concept summaries, link graph data).
- Need to update the BAML prompt to use richer context.
- Need to prototype and evaluate output quality.

### Files That Will Change (When Unblocked)

- `src/lexibrary/archivist/start_here.py` -- new collection functions for
  design file summaries, concept summaries, link graph data
- `src/lexibrary/archivist/service.py` -- `StartHereRequest` gets new fields
- `baml_src/archivist_start_here.baml` -- prompt enrichment
- `baml_src/types.baml` -- no change (output stays the same)
- `tests/test_archivist/test_start_here.py` -- new test fixtures with richer data

### Placeholder

Create `plans/navigation-by-intent.md` when ready to investigate. The analysis
should answer:

1. What inputs produce the best routing table?
2. Should it remain purely LLM-generated or become partially procedural?
3. Should `lexi navigate` replace or complement the static table?

---

## Phase 5: Remove Convention Index

**Status**: Blocked on `plans/conventions-artifact.md` (does not exist yet).

### Why It's Blocked

Convention Index is currently the **only** place conventions exist in the entire
Lexibrary system. The `.aindex` `local_conventions` field is hard-coded to `[]`.
The link graph conventions table is empty. Removing the section from START_HERE
without first building a real conventions system would leave agents with zero
conventions visibility.

### Prerequisites

1. Conventions must have a real storage model (files, `.aindex` fields, or DB).
2. A population pipeline must exist (LLM extraction during design file
   generation, or user-declared in config, or both).
3. `lexi lookup` must surface conventions for files being edited.
4. Only then can the Convention Index section be removed from START_HERE.

### Files That Will Change (When Unblocked)

- `baml_src/types.baml` -- remove `convention_index` from `StartHereOutput`
- `baml_src/archivist_start_here.baml` -- remove convention instruction
- `src/lexibrary/archivist/start_here.py` -- remove from assembly; add
  conventions pointer to Quick Links block
- `tests/test_archivist/test_start_here.py` -- remove convention assertions
- `docs/agent/orientation.md` -- remove "Key constraints" bullet

### Expected Quick Links After Phase 5

```markdown
## Quick Links

- **Domain vocabulary**: run `lexi concepts` or browse `.lexibrary/concepts/`
- **Conventions**: run `lexi lookup <file>` to see applicable conventions
- **Workflow**: see your agent rules file (CLAUDE.md / .cursor/rules / AGENTS.md)
```

### Placeholder

Create `plans/conventions-artifact.md` when ready to design. This is the
largest piece of work spawned by the reimagined analysis.

---

## Risk Mitigation

### Each phase is independently deployable

Phases 1-3 can each be implemented, tested, and merged independently. The
START_HERE assembly function shrinks with each phase but always produces valid
markdown. No phase depends on another having been completed first (except that
Phases 4-5 are blocked on upstream analysis).

### No migration needed

Existing `.lexibrary/START_HERE.md` files in user projects will have the old
5-section format. The next `lexictl update` (or `lexictl update --start-here`)
will regenerate with the new format. The old file is simply overwritten.

### Regeneration is automatic

START_HERE is regenerated on every `lexictl update` (full project update, see
`src/lexibrary/archivist/pipeline.py` line 803-809). Users do not need to take
any manual action.

### Test strategy per phase

| Phase | Test approach |
|-------|---------------|
| 1 | Remove field from mock output, remove assertion for section, verify no regression |
| 2 | Replace field with static text, assert pointer text present in output |
| 3 | New `TestBuildProceduralTopology` class; existing tree tests remain for LLM input |
| 4 | New fixtures with richer input data; evaluate output quality manually |
| 5 | Same as Phase 1 (remove field + assertion), plus verify conventions pointer in Quick Links |

### Rollback

Each phase is a standard code change. If a phase causes issues, revert the
commit. The next `lexictl update` will regenerate START_HERE with the previous
format.

---

## Reconciliation with `agent-start-plan.md`

### What `agent-start-plan.md` proposes

The plan proposes using `SessionStart` and `SubagentStart` Claude Code hooks to
deterministically inject context into agent sessions. Specifically:

1. **Hook script** (`.claude/hooks/inject-blueprints.sh`): reads
   `blueprints/HANDOFF.md` and injects it as `additionalContext`.
2. **Conditional filtering**: skips injection for non-coding agents (Explore,
   Plan, etc.).
3. **Removes CLAUDE.md instruction**: "Read blueprints/START_HERE.md" becomes
   unnecessary since the hook injects the context.

### Overlap analysis

| Aspect | Dismantling Plan | Agent Start Plan | Conflict? |
|--------|-----------------|-----------------|-----------|
| What START_HERE contains | Restructures sections | Does not change content | No |
| How agents receive context | Via `lexictl update` regeneration | Via SessionStart hook injection | No |
| Navigation Protocol | Removes from START_HERE (already in agent rules) | Does not address | No |
| Ontology | Replaces with pointer | Does not address | No |
| Context delivery mechanism | File on disk (`START_HERE.md`) | Hook injection (`additionalContext`) | Complementary |
| Scope | All Lexibrary-managed projects | Lexibrary's own repo only (blueprints) | Different |

### Key distinction

The dismantling plan restructures the *generated* `.lexibrary/START_HERE.md`
that Lexibrary produces for **any** project. It changes what the archivist
pipeline outputs.

The agent-start-plan hooks inject Lexibrary's **own** hand-maintained
`blueprints/START_HERE.md` and `blueprints/HANDOFF.md` into agent sessions
working **on the Lexibrary codebase itself**. This is a project-specific
developer workflow concern, not a product feature.

### What from `agent-start-plan.md` is still relevant?

1. **The hook mechanism pattern** -- `SessionStart` and `SubagentStart` hooks
   for context injection are valuable and could be generalized into the agent
   rule template system. Worth extracting into a separate plan.
2. **Conditional filtering by agent type** -- the allowlist/blocklist approach
   for which agents receive injection is well-thought-out and reusable.
3. **Context budget analysis** -- the tiered approach (15 lines vs 50 lines vs
   full file) is a useful framework for any context injection.

### What is superseded?

1. **The specific HANDOFF.md injection** -- this is a Lexibrary-internal
   developer workflow. It should be tracked as a Lexibrary repo configuration
   task, not a product plan.
2. **"Remove blueprints instruction from CLAUDE.md"** -- this is a
   Lexibrary-internal CLAUDE.md edit, not a product change.
3. **The framing as a START_HERE delivery mechanism** -- the agent-start-plan
   treats hook injection as an alternative to agents reading START_HERE. After
   dismantling, START_HERE will be slim enough (~300 tokens) that direct reading
   is fine. The hook injection adds complexity without proportional benefit.

### Recommendation

**Mark `plans/agent-start-plan.md` as superseded by this plan.** Add a note at
the top of `agent-start-plan.md`:

```markdown
> **Status**: Superseded by `plans/start-here-dismantling.md`.
> The hook mechanism pattern (SessionStart/SubagentStart context injection) is
> still valuable -- extract into a future `plans/hook-based-context-injection.md`
> if/when needed for the agent rule template system.
```

---

## Files Affected (Complete List Across All Phases)

### Phase 1 (Remove Navigation Protocol)

| File | Change |
|------|--------|
| `baml_src/types.baml:40` | Remove `navigation_protocol string` |
| `baml_src/archivist_start_here.baml:46-48` | Remove prompt instruction 5 |
| `src/lexibrary/baml_client/types.py:77` | Auto-regenerated (loses field) |
| `src/lexibrary/baml_client/async_client.py` | Auto-regenerated |
| `src/lexibrary/archivist/start_here.py:87-119` | Remove param + section from `_assemble_start_here()` |
| `src/lexibrary/archivist/start_here.py:195-201` | Remove from `generate_start_here()` call |
| `tests/test_archivist/test_start_here.py:52-60` | Remove from `_make_sample_output()` |
| `tests/test_archivist/test_start_here.py:222` | Remove assertion |
| `openspec/specs/start-here-generation/spec.md:20` | Update section list |
| `docs/agent/orientation.md:19` | Remove bullet |

### Phase 2 (Replace Ontology with Pointer)

| File | Change |
|------|--------|
| `baml_src/types.baml:36` | Remove `ontology string` |
| `baml_src/archivist_start_here.baml:31-33` | Remove prompt instruction 2, renumber |
| `src/lexibrary/baml_client/types.py:74` | Auto-regenerated |
| `src/lexibrary/baml_client/async_client.py` | Auto-regenerated |
| `src/lexibrary/archivist/start_here.py:87-119` | Replace ontology param with pointer block |
| `src/lexibrary/archivist/start_here.py:195-201` | Remove from call |
| `tests/test_archivist/test_start_here.py:52-60` | Remove from mock |
| `tests/test_archivist/test_start_here.py:219` | Replace assertion |
| `openspec/specs/start-here-generation/spec.md:20` | Update section list |
| `docs/agent/orientation.md:16` | Replace bullet |

### Phase 3 (Make Topology Procedural)

| File | Change |
|------|--------|
| `baml_src/types.baml:36` | Remove `topology string` |
| `baml_src/archivist_start_here.baml:28-30` | Remove prompt instruction 1, renumber |
| `src/lexibrary/baml_client/types.py:73` | Auto-regenerated |
| `src/lexibrary/baml_client/async_client.py` | Auto-regenerated |
| `src/lexibrary/archivist/start_here.py` | Add `_build_procedural_topology()` (~60 lines) |
| `src/lexibrary/archivist/start_here.py:87-119` | Replace topology param with procedural arg |
| `src/lexibrary/archivist/start_here.py:131-218` | Restructure `generate_start_here()` |
| `src/lexibrary/config/schema.py:95` | Lower `start_here_tokens` from 800 to 600 |
| `tests/test_archivist/test_start_here.py:52-60` | Remove topology from mock |
| `tests/test_archivist/test_start_here.py` | Add `TestBuildProceduralTopology` class |
| `openspec/specs/start-here-generation/spec.md` | Update pipeline description |
| `docs/agent/orientation.md:15` | Update topology description |

### Phase 4 (Enrich Navigation by Intent) -- blocked

| File | Change |
|------|--------|
| `src/lexibrary/archivist/start_here.py` | New collection functions |
| `src/lexibrary/archivist/service.py:45-51` | New fields on `StartHereRequest` |
| `baml_src/archivist_start_here.baml` | Enriched prompt |
| `tests/test_archivist/test_start_here.py` | Richer fixtures |

### Phase 5 (Remove Convention Index) -- blocked

| File | Change |
|------|--------|
| `baml_src/types.baml` | Remove `convention_index string` |
| `baml_src/archivist_start_here.baml` | Remove convention instruction |
| `src/lexibrary/archivist/start_here.py` | Remove from assembly, expand Quick Links |
| `tests/test_archivist/test_start_here.py` | Remove convention assertions |
| `docs/agent/orientation.md:18` | Remove "Key constraints" bullet |

### Cross-Phase

| File | Change |
|------|--------|
| `src/lexibrary/validator/checks.py:375-405` | Lower token budget threshold after Phase 3 |
| `plans/agent-start-plan.md` | Mark as superseded |
