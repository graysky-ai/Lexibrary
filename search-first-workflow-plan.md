# Plan: Update Agent Rules — Search-First Workflow

## Context

During a recent session, the agent skipped `lexi search` and `lexi concept` checks before making changes, and nearly missed updating the design file afterward. The current rules are scattered across several sections and don't establish a clear "search first, then act" workflow. This update consolidates and strengthens the rules so agents consistently check existing knowledge before writing code.

A critical review surfaced several adjustments:

- `lexi view <ID>` was built to replace type-specific show commands — the rules should use it as the primary way to read non-design artifacts.
- For design files, agents should use `lexi lookup <file>` (which surfaces the linked design), not `lexi view`.
- The post-edit design step should leverage the pre-edit `lexi lookup` result rather than introducing a second lookup.
- `playbook` is a valid `--type` value in the search backend (`search.py:206`) but is blocked by the CLI validation set at `lexi_app.py:457`. This needs fixing.
- The CLI help text for `search` needs to mention multi-word queries, playbooks, and all valid types.
- Search results need an ID column so agents can use `lexi view <ID>` directly from results.
- The index-accelerated code paths (`_tag_search_from_index` and `_fts_search`) populate `_StackResult.post_id` with `hit.path` (a file path like `.lexibrary/stack/ST-042.md`) instead of `hit.artifact_code` (the short `ST-NNN` ID). The file-scanning fallback and direct ID resolution paths are already correct.
- FTS indexing does not include aliases or tags in the searchable body, causing the index-accelerated path to miss results that the file-scanning fallback would find. This needs fixing in the builder.
- The "non-trivial" qualifier is dropped — agents should search before starting work, period.
- The typo referenced in the earlier plan draft has already been fixed.

---

## Phase 1: Fix CLI search to support playbooks and update help text

**Goal:** Make the CLI consistent with the backend and improve discoverability.

### Task Group 1A: Add `playbook` to CLI `--type` validation

**File:** `src/lexibrary/cli/lexi_app.py`

1. Add `"playbook"` to `_VALID_ARTIFACT_TYPES` (line 457).
2. Update the `--type` option help string (line 472) to list all valid types:
   `"Restrict to artifact type: concept, convention, design, playbook, or stack."`
3. Update the `search` command docstring (line 507) to include playbooks:
   `"Search across concepts, conventions, design files, playbooks, and Stack posts."`

### Task Group 1B: Update search help to mention multi-word queries

**File:** `src/lexibrary/cli/lexi_app.py`

1. Update the `query` argument help text (line 465) to:
   `"Free-text search query. Use quotes for multi-word phrases (e.g. \"error handling\")."`

### Phase 1 Testing

```bash
# Playbook type now accepted
lexi search --type playbook
# Should list playbooks or return empty — must NOT error

# Multi-word search still works
lexi search "artifact type"
# Should return results

# Existing types still work
lexi search --type concept test
lexi search --type convention test
lexi search --type design test
lexi search --type stack test

# Invalid type still rejected
lexi search --type bogus test
# Should error with updated valid-types list including "playbook"

# Help text reflects changes
lexi search --help
# --type help should list all 5 types
# query help should mention multi-word phrases
```

**Dependencies:** None. This phase is independent.

---

## Phase 2: Add ID column to search results and fix index-accelerated paths

**Goal:** Every search result row includes the artifact's short ID (`CN-001`, `CV-003`, etc.) so agents can go straight to `lexi view <ID>`. Also fix the index-accelerated paths that incorrectly use file paths where short IDs are expected.

**Depends on:** None. Independent of Phase 1 (can run in parallel).

### Task Group 2A: Add `id` field to result dataclasses

**File:** `src/lexibrary/search.py`

Add an `id: str` field to each result dataclass that doesn't already have one:

| Dataclass | Current state | Change |
|-----------|--------------|--------|
| `_ConceptResult` (line 164) | No ID field | Add `id: str` |
| `_ConventionResult` (line 180) | No ID field | Add `id: str` |
| `_PlaybookResult` (line 198) | No ID field | Add `id: str` |
| `_DesignFileResult` (line 173) | No ID field | Add `id: str` |
| `_StackResult` (line 189) | Has `post_id: str` | Keep as-is (already serves as the ID field) |

