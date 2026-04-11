# Symbol Graph

The symbol graph is a SQLite database at `.lexibrary/symbols.db` that indexes
code relationships below the file level: function and method definitions, call
edges, class hierarchy, enum membership, and module-level constants.

It is a companion to the [link graph](link-graph.md). The link graph records
edges between *artifacts and files*; the symbol graph records edges between
*symbols within files*.

## Status of this feature

- **Phase 1:** schema and wiring. `.lexibrary/symbols.db` is created but
  remains empty.
- **Phase 2:** Python function, method, and class definitions
  plus call edges, exposed through `lexi trace`, `lexi search --type symbol`,
  and a new "Key symbols" section in `lexi lookup --full`. TypeScript and
  JavaScript extraction records definitions; call resolution for those
  languages is intra-file fuzzy matching only until Phase 6.
- **Phase 3:** class hierarchy edges — `inherits`
  (from `class Foo(Bar):` and TS/JS `extends` / `implements`) and
  `instantiates` (from Python PascalCase calls and TS/JS `new`
  expressions) are recorded in `class_edges`, with unresolved external
  bases (e.g. `BaseModel`, `Enum`) captured in
  `class_edges_unresolved`. `lexi trace <ClassName>` now renders "Base
  classes", "Subclasses and instantiation sites", and an "Unresolved
  bases" line; `lexi lookup --full` adds a "Class hierarchy" table.
  The Python resolver walks the MRO when resolving `self.method()`
  calls so inherited method calls show up in the call graph.
- **Phase 4 (current):** enum members and module-level constants. Python
  `Enum`/`StrEnum`/`IntEnum`/`Flag` subclasses (including transitive
  subclasses), TypeScript `enum` declarations, and module-level
  `const`/ALL_CAPS/type-annotated assignments land as `symbols` rows with
  `symbol_type='enum'` or `'constant'`. Their members and values live in
  the `symbol_members` table. `lexi trace <EnumName>` renders a
  `### Members` block, and `lexi search --type symbol <value>` matches
  on member values as well as symbol names.
- **Phase 5:** design-file enrichment with call paths, enum roles, and data
  flows.
- **Phase 6:** composition edges and TypeScript/JavaScript cross-file
  resolution.

## Storage

The database lives at `.lexibrary/symbols.db` alongside `index.db`. It is
gitignored by default and rebuilt from source on every `lexictl update`. It is
safe to delete — the next update regenerates it.

## Configuration

```yaml
# .lexibrary/config.yaml
symbols:
  enabled: true
```

Set `enabled: false` to skip symbol extraction entirely (saves a small amount
of time during `lexictl update`; disables all symbol-level queries).

## Relationship to the link graph

| Scope | File | Example edge |
|-------|------|-------------|
| Artifact / file level | `.lexibrary/index.db` | `pipeline.py` imports `builder.py` |
| Symbol level | `.lexibrary/symbols.db` | `update_project()` calls `build_index()` at line 1525 |

Both databases are populated during the same `lexictl update` run. Neither
depends on the other at schema level, but the services layer joins them for
commands like `lexi lookup` and `lexi search`.

## Commands

### `lexi trace <symbol>`

Shows callers, callees, and unresolved external calls for every symbol
matching the given name.

- Pass a **bare name** (`update_project`) to match any symbol with that
  name; multiple matches render one section per hit.
- Pass a **fully-qualified name**
  (`lexibrary.archivist.pipeline.update_project`) — any argument
  containing a `.` is matched exactly against `qualified_name`.
- Use `--file <path>` to narrow a bare-name match to a single file when
  the same symbol name exists in multiple modules.

```
$ lexi trace update_project

## lexibrary.archivist.pipeline.update_project  [function]
`src/lexibrary/archivist/pipeline.py:1412`

### Callers
| Caller                          | Location                              |
|---------------------------------|---------------------------------------|
| lexibrary.cli.lexictl_app.update| src/lexibrary/cli/lexictl_app.py:312  |

### Callees
| Callee                                           | Location                                 |
|--------------------------------------------------|------------------------------------------|
| lexibrary.linkgraph.builder.build_index          | src/lexibrary/archivist/pipeline.py:1525 |
| lexibrary.symbolgraph.builder.build_symbol_graph | src/lexibrary/archivist/pipeline.py:1534 |

### Unresolved callees (external or dynamic)
| Name                | Line |
|---------------------|------|
| logger.info         | 1456 |
| logger.exception    | 1476 |
```

