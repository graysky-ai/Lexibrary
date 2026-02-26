# Conventions v2 — Deferred Items

> **Status**: Backlog. These items were explicitly deferred from the v1
> conventions plan (`plans/conventions-artifact.md`) to be tackled after
> the v1 storage model, retrieval pipeline, and CLI are proven in use.
>
> **Prerequisite**: Conventions v1 must be fully implemented and exercised
> before starting any v2 item.

---

## 1. Pattern-Based Scopes (deferred from D7)

### What

Allow convention `scope` fields to contain glob patterns in addition to
directory paths. Examples:

```yaml
scope: "*_test.py"           # all test files, any directory
scope: "src/**/*.ts"         # all TypeScript files under src/
scope: "tests/**/conftest.py" # all conftest files
```

### Why deferred

Pattern scopes introduce the hardest algorithmic problem in the
conventions system: **specificity ranking between directories and globs**.
Given a file `src/auth/test_login.py`, is `src/auth/` more specific than
`*_test.py`? There is no natural ordering, and the answer depends on
user intent.

v1 uses `project` and directory-path scopes only. The `scope` field is
a string, so pattern support is a non-breaking extension.

### Design considerations

- **Matching engine**: Use `pathspec` (already a dependency) with
  `"gitignore"` pattern name, or `fnmatch` from stdlib. `pathspec` is
  more powerful but heavier; `fnmatch` is simpler but lacks `**` support.
- **Specificity ranking**: When both a directory scope and a pattern scope
  match, which takes precedence? Options:
  - Pattern conventions always rank after directory conventions within the
    same display priority
  - Explicit `specificity` field in frontmatter
  - Heuristic: longer/more specific patterns rank higher
- **Performance**: Every convention with a pattern scope must be tested
  against the file path. With 200 conventions, this is O(n) per lookup.
  Consider a two-tier index: directory-scoped conventions use prefix
  matching (fast); pattern-scoped conventions use full glob matching
  (slower, tested only after directory matches are collected).
- **Display**: Pattern-scoped conventions should indicate their scope
  in `lexi lookup` output (e.g., `[*_test.py]` prefix).

### Implementation sketch

1. Extend `ConventionIndex.find_by_scope()` with a second pass:
   after collecting directory-hierarchy matches, iterate all
   pattern-scoped conventions and test each against the file path.
2. Pattern conventions slot in after all directory conventions of the
   same or lower priority.
3. Add `scope_type: Literal["project", "directory", "pattern"]` as a
   derived field on `ConventionFile` (inferred from the scope string
   at parse time — contains glob chars → pattern, else directory).
4. Update the link graph `conventions` table with a `scope_type` column.
5. Add validator check: `check_convention_pattern_validity()` — ensure
   pattern scopes are valid glob syntax.

---

## 2. LLM-Extracted Conventions via Archivist (deferred from D4 / OQ1)

### What

During the archivist pipeline (design file generation), the LLM reads
source code. A secondary extraction step identifies conventions:

1. After generating design files for all files in a directory, a new
   BAML prompt synthesizes the directory's conventions from the code.
2. Extracted conventions are scoped to the directory and written as
   convention files with `source: archivist`, `status: draft`.
3. The sign-off config (`artifact_review.conventions`) controls whether
   these are auto-promoted to `active` or left for human review.

### Why deferred

- v1 relies on coding agents creating conventions via `lexi convention new`
  as the primary discovery mechanism. The archivist is a **backup** for
  conventions that agents miss.
- The extraction prompt (OQ1) needs design work: what inputs, what output
  schema, how to filter unhelpful conventions.
- Auto sign-off via LLM-as-judge needs criteria definition.

### Design considerations

- **BAML prompt** (`archivist_extract_conventions.baml`): Receives the
  design files for a directory + the source code for all files in that
  directory. Outputs a list of `{title, body, tags}` tuples.
- **Input filtering**: Only run extraction on directories with 3+ source
  files (single-file directories rarely have meaningful conventions).
- **Quality filter**: The extraction prompt should produce conventions that
  are:
  - Concrete and verifiable (not "follow best practices")
  - Specific to this codebase (not generic language conventions)
  - Not duplicating existing conventions (receive parent-scope conventions
    as context to avoid repetition)
- **Deduplication**: Before writing a new convention file, check if a
  convention with similar body text already exists (fuzzy match on rule
  paragraph).
- **LLM-as-judge auto sign-off**: A second LLM call evaluates each
  extracted convention against criteria:
  - Is it specific enough to be actionable?
  - Is it supported by evidence in the source code?
  - Does it conflict with existing active conventions?
  If all pass → `status: active`. Otherwise → `status: draft`.

### `artifact_review` config (deferred from OQ2)

```yaml
# .lexibrary/config.yaml
artifact_review:
  conventions: manual    # or "auto" — default is "manual"
  concepts: manual       # extensible to other artifact types
```

- `manual`: All archivist-extracted conventions start as `draft`.
- `auto`: LLM-as-judge evaluates and promotes to `active` if passing.

This config pattern should be **extensible to all artifact types** in
future (concepts, Stack posts, design files).

---

## 3. Convention Staleness Detection

### What

Detect conventions that reference patterns no longer present in the
codebase. Example: a convention says "all handlers use `@require_auth`
decorator" but the decorator was renamed to `@auth_required`.

### Design considerations

- **Approach**: During validation, scan active conventions for code
  patterns (backtick-delimited identifiers) and check if those patterns
  exist in the source files under the convention's scope.
- **Limitations**: Not all conventions reference specific code patterns.
  Rules like "prefer composition over inheritance" cannot be staleness-
  checked. Only conventions with explicit identifiers are candidates.
- **Severity**: Warning, not error. Stale conventions may still be
  intentional (aspirational rules).

---

## 4. Convention Conflict Detection (enhancement of D6)

### What

The v1 validator flags conflicts as warnings (D6). v2 enhances this with:

- **Semantic conflict detection**: Use LLM to compare conventions across
  scopes and identify contradictions (not just keyword overlap).
- **`overrides` frontmatter field**: Explicit declaration that a
  child-scope convention overrides a parent-scope convention. Suppresses
  the conflict warning.
- **Conflict resolution report**: `lexi conventions --conflicts` shows
  all detected conflicts with scope context.

---

## 5. Convention Analytics

### What

Usage metrics to help users understand their conventions landscape:

- `lexi conventions --stats`: Count by scope, status, source, tag.
- Coverage report: Which directories have conventions? Which are bare?
- Convention density: Average conventions per directory at each depth.

---

## Sequencing

| Item | Prerequisite | Priority |
|------|-------------|----------|
| Pattern-based scopes | v1 proven, usage data | High |
| Archivist extraction | v1 proven, BAML prompt design | High |
| Staleness detection | v1 proven | Medium |
| Conflict detection (enhanced) | v1 proven | Medium |
| Analytics | v1 proven | Low |

Pattern-based scopes and archivist extraction can be implemented in
parallel. Both should wait until v1 has been used on at least 2-3
real projects to validate the scope model and identify missing
conventions that the archivist could catch.
