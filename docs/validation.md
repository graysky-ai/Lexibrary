# Validation

This guide explains how `lexictl validate` works -- the 13 checks it runs, how they are grouped by severity, and how to use the command in CI pipelines.

## Overview

`lexictl validate` runs a suite of consistency checks against your `.lexibrary/` directory and reports issues grouped by severity. It verifies that design files are fresh, wikilinks resolve, file references exist, concepts have valid frontmatter, token budgets are respected, and the link graph is consistent.

```bash
lexictl validate
```

## Severity Levels

Issues are classified into three severity levels:

| Severity | Symbol | Meaning |
|---|---|---|
| **error** | X (red) | Broken references or invalid data that should be fixed |
| **warning** | ! (yellow) | Stale data or budget overruns that may need attention |
| **info** | i (blue) | Suggestions for improvement that are not urgent |

## The 13 Checks

### Error-Severity Checks

These checks identify broken references and invalid data.

#### `wikilink_resolution`

Parses all design files and Stack posts for `[[wikilink]]` references and verifies that each one resolves to an existing concept. Uses the `WikilinkResolver` which checks concept titles and aliases (case-insensitive). When a wikilink does not resolve, the check includes fuzzy-match suggestions.

**What it scans:**
- Design file `wikilinks` fields
- Stack post bodies (inline `[[wikilink]]` patterns)
- Stack post `refs.concepts` frontmatter entries

**Example issue:**
```
wikilink_resolution | .lexibrary/src/auth/service.py.md | [[auth-middleware]] does not resolve | Did you mean [[authentication-middleware]]?
```

#### `file_existence`

Verifies that source files and cross-references actually exist on disk.

**What it checks:**
- Design file `source_path` fields -- the source file the design file describes must exist.
- Stack post `refs.files` entries -- referenced source files must exist.
- Stack post `refs.designs` entries -- referenced design files must exist.

**Example issue:**
```
file_existence | .lexibrary/src/old_module.py.md | Source file src/old_module.py does not exist | Remove the design file or restore the source file.
```

#### `concept_frontmatter`

Validates that every concept file in `.lexibrary/concepts/` has valid YAML frontmatter with all mandatory fields.

**Mandatory fields:** `title`, `aliases`, `tags`, `status`

**Valid status values:** `draft`, `active`, `deprecated`

**What it checks:**
- Frontmatter block exists (delimited by `---`)
- YAML parses without errors
- Frontmatter is a key-value mapping (not a list or scalar)
- All four mandatory fields are present
- `status` value is one of the three valid options

### Warning-Severity Checks

These checks identify data that is stale or exceeds budgets.

#### `hash_freshness`

Compares the `source_hash` stored in each design file's metadata footer against the current SHA-256 hash of the source file. A mismatch means the source file has changed since the design file was last generated.

**Example issue:**
```
hash_freshness | src/auth/service.py.md | Design file is stale: source_hash mismatch (stored a1b2c3d4e5f6... vs current 7890abcdef01...) | Run `lexictl update` to regenerate the design file.
```

#### `token_budgets`

Checks that generated artifacts stay within their configured token budgets. Uses an approximate tokenizer (characters / 4) for fast, dependency-free counting.

**Artifacts checked and their default budgets:**

| Artifact | Config Key | Default |
|---|---|---|
| `START_HERE.md` | `token_budgets.start_here_tokens` | 800 |
| Design files | `token_budgets.design_file_tokens` | 400 |
| Concept files | `token_budgets.concept_file_tokens` | 400 |
| `.aindex` files | `token_budgets.aindex_tokens` | 200 |

**Example issue:**
```
token_budgets | src/auth/service.py.md | Over budget: 520 tokens (limit 400) | Trim content to stay within the token budget.
```

#### `orphan_concepts`

Identifies concepts that have zero inbound wikilink references from any artifact. A concept with no references may be unused and could be removed, or may need to be linked from relevant design files.

**What it scans for references:**
- Design file bodies (all `.md` files under `.lexibrary/src/`)
- Stack post bodies
- Other concept files (cross-references)