When the traced symbol is a class, `lexi trace` also renders the class
hierarchy sections introduced in Phase 3:

```
$ lexi trace LexibraryConfig

## lexibrary.config.schema.LexibraryConfig  [class]
`src/lexibrary/config/schema.py:42`

### Base classes
| Base                                    | Location                                  |
|-----------------------------------------|-------------------------------------------|
| lexibrary.config.schema._ConfigBase     | src/lexibrary/config/schema.py:18         |

### Subclasses and instantiation sites
| Type          | Source                                  | Location                                 |
|---------------|------------------------------------------|------------------------------------------|
| instantiates  | lexibrary.config.loader.load_config      | src/lexibrary/config/loader.py:87        |
| instantiates  | lexibrary.init.wizard.write_config       | src/lexibrary/init/wizard.py:214         |

Unresolved bases: BaseModel
```

- **Base classes** — every resolved parent the class inherits from or
  implements. Phase 3 records these from Python `class Foo(Bar):`
  declarations, TS/JS `extends`, and TS `implements` clauses.
- **Subclasses and instantiation sites** — every resolved class that
  inherits from this one (`inherits` rows) plus every call site that
  constructs it (`instantiates` rows). Phase 3 emits `instantiates`
  from Python PascalCase calls matching `^[A-Z][A-Za-z0-9]*$` and
  TS/JS `new` expressions.
- **Unresolved bases** — a trailing line listing base names the
  resolver could not map to a project symbol (typically external
  libraries such as Pydantic `BaseModel`, stdlib `Enum`). The playbook
  treats these as out-of-scope for refactoring.

When the traced symbol is an enum or a module-level constant, `lexi
trace` also renders a `### Members` block introduced in Phase 4:

```
$ lexi trace BuildStatus

## myapp.status.BuildStatus  [enum]
`src/myapp/status.py:12`

### Members
| Name     | Value       | Ordinal |
|----------|-------------|---------|
| PENDING  | "pending"   | 0       |
| RUNNING  | "running"   | 1       |
| FAILED   | "failed"    | 2       |
```

- **Members** — one row per `symbol_members` row for the traced
  symbol, in ordinal order. For Python `Enum`/`StrEnum`/`IntEnum`
  subclasses and TypeScript `enum` declarations, each row is an enum
  variant with its literal value (or empty when the value is a
  non-literal expression such as `auto()`). For module-level constants
  (`SCHEMA_VERSION = 2`, `const API_URL = "..."`), the block renders a
  single row with the constant's name and literal value and `Ordinal`
  set to `0`.

If the symbol's file has a stale `last_hash` in `symbols.db`, `lexi trace`
prints a `Symbol graph may be stale for <file> — run lexi design update
<file> to refresh.` warning on stderr and still renders the (possibly
outdated) results. If no symbol matches, the command exits with code 1
and hints at `lexi design update` and `lexi search --type symbol`.

### `lexi search --type symbol <query>`

LIKE-search on `symbols.name` and `symbols.qualified_name`. Phase 4
extends this to also match on `symbol_members.value`, so an unfamiliar
magic string in an error message can be traced back to its defining
enum or constant without grepping:

```
$ lexi search --type symbol pending

### Symbols
| Name         | Type     | Location                     |
|--------------|----------|------------------------------|
| BuildStatus  | enum     | src/myapp/status.py:12       |
```

`BuildStatus` matches because one of its enum members has the value
`"pending"`, not because its name contains `pending`. Value matches and
name matches are merged into a single result set; each symbol appears
at most once. Returns a `file:line` for each hit. Unlike the artifact
search path this does not support `--tag` or any stack-only flags;
combining them exits with code 1 and an error explaining the mismatch.
`--limit` still applies.

### `lexi lookup <file> --full`

