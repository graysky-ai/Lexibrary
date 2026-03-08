# Ignore Patterns

This guide explains how Lexibrary's ignore system works -- the pattern sources, their precedence, and how they affect file discovery during `lexictl update` and `lexictl index`.

## Overview

Lexibrary uses a layered ignore system to determine which files and directories to skip during indexing. Patterns come from four sources, checked in a specific order. Any match from any source causes the file to be excluded.

## Pattern Sources

### 1. Built-in Defaults (Config Patterns)

The `ignore.additional_patterns` config setting provides the base set of ignore patterns. The defaults are:

```yaml
ignore:
  additional_patterns:
    - ".lexibrary/TOPOLOGY.md"
    - ".lexibrary/**/*.md"
    - ".lexibrary/**/.aindex"
    - "node_modules/"
    - "__pycache__/"
    - ".git/"
    - ".venv/"
    - "venv/"
    - "*.lock"
```

These defaults ensure that Lexibrary's own output files are not re-indexed, and common dependency/build directories are excluded.

You can add to this list in `.lexibrary/config.yaml`:

```yaml
ignore:
  additional_patterns:
    # Keep the defaults (they are replaced, not appended):
    - ".lexibrary/TOPOLOGY.md"
    - ".lexibrary/**/*.md"
    - ".lexibrary/**/.aindex"
    - "node_modules/"
    - "__pycache__/"
    - ".git/"
    - ".venv/"
    - "venv/"
    - "*.lock"
    # Add your own:
    - "dist/"
    - "build/"
    - "*.min.js"
    - "vendor/"
```

Note: The `additional_patterns` list is a full replacement, not an append. When you customize it, include the defaults you want to keep.

### 2. `.gitignore` Integration

When `ignore.use_gitignore` is `true` (the default), Lexibrary reads `.gitignore` files from the project root and all subdirectories. The standard gitignore pattern format is used (via the `pathspec` library with the `"gitignore"` pattern name).

Multiple `.gitignore` files are supported -- each one is scoped to its directory. A pattern in `src/.gitignore` only applies to paths under `src/`.

To disable `.gitignore` integration:

```yaml
ignore:
  use_gitignore: false
```

### 3. `.lexignore` File

The `.lexignore` file at the project root provides Lexibrary-specific ignore patterns that do not belong in `.gitignore` (because you may want to track files in git but not index them with Lexibrary).

The file uses the same gitignore pattern format:

```
# .lexignore
# Files tracked in git but not indexed by Lexibrary

# Generated documentation
docs/api/generated/

# Large data files
data/*.csv
data/*.json

# Test fixtures
tests/fixtures/

# Third-party vendored code
vendor/
```

If `.lexignore` does not exist, this source is silently skipped.

### 4. Binary Extension Detection

Separately from pattern matching, Lexibrary skips files whose extensions are in the `crawl.binary_extensions` list. The default list includes:

- **Images:** `.png`, `.jpg`, `.jpeg`, `.gif`, `.ico`, `.svg`, `.webp`
- **Audio/Video:** `.mp3`, `.mp4`, `.wav`, `.ogg`, `.webm`
- **Fonts:** `.woff`, `.woff2`, `.ttf`, `.eot`
- **Archives:** `.zip`, `.tar`, `.gz`, `.bz2`, `.7z`, `.rar`
- **Documents:** `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`
- **Executables/Compiled:** `.exe`, `.dll`, `.so`, `.dylib`, `.pyc`, `.pyo`, `.class`, `.o`, `.obj`
- **Database:** `.sqlite`, `.db`

To add extensions:

```yaml
crawl:
  binary_extensions:
    # Include defaults (this list is a full replacement):
    - ".png"
    - ".jpg"
    # ... (include all defaults you want to keep)
    # Add your own:
    - ".parquet"
    - ".arrow"
```

## Pattern Precedence

When Lexibrary checks whether a file should be ignored, it evaluates sources in this order:

1. **Config patterns** (`ignore.additional_patterns`) -- Checked first because they are the cheapest to evaluate (compiled once at startup).
2. **`.gitignore` patterns** -- Checked in reverse directory order (most specific subdirectory first), so a `.gitignore` in a subdirectory takes precedence.
3. **`.lexignore` patterns** -- Checked last.

A match at **any** level causes the file to be excluded. There is no negation across sources -- a file ignored by `.gitignore` cannot be un-ignored by `.lexignore`.

### Evaluation Flow

```
Is the file matched by config patterns?
  --> Yes: IGNORED
  --> No: Is the file matched by any .gitignore?
    --> Yes: IGNORED
    --> No: Is the file matched by .lexignore?
      --> Yes: IGNORED
      --> No: FILE IS INDEXED
```

Binary extension checking happens separately and earlier in the pipeline, before pattern matching.

## How Patterns Affect File Discovery

### During `lexictl update`

The full project update discovers files by recursively scanning `scope_root`. For each file:

1. Binary extension check -- skip if the extension is in `crawl.binary_extensions`.
2. Ignore pattern check -- skip if matched by any ignore source.
3. File size check -- skip if larger than `crawl.max_file_size_kb`.
4. `.lexibrary/` contents are always skipped (hard-coded, not pattern-based).

### During `lexictl update --changed-only`

The changed-only mode processes only the specified file paths, but still applies:

1. Binary extension check.
2. Ignore pattern check.
3. `.lexibrary/` contents check.

Files that do not pass these checks are silently skipped.

### During `lexictl index`

The `lexictl index` command (for indexing directories) applies the same ignore matching when discovering files.

### Directory Descent Optimization

The `IgnoreMatcher` also provides a `should_descend()` method that allows the crawler to skip entire directory trees without traversing their contents. If a directory matches an ignore pattern, none of its children are examined.

## Pattern Format

All pattern sources use the gitignore pattern format (via the `pathspec` library):

| Pattern | Matches |
|---|---|
| `*.log` | All `.log` files in any directory |
| `build/` | The `build` directory and all its contents |
| `/dist/` | Only the `dist` directory at the root |
| `**/*.min.js` | All `.min.js` files in any nested directory |
| `!important.log` | Negation -- un-ignores `important.log` (within the same source) |
| `docs/*.md` | `.md` files directly in `docs/` (not nested) |
| `temp*` | Any file or directory starting with `temp` |

Negation patterns (`!`) work within a single source (e.g., within a single `.gitignore` file) but do not negate patterns from other sources.

## Common Examples

### Ignore a build directory

```yaml
# In config.yaml
ignore:
  additional_patterns:
    - "dist/"
    - "build/"
    - "out/"
```

### Ignore generated files

```
# In .lexignore
*.generated.ts
*.auto.py
generated/
```

### Ignore test fixtures but not test files

```
# In .lexignore
tests/fixtures/
tests/data/
```

### Ignore vendor code

```yaml
# In config.yaml
ignore:
  additional_patterns:
    - "vendor/"
    - "third_party/"
```

## Debugging Ignore Patterns

If files are unexpectedly included or excluded:

1. Check `ignore.additional_patterns` in `.lexibrary/config.yaml`.
2. Check `.gitignore` files (both root and subdirectory).
3. Check `.lexignore` at the project root.
4. Check `crawl.binary_extensions` for binary file types.
5. Check `crawl.max_file_size_kb` for large files.
6. Remember that `ignore.use_gitignore` controls whether `.gitignore` is consulted.

## Related Documentation

- [Configuration](configuration.md) -- `ignore` and `crawl` config sections
- [Design File Generation](design-file-generation.md) -- How file discovery uses the ignore system
- [Getting Started](getting-started.md) -- Initial ignore pattern setup during `lexictl init`
