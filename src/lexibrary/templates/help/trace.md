# `lexi trace` — output interpretation

`lexi trace <symbol>` emits a per-match block of Markdown-style sections.
Only non-empty sections appear, and which sections appear depends on the
symbol type. This is the full reference for interpreting that output.

## Header block

Every matched symbol starts with:

    ## <qualified_name or name>  [<symbol_type>]
    `<file_path>:<line_start>`

`symbol_type` is one of `function`, `method`, `class`, `enum`, `constant`.

## Section reference

### Callers
Resolved inbound call edges — functions/methods that call this symbol.
Columns: `Caller`, `Location`. Appears for functions and methods; for
classes, instantiation sites appear under `### Subclasses, instantiation,
and composition` instead.

### Callees
Resolved outbound call edges. Columns: `Callee`, `Location`. Appears for
functions and methods.

### Unresolved callees (external or dynamic)
Outbound call sites that did not resolve to an indexed symbol — stdlib,
third-party libraries, dynamic dispatch. Columns: `Name`, `Line`.
**Informational, not errors.** These are not refactoring risks from
lexi's point of view.

### Class relationships
Resolved outbound class edges — base classes and compositions. Columns:
`Relationship` (one of `inherits`, `composes`), `Target`, `Location`.
Appears only for classes.

### Subclasses, instantiation, and composition
Resolved inbound class edges. Columns: `Type` (one of `inherits`,
`instantiates`, `composes`), `Source`, `Location`. Appears only for
classes. When renaming or removing a class, check this section first.

### Unresolved bases / Unresolved compositions
Trailing text lines listing external base classes (e.g. `BaseModel`,
`Enum`) or composition targets that are not defined in the indexed
codebase. **Treat as out-of-scope** — they are not refactoring risks.

### Members
Enum variants and constant values. Columns: `Name`, `Value`, `Ordinal`.
Appears for enum and constant symbols. `Ordinal` may be blank when the
extractor did not capture a source-order position.

## Disambiguation

- A bare name (no dot) matches every symbol with that name across all files.
- A fully-qualified name (e.g. `lexibrary.archivist.pipeline.update_project`)
  matches only that exact symbol.
- `--file <path>` narrows either form to a single file.

## Staleness

If the on-disk hash of a file has drifted from the symbol graph's
`last_hash`, `lexi trace` emits a `warn()` on stderr naming the file and
the refresh command (`lexi design update <file>`). The trace still
renders — the warning is advisory.