The `Key symbols` section lists the file's public functions, classes, and
methods with caller and callee counts — useful for sizing refactor blast
radius before editing. Methods are grouped under their class. The list is
capped at 10 rows; if the file defines more public symbols, a trailing
`… and N more` line is appended. The section is omitted when
`symbols.enabled` is `false` or `symbols.db` is missing.

### Class hierarchy in lookup output

Phase 3 adds a `### Class hierarchy` table to `lexi lookup --full` for
any file that defines at least one class. The table has one row per
class, with the class name, its resolved bases, any unresolved external
bases (suffixed with `*`), the count of known subclasses, the number of
methods, and the class's starting line number:

```
### Class hierarchy

| Class              | Bases                      | Subclasses | Methods | Line |
|--------------------|----------------------------|------------|---------|------|
| LexibraryConfig    | _ConfigBase, BaseModel*    |          2 |       7 |   42 |
| StackConfig        | BaseModel*                 |          0 |       3 |  118 |
```

- Resolved bases are joined with `, `. Unresolved bases are appended
  with a `*` suffix to mark them as external (not refactorable from
  lexi's point of view).
- A class with no bases shows `—` in the Bases column.
- The section is omitted entirely when the file defines no classes or
  when `symbols.db` is missing.

## Enums and constants

Phase 4 records every Python `Enum`/`StrEnum`/`IntEnum`/`Flag`
subclass, every TypeScript `enum` declaration (including `const enum`
and `export enum`), and every module-level `const` / ALL_CAPS /
type-annotated assignment as a `symbols` row with
`symbol_type='enum'` or `'constant'`. Enum members and constant
values live in the `symbol_members` table — one row per enum variant,
or a single row per constant with `ordinal = 0`.

What is indexed:

- **Python enums** — any top-level class whose base chain includes
  `Enum`, `IntEnum`, `StrEnum`, `Flag`, or `IntFlag` (including
  dotted `enum.Enum` references). A second pass walks the
  `class_edges` inherits graph after extraction, so a project-local
  base (`class MyBase(StrEnum): ...`) transitively classifies every
  subclass (`class BuildStatus(MyBase): ...`) as
  `symbol_type='enum'`.
- **Python constants** — module-level assignments where the name is
  ALL_CAPS or the statement has a type annotation, AND the right-hand
  side is a simple literal (`string`, `int`, `float`, `True`, `False`,
  `None`, or a tuple/list/set of those). Assignments inside function
  or class bodies are NOT indexed. Non-literal right-hand sides
  (function calls, comprehensions, expressions over names) are
  skipped.
- **TypeScript enums** — `enum Foo { ... }`, `const enum Foo { ... }`,
  and `export enum Foo { ... }`. Each enum variant lands as one
  `symbol_members` row with its literal value as the raw source text.
- **TypeScript and JavaScript constants** — `lexical_declaration` at
  program scope where the kind is `const` and the right-hand side is
  a primitive literal (`string`, `number`, `true`, `false`, `null`,
  `regex`). Object literals, array literals, template strings with
  substitutions, and arrow functions are NOT indexed as constants —
  arrow functions are already handled by the function pipeline.

This enables two complementary query patterns:

- **By name:** `lexi trace BuildStatus` — trace the enum like any
  other symbol and read its members from the `### Members` block, in
  ordinal order.
- **By value:** `lexi search --type symbol pending` — find every
  symbol whose member value contains `pending`. Useful when a bug
  surfaces a magic string in an error message or log line and you
  need to know the canonical enum that produced it.

JavaScript is intentionally not parsed for enums. JS has no `enum`
keyword, and the common `Object.freeze({...})` workaround is too
ambiguous to index without false positives — JS files contribute only
constants to the symbol graph.

## See also

- Concept: [[Symbol Graph]] (`CN-021`)
- Concept: [[Call Edge]] (`CN-022`)
- Concept: [[Symbol Resolution]] (`CN-023`)
- Playbook: [[Tracing a symbol with lexi trace]] (`PB-008`)
- Playbook: [[Refactoring with the call graph]] (`PB-009`)
- [Link Graph](link-graph.md)
- [How It Works](how-it-works.md)