### Task Group 2B: Populate ID fields in all construction sites

**File:** `src/lexibrary/search.py`

There are **three categories** of construction sites that need updating:

#### Category 1: File-scanning fallback functions

These construct results from parsed frontmatter. Add `id=<frontmatter>.id`:

1. `_search_concepts` (line 881): add `id=c.frontmatter.id` to `_ConceptResult(...)`.
2. `_search_conventions` (line 1109): add `id=c.frontmatter.id` to `_ConventionResult(...)`.
3. `_search_playbooks` (line 1179): add `id=pb.frontmatter.id` to `_PlaybookResult(...)`.
4. `_search_design_files` (line 954): add `id=design.frontmatter.id` to `_DesignFileResult(...)`.
5. `_search_stack_posts`: `post_id` is already populated from `frontmatter.id` — no change needed.

#### Category 2: Direct ID resolution helpers

These construct single results from parsed files. Add `id=<frontmatter>.id`:

1. `_resolve_concept_file` (line 281): add `id=concept.frontmatter.id`.
2. `_resolve_convention_file` (line 296): add `id=conv.frontmatter.id`.
3. `_resolve_playbook_file` (line 312): add `id=pb.frontmatter.id`.
4. `_resolve_design_by_id` (line 349 area): add `id=design.frontmatter.id` to the `_DesignFileResult`.
5. `_resolve_stack_file` (line 327): `post_id` already correct — no change needed.

#### Category 3: Index-accelerated paths (BUG FIX)

These construct results from `ArtifactResult` (`hit`) objects returned by the linkgraph. They must use `hit.artifact_code` (the short `XX-NNN` ID stored in the `artifacts.artifact_code` column) — **not** `hit.path`.

`hit.artifact_code` is available on `ArtifactResult` (defined at `linkgraph/query.py:47`) and is populated from `frontmatter.id` during linkgraph build.

**`_tag_search_from_index`** (line 617):
1. Concept construction (~line 670 area): add `id=hit.artifact_code or ""`.
2. Convention construction (~line 688 area): add `id=hit.artifact_code or ""`.
3. Design construction (line 701): add `id=hit.artifact_code or ""`.
4. **Stack construction (line 711): change `post_id=hit.path` to `post_id=hit.artifact_code or hit.path`**. This is the primary bug — stack results show file paths instead of `ST-NNN` IDs when the index-accelerated path is used.

**`_fts_search`** (line 727):
1. Concept construction (line 776): add `id=hit.artifact_code or ""`.
2. Convention construction (line 793): add `id=hit.artifact_code or ""`.
3. Design construction (line 803): add `id=hit.artifact_code or ""`.
4. **Stack construction (line 811): change `post_id=hit.path` to `post_id=hit.artifact_code or hit.path`**. Same bug as above.

Note: `hit.artifact_code` can be `None` for artifacts inserted before the `artifact_code` column was added. The `or ""` / `or hit.path` fallback handles this gracefully.

### Task Group 2C: Update table rendering to show ID column

**File:** `src/lexibrary/search.py`

#### Markdown rendering (`_render_markdown`, line 105)

Update each table's headers and row construction:

| Type | Current columns | New columns |
|------|----------------|-------------|
| Concepts | Name, Status, Tags, Summary | **ID**, Name, Status, Tags, Summary |
| Conventions | Title, Scope, Status, Rule, Tags | **ID**, Title, Scope, Status, Rule, Tags |
| Design Files | Source, Description, Tags | **ID**, Source, Description, Tags |
| Stack | ID (already present), Status, Votes, Title, Tags | No header change needed — already has ID column |
| Playbooks | Title, Status, Overview, Tags | **ID**, Title, Status, Overview, Tags |

#### JSON rendering (`_render_json`, line 51)

Add `"id"` and `"type"` fields to every record for unambiguous parsing:

```python
# Concepts
{"type": "concept", "id": c.id, "name": c.name, "tags": c.tags, "status": c.status}

# Conventions
{"type": "convention", "id": cv.id, "title": cv.title, "scope": cv.scope, "tags": cv.tags, "status": cv.status}

# Stack (already has "id" from post_id — just add "type")
{"type": "stack", "id": s.post_id, "title": s.title, "votes": s.votes, "tags": s.tags, "status": s.status}

# Designs
{"type": "design", "id": d.id, "source": d.source_path, "description": d.description, "tags": d.tags}

# Playbooks
{"type": "playbook", "id": pb.id, "title": pb.title, "status": pb.status, "tags": pb.tags, "overview": pb.overview}
```

