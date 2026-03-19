# Topology Update Plan

## Problem

The current `TOPOLOGY.md` is nearly useless for agent navigation:

```
src/ -- Directory containing binary and data files.
  lexibrary/ -- Directory containing Python source files.  (10 subdirs)
    artifacts/ -- Directory containing binary and data files.
    cli/ -- Directory containing Python source files.
```

**Root causes:**
1. **Billboard descriptions are heuristic garbage.** The `_generate_billboard()` function in `generator.py` pattern-matches for `" source ("` in entry descriptions. When entries have design-file frontmatter descriptions (which don't contain that pattern), everything falls through to "Directory containing binary and data files." This is the #1 problem.
2. **No structural context.** A naive agent sees a tree of names with no understanding of what the project is, how directories relate, or where to start.
3. **No landmark files.** An agent can't tell which directories contain entry points, configs, or important modules without exploring each one.
4. **Rigid depth thresholds.** The 10/40 directory thresholds are arbitrary and don't account for directory importance.
5. **Directory entry descriptions are opaque.** `_get_dir_description()` generates descriptions like "Contains 8 files, 2 subdirectories" for subdirectory entries in a parent's `.aindex`. The child directory's billboard (which already summarizes its contents) is available but ignored.

**Important implementation note:** `_get_file_description()` in `generator.py` *already* pulls design-file frontmatter descriptions into `AIndexEntry.description`. The rich data is already present in the entries list passed to `_generate_billboard()` — the function just doesn't use it. No new data plumbing is needed for Phase 1.

## Design Goal

**TOPOLOGY.md should be the single file that bootstraps a naive agent's mental model of any project.** After reading it, an agent should be able to:
- Understand what the project is and what language/framework it uses
- Know where to look for any given concern (CLI, tests, config, core logic)
- Decide which directories to explore without trial and error
- Understand structural patterns (e.g. "tests/ mirrors src/")

---

## Phase 1: Fix Billboard Generation (the biggest lever)

**Files:** `src/lexibrary/indexer/generator.py`, `tests/test_indexer/test_generator.py`

**Depends on:** Nothing (self-contained).

### 1a. Rewrite `_generate_billboard()`

**Current approach:** Pattern-match `" source ("` in entry descriptions → language detection → generic template.

**New approach:** Three-tier fallback:

```python
def _generate_billboard(entries: list[AIndexEntry]) -> str:
    if not entries:
        return "Empty directory."

    # Tier 1: Synthesize from rich (design-file) descriptions
    rich_descriptions = [
        e.description for e in entries
        if e.entry_type == "file" and not _is_structural_description(e.description)
    ]
    if rich_descriptions:
        return _synthesize_summary(rich_descriptions)

    # Tier 2: Extension-based summary with counts
    extensions = Counter(
        Path(e.name).suffix for e in entries if e.entry_type == "file"
    )
    if extensions:
        return _extension_based_summary(extensions, len(entries))

    # Tier 3: Pure count fallback
    file_count = sum(1 for e in entries if e.entry_type == "file")
    dir_count = sum(1 for e in entries if e.entry_type == "dir")
    parts = []
    if file_count:
        parts.append(f"{file_count} files")
    if dir_count:
        parts.append(f"{dir_count} subdirectories")
    return ", ".join(parts) if parts else "Empty directory."
```

### 1b. Define `_is_structural_description()`

A description is "structural" (i.e., not from a design file) if it matches any of these patterns. These are the exact formats produced by `_get_structural_description()`, `_get_dir_description()`, and edge cases:

| Pattern | Example |
|---------|---------|
| `"{Language} source ({N} lines)"` | `"Python source (42 lines)"` |
| `"Binary file ({ext})"` | `"Binary file (.png)"` |
| `"Unknown file type"` | — |
| `"Contains {N} files"` | `"Contains 8 files"` |
| `"Contains {N} files, {M} subdirectories"` | `"Contains 8 files, 2 subdirectories"` |
| `"Contains {N} items"` | `"Contains 3 items"` |
| `"Empty directory."` | — |

**Implementation:** Regex match against these known patterns. This is safer than a blocklist of words because it's coupled to the exact output of the structural generators.

```python
_STRUCTURAL_PATTERNS = re.compile(
    r"^("
    r".+ source \(\d+ lines?\)|"        # "{Lang} source (N lines)"
    r"Binary file \(\.\w+\)|"           # "Binary file (.ext)"
    r"Unknown file type|"
    r"Contains \d+ (?:files|items).*|"  # "Contains N files[, M subdirectories]"
    r"Empty directory\."
    r")$"
)

def _is_structural_description(description: str) -> bool:
    return bool(_STRUCTURAL_PATTERNS.match(description))
```

### 1c. Implement `_synthesize_summary()` — Keyword-Frequency Fragment Selection

**Strategy:** Extract a short "role fragment" from each description, then use keyword frequency across all fragments to select the 3 most representative, avoiding redundancy via overlap deduplication.

**Why this approach:** Real design-file descriptions in this project follow consistent patterns ("Provides a tolerant parser for v2 .aindex artifact files so other parts..."). Files within the same directory naturally share domain vocabulary (e.g., `artifacts/` descriptions all mention "Pydantic", "models", "artifact", "parser"). Keyword frequency naturally surfaces the directory's central themes.

**Algorithm:**

**Step 1 — Extract role fragments** from each description:
1. Strip common leading verb phrases: `"Provides? (a|an|the)?"`, `"Acts? as (a|an|the)?"`, `"Defines?"`, `"Generates?"`, `"Coordinates?"`, `"This file (declares|provides) (a|an|the)?"`.
2. Truncate at the first subordinating clause marker: `" that "`, `" so "`, `" which "`, `" without "`, `" keeping "`, `" used by "`, `" used to "` — but only if the marker appears after at least 10 characters (to avoid over-truncation).
3. Cap at 8 words.
4. Strip trailing punctuation and filler.

**Example transformations from real data:**

| Input description | Extracted fragment |
|---|---|
| "Provides a tolerant parser for v2 .aindex artifact files so other parts..." | "tolerant parser for v2 .aindex artifact files" |
| "Acts as the single public entrypoint that aggregates and re-exports all Pydantic data models" | "single public entrypoint" |
| "Provides the canonical Pydantic schemas used by the AST-based extractor" | "canonical Pydantic schemas" |
| "Provides a small, thread-safe debounce utility that coalesces rapid filesystem..." | "small, thread-safe debounce utility" |
| "Coordinates the end-to-end process of producing .aindex artifacts" | "end-to-end process of producing .aindex artifacts" |

**Step 2 — Score fragments by keyword coverage:**
1. Tokenize each fragment: lowercase, extract `[a-zA-Z][a-zA-Z0-9_-]+` words, remove stop words (length ≤ 2, plus a curated set: common articles, prepositions, generic adjectives like "small", "stable", "simple", "single", "centralized", "lightweight", "reusable", "focused", "strict", "tolerant", and structural nouns like "function", "utility", "helper", "module", "package", "file").
2. Count keyword frequency across all fragments (each fragment contributes each keyword at most once — use `set()` before counting).
3. Score each fragment = sum of keyword counts for its words.

**Step 3 — Select top fragments with deduplication:**
1. Sort fragments by score descending.
2. Greedily select fragments: skip a fragment if >50% of its keywords overlap with already-selected fragments.
3. Stop at 3 selected fragments.

**Step 4 — Format:**
- Join selected fragments with `"; "`.
- Truncate to ~80 characters at a word boundary if needed.

**Short-circuit:** If ≤3 rich descriptions exist, join their fragments directly (skip scoring).

**Expected outputs for real directories:**

| Directory | Expected billboard |
|---|---|
| `artifacts/` | `"public entrypoint for Pydantic data models; parser for .aindex artifact files; design-file markdown artifacts"` (or similar) |
| `cli/` | `"CLI entry-points; plain-text output helpers; agent-facing Lexibrary operations"` |
| `ast_parser/` | `"public API for interface skeleton extraction; JavaScript/JSX AST walker; Pydantic schemas for AST extractor"` |
| `daemon/` | `"daemon package re-export; thread-safe debounce; watchdog-based event handler"` |
| `indexer/` | `"AIndexFile representation for a directory; end-to-end .aindex artifact production"` |

**Note:** These are approximate — the exact output depends on stop word tuning. The goal is "good enough to orient an agent," not "perfect English prose."

### 1d. Implement `_extension_based_summary()`

Tier 2 fallback when no rich descriptions exist. Replaces the old "Directory containing {lang} source files" with something slightly more informative:

```python
def _extension_based_summary(extensions: Counter, total_entries: int) -> str:
    lang_counts = {}
    for ext, count in extensions.items():
        lang = EXTENSION_MAP.get(ext)
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + count
    if not lang_counts:
        return f"{total_entries} entries"
    top = sorted(lang_counts.items(), key=lambda x: -x[1])
    if len(top) == 1:
        lang, count = top[0]
        return f"{count} {lang} files"
    parts = [f"{count} {lang}" for lang, count in top[:3]]
    return f"Mixed: {', '.join(parts)}"
```

### 1e. Fix `_get_dir_description()` (Oversight)

**Current:** Reads the child `.aindex` but only extracts file/dir counts → "Contains 8 files, 2 subdirectories".

**Problem:** The child's `.aindex` already has a `billboard` field that summarizes its contents. This billboard is ignored, producing opaque count-only descriptions for directory entries in the parent's `.aindex`.

**Fix:** Use the child's billboard as the directory entry description when it's available and non-structural:

```python
def _get_dir_description(subdir: Path, project_root: Path) -> str:
    mirror_aindex = aindex_path(project_root, subdir)
    child_aindex = parse_aindex(mirror_aindex)
    if child_aindex is not None:
        # Prefer the child's billboard if it's meaningful
        if child_aindex.billboard and not _is_structural_description(child_aindex.billboard):
            return child_aindex.billboard
        # Fall back to count-based description
        file_count = sum(1 for e in child_aindex.entries if e.entry_type == "file")
        dir_count = sum(1 for e in child_aindex.entries if e.entry_type == "dir")
        if dir_count:
            return f"Contains {file_count} files, {dir_count} subdirectories"
        return f"Contains {file_count} files"
    # Fallback: count direct children in the filesystem
    try:
        count = sum(1 for _ in subdir.iterdir())
    except OSError:
        count = 0
    return f"Contains {count} items"
```

**Ordering note:** This creates a dependency between billboard quality and directory descriptions. After Phase 1, billboards will be rich, so `_get_dir_description` will naturally produce richer output. However, on the first run after deployment, billboards may still be stale. The count fallback handles this.

### 1f. Tests (in-phase)

Add/update tests in `tests/test_indexer/test_generator.py`:

| Test class | Tests |
|---|---|
| `TestIsStructuralDescription` | Each known pattern matches; rich descriptions don't match; edge cases (empty string, partial matches) |
| `TestExtractRoleFragment` | Prefix stripping for each verb form; truncation at clause markers; 8-word cap; short descriptions pass through unchanged |
| `TestSynthesizeSummary` | ≤3 descriptions: direct join; >3 descriptions: keyword scoring selects most representative; overlap dedup works; result ≤80 chars; single description: returned as-is |
| `TestGenerateBillboard` (update existing) | Tier 1 with rich descriptions; Tier 2 with structural-only descriptions; Tier 3 count fallback; Mixed (some rich, some structural) — only rich used |
| `TestExtensionBasedSummary` | Single language; multiple languages; no recognized extensions |
| `TestGetDirDescription` (new) | Uses child billboard when available and non-structural; falls back to counts when billboard is structural; falls back to filesystem count when no child .aindex |

---

## Phase 2: Add Project Header Section

**Files:** `src/lexibrary/archivist/topology.py`, `tests/test_archivist/test_topology.py`

**Depends on:** Nothing (can run in parallel with Phase 1).

### 2a. Derive landmarks from descriptions (not a hardcoded table)

Instead of maintaining a language-specific landmark detection table, derive landmarks from the data already in `.aindex` entries. Files whose descriptions contain role-indicating keywords are self-documenting landmarks.

**Landmark detection keywords** (searched in `AIndexEntry.description`):

| Category | Keywords |
|---|---|
| Entry point | `"entry point"`, `"entry-point"`, `"main"` (in description, not filename), `"application entry"` |
| Test root | directory name matches `tests/`, `test/`, `__tests__/`, `spec/` |
| Config | `"configuration"`, `"config"`, `"settings"` in description; OR filename matches `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `setup.cfg` |

**Project name and language** are still derived from:
- **Name:** `project_root.name` (simple, no file parsing needed)
- **Language:** dominant file extension across all `.aindex` entries (already available via `_collect_aindex_data`)

### 2b. Modify `generate_topology()` to emit a header

Add a header section before the code-fenced tree:

```markdown
# Project Topology

**Lexibrarian** — Python (src/lexibrary/)
Entry: src/lexibrary/cli/lexi_app.py | Tests: tests/ | Config: pyproject.toml

```

**Implementation:** New function `_generate_header(infos: list[_DirInfo], project_root: Path) -> str` that:
1. Scans all `_DirInfo` objects and their entries for landmark keywords.
2. Detects dominant language from file extensions across all entries.
3. Formats the 2-line header.

**Data flow change:** `_collect_aindex_data` currently discards individual entries (only stores `child_entry_count` and `child_dir_names`). To scan entry descriptions for landmarks, either:
- **(A)** Extend `_DirInfo` to carry a list of key entries (entries matching landmark keywords). This is the cleaner approach — `_DirInfo` gains an optional `key_entries: list[AIndexEntry]` field populated during collection.
- **(B)** Do a second pass over `.aindex` files in `_generate_header`. Simpler but redundant I/O.

**Recommendation:** Option A — extend `_DirInfo`.

### 2c. Tests (in-phase)

| Test class | Tests |
|---|---|
| `TestGenerateHeader` | Detects entry points from descriptions; detects test roots from directory names; detects config files; formats header correctly; no landmarks found → minimal header (just name + language); multiple entry points → picks first |
| `TestCollectAindexData` (update) | Verify `key_entries` populated when landmark descriptions present; verify empty when no landmarks |
| `TestGenerateTopology` (update) | Header appears before tree; header omitted when no `.aindex` data |

---

## Phase 3: Improve Collapse Annotations

**Files:** `src/lexibrary/archivist/topology.py`, `tests/test_archivist/test_topology.py`

**Depends on:** Nothing (can run in parallel with Phases 1-2).

### 3a. Show hidden child names in collapse annotation

**Current:** `(8 subdirs)`

**New:** `(8 subdirs: commands, models, utils, ...)`

**Implementation:** In `_count_hidden_children`, also collect the names of hidden children. Show up to 4 names, append `"..."` if more exist.

```python
def _get_hidden_children_info(info: _DirInfo) -> tuple[int, list[str]]:
    """Return (count, names) of hidden child directories."""
    hidden_names = []
    for child_name in info.child_dir_names:
        child_path = ...  # build child path
        if child_path in info_by_path and not _should_show(child_path):
            hidden_names.append(child_name)
    return len(hidden_names), hidden_names

# In rendering:
count, names = _get_hidden_children_info(info)
if count > 0:
    preview = ", ".join(names[:4])
    if count > 4:
        preview += ", ..."
    suffix = f"  ({count} subdirs: {preview})"
```

### 3b. Add `>` marker for directories with hidden children

```
templates/ -- Jinja2 templates for generated artifacts  (7 subdirs: config, cli, ... >)
```

The `>` marker signals "there's more here" — useful for agents deciding where to explore deeper.

### 3c. Tests (in-phase)

| Test class | Tests |
|---|---|
| `TestCollapseAnnotation` | Names shown up to 4; ellipsis when >4 hidden; `>` marker present; no annotation when 0 hidden; names sorted alphabetically |

---

## Phase 4: Structural Patterns Section — DEFERRED

**Status:** Deferred to a follow-up initiative.

**Reasoning:**
1. **Highest complexity, lowest confidence.** Mirror-directory detection produces false positives (e.g., `utils/` appearing in both `src/` and `tests/` doesn't mean they mirror). Name matching requires nuance: does `test_topology.py` match `topology.py`? What about `test_archivist/test_topology.py` matching `archivist/topology.py`?
2. **"One-module-per-entity" detection** is indistinguishable from "directory that contains multiple files" without semantic analysis.
3. **Phases 1-3 deliver ~80% of the value.** Improved billboards + a project header + better collapse annotations will transform the topology. Patterns can be evaluated once we see how the improved topology reads in practice.
4. **Better as a separate, focused initiative** where detection heuristics can be iterated and validated against multiple real projects, not just the dogfood instance.

---

## Phase 5: Improve Adaptive Depth

**Files:** `src/lexibrary/archivist/topology.py`, `tests/test_archivist/test_topology.py`

**Depends on:** Phase 2 (needs landmark data from `_DirInfo.key_entries` for importance scoring). Can run after Phase 2 completes.

### 5a. Importance-weighted depth

**Current:** Fixed depth limits (None / 2 / 1) based on directory count. Hotspots (>5 children) always shown.

**New:** Keep the 3-tier base system but add an importance bonus:

```python
def _should_show(rel_path: str, info: _DirInfo | None = None) -> bool:
    depth = _compute_depth(rel_path, project_name)
    if display_depth is None:
        return True
    if depth <= display_depth:
        return True
    if rel_path in hotspot_paths:
        return True
    # Importance bonus: +1 depth for directories on path to landmarks
    if depth <= display_depth + 1 and rel_path in important_paths:
        return True
    return False
```

**`important_paths`** is the set of all directory paths that are ancestors of detected landmarks (entry points, test roots, config locations). Computed once from `_DirInfo.key_entries` data.

### 5b. Tune thresholds

Review the current thresholds (10/40) against real projects. May adjust to (15/50) or similar based on how the improved billboards affect readability at each tier.

### 5c. Tests (in-phase)

| Test class | Tests |
|---|---|
| `TestImportanceWeightedDepth` | Landmark ancestor shown at depth+1; non-landmark at depth+1 hidden; landmark detection propagates to parent dirs; works correctly at each tier (small/medium/large) |
| `TestBuildProceduralTopology` (update existing) | Update medium/large project tests to account for importance bonus behavior |

---

## Phase 6: Format Improvements

**Files:** `src/lexibrary/archivist/topology.py`, `tests/test_archivist/test_topology.py`

**Depends on:** Phases 3 and 5 (collapse annotations and depth improvements should be stable before formatting changes).

### 6a. Visual grouping

Add blank lines between top-level (depth 1) sections of the tree for scannability:

```
src/
  lexibrary/ -- AI-friendly codebase indexer

tests/ -- mirrors src/lexibrary/ structure

docs/ -- Project documentation
```

### 6b. Tests (in-phase)

| Test class | Tests |
|---|---|
| `TestFormatImprovements` | Blank lines between depth-1 sections; no blank lines within nested sections; single top-level section has no extra blank lines |

---

## Dependency Graph

```
Phase 1 (Billboard)  ──────────────────────┐
                                            ├──→ Phase 5 (Adaptive Depth)
Phase 2 (Header)     ──────────────────────┘         │
                                                      │
Phase 3 (Collapse)   ─────────────────────────────────┼──→ Phase 6 (Format)
                                                      │
Phase 4 (Patterns)   — DEFERRED                       │
```

**Parallelizable:** Phases 1, 2, and 3 are fully independent.
**Sequential:** Phase 5 requires Phase 2. Phase 6 requires Phases 3 and 5.

---

## Regeneration / Migration

After deploying Phase 1, all existing `.aindex` files will have stale billboards (the old "binary and data files" text). **A full reindex is required** to pick up the improved billboards:

```bash
lexi update
```

This should be called out in the PR/release notes. The `_get_dir_description` improvement (Phase 1e) also depends on child billboards being regenerated, so `lexi update` must process directories bottom-up (which it already does via the orchestrator).

---

## Files to Modify

| File | Phases | Changes |
|------|--------|---------|
| `src/lexibrary/indexer/generator.py` | 1 | Rewrite `_generate_billboard()`, add `_is_structural_description()`, `_extract_role_fragment()`, `_synthesize_summary()`, `_extension_based_summary()`. Fix `_get_dir_description()`. |
| `src/lexibrary/archivist/topology.py` | 2, 3, 5, 6 | Header generation, collapse annotations with names, importance-weighted depth, format improvements. Extend `_DirInfo`. |
| `src/lexibrary/artifacts/aindex.py` | — | No changes needed (models are sufficient) |
| `tests/test_indexer/test_generator.py` | 1 | Tests for all new billboard functions + `_get_dir_description` |
| `tests/test_archivist/test_topology.py` | 2, 3, 5, 6 | Tests for header, collapse, depth, format |

---

## What Good Looks Like

For this project, the topology should render something like:

```markdown
# Project Topology

**Lexibrarian** — Python (src/lexibrary/)
Entry: src/lexibrary/cli/lexi_app.py | Tests: tests/ | Config: pyproject.toml

src/
  lexibrary/ -- CLI entry-points; agent-facing operations; artifact models and parsers
    archivist/ -- design file and topology generation
    artifacts/ -- Pydantic data models; .aindex parser and serializer; design-file schemas
    ast_parser/ -- interface skeleton extraction; tree-sitter language parsers
    cli/ -- CLI entry-points; plain-text output; agent-facing operations
    config/ -- configuration schema and loading
    daemon/ -- thread-safe debounce; watchdog event handler; periodic sweep scheduler
    ignore/ -- gitignore-style file matching
    indexer/ -- AIndexFile generation; end-to-end indexing orchestration
    init/ -- project scaffolding; wizard; environment detection
      rules/ -- agent rule-file generators for Claude, Cursor, Codex
    iwh/ -- I Was Here signal creation and management
    lifecycle/ -- artifact staleness detection and cleanup
    llm/ -- LLM client registry; rate limiting; BAML service adapter
    playbooks/ -- (new) playbook execution engine
    search/ -- cross-artifact search
    stack/ -- Stack Q&A post management
    templates/ -- Jinja2 templates for generated artifacts  (7 subdirs: config, cli, concept, ... >)
    tokenizer/ -- token counting for LLM context budgeting
    utils/ -- shared path utilities; atomic writes; hashing
    validator/ -- library health checks and validation
    wiki/ -- wikilink resolution and cross-reference tracking

tests/ -- mirrors src/lexibrary/ structure
```

Compare this to the current output — a naive agent reading the improved version can immediately understand the project and navigate to the right area.

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `_synthesize_summary` produces poor summaries | Keyword-frequency approach tested against 5+ real directories in this project. Any summary > "binary and data files." Fragment extraction is deterministic and testable in isolation. |
| Billboard quality degrades for projects without design files | Tier 2 (extension-based) and Tier 3 (count) fallbacks ensure graceful degradation. Worst case is equivalent to current behavior. |
| `_get_dir_description` creates circular dependency with billboards | On first run, stale billboards may be structural → falls back to counts. Second `lexi update` resolves this naturally. |
| Topology gets too large for big projects | Adaptive depth already constrains this. Header and collapse add ~5-10 lines. Monitor in practice. |
| Stop word list needs tuning | Start with a conservative set. Easy to iterate — changes are isolated to `_synthesize_summary` internals. |
| Phase 2 `_DirInfo` extension breaks existing tests | `key_entries` field has a default (empty list). All existing tests pass without modification. |