The check considers both the concept's title and all its aliases when determining whether the concept is referenced.

#### `deprecated_concept_usage`

Finds wikilinks that point to concepts with `status: deprecated`. These references should be updated to point to the concept's replacement (if `superseded_by` is set) or removed.

**Example issue:**
```
deprecated_concept_usage | src/auth/middleware.py.md | References deprecated concept [[old-auth-pattern]]. | Replace with [[new-auth-pattern]]
```

### Info-Severity Checks

These checks provide suggestions for improvement.

#### `forward_dependencies`

Verifies that dependency targets listed in design file `## Dependencies` sections exist on disk. Missing targets indicate the dependency list is out of date.

#### `stack_staleness`

Flags Stack posts whose `refs.files` entries point to source files with stale design files (source hash mismatch). This is a heuristic -- the source change may not affect the post's relevance, but it signals that the solution should be reviewed.

#### `aindex_coverage`

Walks the `scope_root` directory tree and checks that each directory has a corresponding `.aindex` file in `.lexibrary/`. Directories without `.aindex` files are not indexed and will not appear in agent routing. Skips hidden directories, `.lexibrary/` itself, `node_modules/`, `__pycache__/`, `venv/`, and `.venv/`.

#### `bidirectional_deps`

Compares design file dependency lists against `ast_import` links in the link graph index. Reports mismatches in either direction:

- A dependency listed in the design file but not found as an `ast_import` link in the graph.
- An `ast_import` link in the graph that is not listed in the design file dependencies.

Returns no issues when the link graph index is absent, corrupt, or has a schema version mismatch (graceful degradation).

#### `dangling_links`

Detects artifacts in the link graph index whose backing files no longer exist on disk. Checks artifacts of kind `source`, `design`, `concept`, and `stack` (convention artifacts use synthetic paths and are skipped). Returns no issues when the index is absent or has a schema mismatch.

#### `orphan_artifacts`

Similar to `dangling_links`, detects link graph index entries for all non-convention artifacts whose backing files have been deleted. Suggests running `lexictl update` to rebuild the index.

## Running a Single Check

To run only one specific check:

```bash
lexictl validate --check hash_freshness
```

This is useful when you want to focus on a particular concern without running the full suite.

## Filtering by Severity

To show only issues at a specific severity level or above:

```bash
# Show only errors
lexictl validate --severity error

# Show errors and warnings (skip info)
lexictl validate --severity warning
```

## JSON Output

For programmatic consumption (CI pipelines, monitoring):

```bash
lexictl validate --json
```

This outputs a JSON object with two keys:

```json
{
  "issues": [
    {
      "severity": "error",
      "check": "wikilink_resolution",
      "message": "[[auth-middleware]] does not resolve",
      "artifact": ".lexibrary/src/auth/service.py.md",
      "suggestion": "Did you mean [[authentication-middleware]]?"
    }
  ],
  "summary": {
    "error_count": 1,
    "warning_count": 3,
    "info_count": 5,
    "total": 9
  }
}
```

## Exit Codes

`lexictl validate` uses exit codes to signal the result:

| Exit Code | Meaning |
|---|---|
| `0` | No issues found (clean) |
| `1` | Error-severity issues found |
| `2` | Warning-severity issues found (no errors) |

This makes it straightforward to use as a CI gate:

```bash
lexictl validate || exit 1
```

## Rich Console Output

When not using `--json`, validation results are rendered as a Rich table grouped by severity. Each severity group shows the check name, affected artifact, message, and suggestion. A summary line at the end shows total counts per severity.

## Related Documentation

- [Configuration](configuration.md) -- `token_budgets` settings that affect the `token_budgets` check
- [Design Files](design-files.md) -- How design files are created and when hashes become stale
- [Concepts](concepts.md) -- Concept frontmatter requirements checked by `concept_frontmatter`
- [Link Graph](link-graph.md) -- The index queried by `bidirectional_deps`, `dangling_links`, and `orphan_artifacts`
- [CI Integration](ci-integration.md) -- Using `lexictl validate` as a CI gate