#### Plain rendering (`_render_plain`, line 90)

Add the ID as the first field in each tab-separated line:

```python
# Concepts: id \t name \t tags \t status
info(f"{c.id}\t{c.name}\t{', '.join(c.tags)}\t{c.status}")

# Conventions: id \t title \t scope \t tags \t status
info(f"{cv.id}\t{cv.title}\t{cv.scope}\t{', '.join(cv.tags)}\t{cv.status}")

# Stack: already shows post_id first — no change needed

# Designs: id \t source_path \t description \t tags
info(f"{d.id}\t{d.source_path}\t{d.description}\t{', '.join(d.tags)}")

# Playbooks: id \t title \t status \t tags \t overview
info(f"{pb.id}\t{pb.title}\t{pb.status}\t{', '.join(pb.tags)}\t{pb.overview}")
```

### Phase 2 Testing

```bash
# Verify ID column appears in output
lexi search test
# Each section should have ID as the first column
# Concept rows: CN-NNN
# Convention rows: CV-NNN
# Design rows: DS-NNN
# Stack rows: ST-NNN (NOT file paths)

# Verify specific type searches show IDs
lexi search --type stack test
# ID column should show ST-002, ST-003, etc. — not file paths

# Verify JSON output includes IDs and type discriminator
lexi --format json search test
# Each result object should have "id" and "type" fields
# e.g. {"type": "concept", "id": "CN-001", "name": "...", ...}

# Verify view works with IDs from results
lexi search --type convention test
# Pick an ID from results, then:
lexi view CV-001   # (or whatever ID appears)
# Should display the full artifact

# Verify plain output includes IDs
lexi --format plain search test
# Each line should start with the short ID
```

**Dependencies:** None. This phase is independent of Phase 1.

---

## Phase 3: Include aliases and tags in FTS index body

**Goal:** Close the gap where the FTS-accelerated search path misses results that the file-scanning fallback would find. Currently, FTS indexes only `title` and `body` (summary + content). Aliases and tags are stored in separate tables but are not included in the FTS searchable text, so a query matching an alias or tag name won't surface the artifact via FTS.

**Depends on:** None. Independent of Phases 1 and 2 (can run in parallel with both).

### Background

The FTS5 virtual table `artifacts_fts` has two columns: `title` and `body` ([schema.py:138-142](src/lexibrary/linkgraph/schema.py#L138-L142)). The `body` column is assembled from artifact content parts during build and inserted via `_insert_fts(rowid, title, body)`.

Aliases are stored in the `aliases` table and are only available to concepts and conventions (the two types that have `frontmatter.aliases`). Tags are stored in the `tags` table and apply to all artifact types.

The fix: append aliases and tags to the `fts_body` string before calling `_insert_fts`. This means FTS queries will match on alias text and tag text, bringing FTS results in line with file-scanning fallback results.

### Which types have aliases?

| Type | Has `frontmatter.aliases`? | Builder inserts aliases? |
|------|---------------------------|-------------------------|
| Concept | Yes | Yes — `builder.py:467` (full) and `builder.py:1491` (incremental) |
| Convention | Yes | Yes — `builder.py:1066` (full) and `builder.py:1842` (incremental) |
| Playbook | Yes | Not currently inserted into `aliases` table (only concepts/conventions use `_insert_alias`) |
| Design | No | N/A |
| Stack | No | N/A |

Note: Playbooks have `frontmatter.aliases` on the model but the builder doesn't insert them into the `aliases` table. For FTS purposes we only need to include them in the `fts_body` — the `aliases` table is used for wikilink resolution, which is a separate concern.

### Task Group 3A: Add aliases to FTS body for concepts

**File:** `src/lexibrary/linkgraph/builder.py`

**Full build** (line 486-493 area):
```python
# Current:
# 6. FTS row -- body = summary + "\n" + body
fts_body_parts = []
if concept_file.summary:
    fts_body_parts.append(concept_file.summary)
if concept_file.body:
    fts_body_parts.append(concept_file.body)

# Add after body, before joining:
if concept_file.frontmatter.aliases:
    fts_body_parts.append(" ".join(concept_file.frontmatter.aliases))
if concept_file.frontmatter.tags:
    fts_body_parts.append(" ".join(concept_file.frontmatter.tags))
```

**Incremental build** (line 1510-1517 area): Apply the same change to the incremental `_update_concept` path.

### Task Group 3B: Add aliases to FTS body for conventions

**File:** `src/lexibrary/linkgraph/builder.py`

**Full build** (line 1052-1059 area):
```python
# Current:
# 4. FTS row -- body = rule + "\n" + body
fts_body_parts = []
if conv_file.rule:
    fts_body_parts.append(conv_file.rule)
if conv_file.body:
    fts_body_parts.append(conv_file.body)

# Add after body, before joining:
if conv_file.frontmatter.aliases:
    fts_body_parts.append(" ".join(conv_file.frontmatter.aliases))
if conv_file.frontmatter.tags:
    fts_body_parts.append(" ".join(conv_file.frontmatter.tags))
```

**Incremental build** (line 1828-1835 area): Apply the same change to the incremental `_update_convention` path.

### Task Group 3C: Add aliases to FTS body for playbooks

**File:** `src/lexibrary/linkgraph/builder.py`

Playbook FTS is not shown in the code excerpts above, but follows the same pattern. Locate the playbook FTS insertion in both full and incremental build paths and add:

```python
if playbook_file.frontmatter.aliases:
    fts_body_parts.append(" ".join(playbook_file.frontmatter.aliases))
if playbook_file.frontmatter.tags:
    fts_body_parts.append(" ".join(playbook_file.frontmatter.tags))
```

Note: Playbooks do not currently have a dedicated `_update_playbook` incremental path — check whether incremental playbook updates exist. If not, only the full build path needs updating.

### Task Group 3D: Add tags to FTS body for designs and stack posts

**File:** `src/lexibrary/linkgraph/builder.py`

Designs and stack posts don't have aliases but do have tags. Add tags to FTS body:

**Design files — full build** (line 806-813 area):
```python
# Add after interface_contract, before joining:
if design_file.tags:
    fts_body_parts.append(" ".join(design_file.tags))
```

**Design files — incremental builds** (line 1416-1422 area and line 1698-1705 area): Apply same change.

**Stack posts — full build** (line 914-926 area):
```python
# Add after findings, before joining:
if stack_post.frontmatter.tags:
    fts_body_parts.append(" ".join(stack_post.frontmatter.tags))
```

**Stack posts — incremental build** (line 1600-1612 area): Apply same change.

### Task Group 3E: Enrich FTS/tag search results with tags from linkgraph

The index-accelerated paths currently return empty tag lists (`tags=[]` in `_fts_search`, single-tag lists in `_tag_search_from_index`). While adding tags to the FTS body fixes *searchability*, the *display* of results still shows empty/incomplete tags.

**File:** `src/lexibrary/search.py`

After collecting hits in both `_fts_search` and `_tag_search_from_index`, batch-fetch tags for all hit IDs from the linkgraph:

1. Add a helper or use an existing linkgraph query to fetch tags for a list of artifact IDs. Check if `LinkGraph` already has a `get_tags_for_artifacts` method; if not, add one to `query.py`:

   ```python
   def get_tags_for_artifacts(self, artifact_ids: list[int]) -> dict[int, list[str]]:
       """Return {artifact_id: [tag, ...]} for the given IDs."""
       if not artifact_ids:
           return {}
       placeholders = ",".join("?" * len(artifact_ids))
       rows = self._conn.execute(
           f"SELECT artifact_id, tag FROM tags WHERE artifact_id IN ({placeholders})",
           artifact_ids,
       ).fetchall()
       result: dict[int, list[str]] = {}
       for aid, tag in rows:
           result.setdefault(aid, []).append(tag)
       return result
   ```

2. In `_fts_search`, after the `hits` loop, replace `tags=[]` with the actual tags from the batch query. This requires tracking which `hit.id` maps to which result entry (e.g. by building results in a dict keyed by `hit.id`, then converting to the list-based `SearchResults`).

3. In `_tag_search_from_index`, similarly replace the single-tag lists with full tag sets.

**Note:** This task group is optional for the MVP — the FTS body change (3A-3D) already fixes the *search miss* problem. This task fixes the *display accuracy* problem. If you want to defer this, add a note to the plan for a follow-up.

### Task Group 3F: Enrich FTS search results with votes for stack posts

The FTS and tag-search paths hardcode `votes=0` for stack results ([search.py:714](src/lexibrary/search.py#L714), [search.py:816](src/lexibrary/search.py#L816)). The votes field is not in the linkgraph schema, so enriching it would require either:

- (a) Adding a `votes` column to the `artifacts` table (schema change, requires version bump), or
- (b) Falling back to file parsing for stack results from the index path.

**Recommendation:** Defer this. The FTS path is meant to be fast; adding file I/O defeats the purpose. Votes are a display-only concern and `0` is acceptable for now. Note this as a known limitation.

### Phase 3 Testing

```bash
# Rebuild the linkgraph to pick up FTS body changes
lexictl update   # (user must run this — agents cannot run lexictl)

# Test alias search via FTS
# First, find a concept with aliases:
lexi view CN-001   # Check if it has aliases in frontmatter
# Then search for the alias:
lexi search "<alias-text>"
# Should find the concept — previously would have missed via FTS

# Test tag search via FTS
lexi search "some-tag-name"
# Should surface artifacts tagged with that tag

# Compare FTS vs file-scanning results
# (Temporarily disable linkgraph by renaming .lexibrary/linkgraph.db)
# Run same searches and verify result sets match

# Verify no regressions in normal search
lexi search test
lexi search --type concept test
lexi search --tag some-tag
```

**Dependencies:** None. This phase is independent and can run in parallel with Phases 1 and 2. However, testing requires a linkgraph rebuild (`lexictl update`).

---

## Phase 4: Update CLAUDE.md agent rules

**Goal:** Establish a clear search -> view/lookup -> edit -> update-design pipeline, making explicit when to use `lexi view` vs `lexi lookup`.

**Depends on:** Phase 1 (rules reference `--type playbook`), Phase 2 (rules tell agents to use IDs from search results).

### Task Group 4A: Add "Before Starting Work" section

**File:** `CLAUDE.md` — insert after "Session Start", before "Before Reading or Editing Files"

```markdown
## Before Starting Work

- Run `lexi search <keyword>` (or `lexi search "key phrase"`) before starting
  any task. This searches across all artifact types — concepts, conventions,
  designs, playbooks, and stack posts.
- Search results include an ID column. Use `lexi view <ID>` to read the
  full artifact for any non-design result (e.g. `lexi view CN-001`,
  `lexi view ST-042`, `lexi view CV-003`).
- For design file results, use `lexi lookup <source_file>` instead — this
  gives you the design content plus the file's role, dependencies, and
  known issues in one call.
- Use `lexi search --type <type>` when you need type-specific filtering
  (valid types: concept, convention, design, playbook, stack).
```

### Task Group 4B: Simplify "Architectural Decisions" and "Debugging" sections

**File:** `CLAUDE.md`

- **Architectural Decisions**: Reword to:
  ```markdown
  ## Architectural Decisions

  - If `lexi search` (run in "Before Starting Work") didn't surface relevant
    concepts, also try `lexi search --type concept <topic>` for narrower
    lookup. Use `lexi view <ID>` to read the full artifact.
  ```

- **Debugging and Problem Solving**: Reword to:
  ```markdown
  ## Debugging and Problem Solving

  - If `lexi search` (run in "Before Starting Work") didn't surface a
    solution, try `lexi search --type stack <query>` with more specific
    terms. Use `lexi view <ID>` to read the full post.
  - For complex research or investigation, delegate to the `lexi-research`
    subagent rather than doing extensive exploration inline.
  - After solving a non-trivial bug, run `lexi stack post` to document
    the problem and solution for future reference.
  ```

### Task Group 4C: Clarify design file workflow in "After Editing Files"

**File:** `CLAUDE.md`

Replace the existing design-file bullet with an explicit workflow that
leverages the pre-edit `lexi lookup` result:

```markdown
- After editing a source file under `src/`, check the `lexi lookup` output
  from your pre-edit step for a linked design file. If one exists:
  1. Re-read the design file to see current content.
  2. Update relevant sections (Interface Contract, Dependencies,
     Complexity Warning, Wikilinks, Tags) to reflect your changes.
  3. Set `updated_by: agent` in frontmatter if not already set.
  4. Do not regenerate the full design file.
```

### Phase 4 Testing — Dry-run scenario

Trace through a hypothetical task: "Add a `--verbose` flag to `lexi search`."

Expected agent workflow under the updated rules:

1. **Session Start** -> Read `.lexibrary/TOPOLOGY.md`.
2. **Before Starting Work** -> Run `lexi search "search command"`. Results show ID column. Agent sees `CN-005` (hypothetical concept) and runs `lexi view CN-005`. Also sees `DS-012` for `lexi_app.py` — agent notes the design exists but will use `lexi lookup` for it later.
3. **Before Reading or Editing Files** -> Run `lexi lookup src/lexibrary/cli/lexi_app.py`. Gets design content, dependencies, known issues.
4. **Edit** -> Add the `--verbose` flag to the search command.
5. **After Editing Files** -> Re-read the design file found in step 3. Update the Interface Contract section to document the new flag. Set `updated_by: agent`.
6. **Architectural Decisions** -> Already covered by the broad search in step 2. If the feature touched conventions, a narrower `lexi search --type concept` would have been run.

Verify: the updated CLAUDE.md rules guide the agent through every step above without gaps or redundant commands. Confirm the rules clearly distinguish when to use `lexi view <ID>` (concepts, conventions, playbooks, stack) vs `lexi lookup <file>` (designs).

---

## Phase 5: Update tests and design files

**Goal:** Keep tests and designs consistent with the code and rule changes.

**Depends on:** Phase 1 (playbook type support), Phase 2 (ID column changes), Phase 3 (FTS body changes).

### Task Group 5A: Update tests for playbook type support

**File:** `tests/test_cli/test_lexi.py` (or relevant search test file)

1. Add a test that `lexi search --type playbook` does not error.
2. Update any test that asserts the valid-types error message to include `playbook`.

### Task Group 5B: Update tests for ID column in search results

**File:** `tests/test_cli/test_lexi.py` (or relevant search test file)

1. Update any test that asserts search output format to expect the ID column.
2. Add a test that Stack search results show `ST-NNN` IDs, not file paths.
3. Add a test that JSON output includes `"type"` and `"id"` fields for all artifact types.

### Task Group 5C: Update tests for FTS alias/tag indexing

**File:** `tests/` (relevant linkgraph builder or search test file)

1. Add a test that building a concept with aliases includes alias text in the FTS body.
2. Add a test that FTS search for an alias term returns the owning concept.
3. Add a test that FTS search for a tag term returns the tagged artifact.
4. If Task Group 3E was implemented, add a test that FTS results include full tag lists (not empty).

### Task Group 5D: Update design files

Update design files for any modified source files (`lexi_app.py`, `search.py`, `builder.py`, `query.py`) to reflect the changes made in Phases 1, 2, and 3.

### Phase 5 Testing

```bash
uv run pytest tests/ -x -q
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/
```

---

## Summary of dependencies

```
Phase 1 (CLI: playbook type + help text)  ──┐
                                             │
Phase 2 (Search: ID columns + bug fix)  ────┼─► Phase 4 (CLAUDE.md rules)
                                             │        │
Phase 3 (FTS: aliases + tags in body)  ─────┘        ▼
                                              Phase 5 (tests + designs)
```

Phases 1, 2, and 3 are independent and can run in parallel.
Phase 4 depends on Phases 1 and 2 (rules reference `--type playbook` and ID-based workflow). Phase 4 does not depend on Phase 3.
Phase 5 depends on Phases 1, 2, and 3 for code tests, and on Phase 4 for completeness.

---

## Known limitations (deferred)

1. **FTS votes for stack posts:** The index-accelerated paths hardcode `votes=0` for stack results. Fixing this properly requires either a schema change (adding a `votes` column to `artifacts`) or file I/O in the FTS path. Deferred — votes are display-only.

2. **Playbook aliases not in `aliases` table:** Playbooks have `frontmatter.aliases` but the builder doesn't insert them into the `aliases` table (used for wikilink resolution). Phase 3 includes aliases in the FTS body for searchability, but wikilink resolution for playbook aliases remains unsupported.
