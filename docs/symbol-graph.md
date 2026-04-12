# Symbol Graph

The symbol graph is a SQLite database at `.lexibrary/symbols.db` that indexes
code relationships below the file level: function and method definitions, call
edges, class hierarchy, enum membership, and module-level constants.

It is a companion to the [link graph](link-graph.md). The link graph records
edges between *artifacts and files*; the symbol graph records edges between
*symbols within files*.

## Schema overview

The symbol graph schema defines the following core tables:

| Table | Purpose |
|-------|---------|
| `meta` | Key-value metadata: schema version, last-built timestamp |
| `files` | One row per indexed source file with its SHA-256 hash |
| `symbols` | Function, method, class, enum, and constant definitions with qualified names |
| `symbol_members` | Enum variants and constant values, one row per member |
| `calls` / `unresolved_calls` | Resolved and unresolved call edges between symbols |
| `class_edges` / `class_edges_unresolved` | Resolved and unresolved class relationship edges (`inherits`, `instantiates`, `composes`) |
| `symbol_branch_parameters` | Parameter names appearing in branch conditions within function bodies (Phase 7) |

Schema versioning is managed by `SCHEMA_VERSION` in `src/lexibrary/symbolgraph/schema.py`. On version mismatch the database is dropped and rebuilt from scratch -- there is no incremental migration. See convention CV-017 for the full extension procedure.

## Extracted languages and limits

| Language | Definitions | Call edges | Class edges | Enums/constants | Composition |
|----------|------------|------------|-------------|-----------------|-------------|
| Python | Functions, methods, classes | Cross-file via import resolver | `inherits`, `instantiates`, `composes` | `Enum`/`StrEnum`/`IntEnum`/`Flag` subclasses; ALL_CAPS and annotated module-level constants | Type-annotated class attributes and `__init__` `self.x: Type` |
| TypeScript | Functions, methods, classes | Cross-file via `tsconfig.json` resolver | `inherits` (`extends`/`implements`), `instantiates` (`new`), `composes` | `enum`, `const enum`, `export enum`; top-level `const` literals | `public_field_definition` with type annotations |
| JavaScript | Functions, methods, classes | Cross-file via JS resolver (shared with TS) | `inherits` (`extends`), `instantiates` (`new`), `composes` | Top-level `const` literals only (no JS `enum` keyword) | Class field type annotations |

**Known limits:**

- Generic wrapper stripping is single-layer: `dict[str, list[Thing]]` extracts `list` as the inner type, not `Thing`. This covers the majority of practical attribute types.
- Python composition extraction requires type annotations (`self.x: Type`). Unannotated `self.x = Foo()` assignments are skipped.
- JavaScript does not contribute enums -- `Object.freeze({...})` patterns are too ambiguous to index without false positives.
- `node_modules` imports return `None` (correctly classified as external/unresolved).

## Storage

The database lives at `.lexibrary/symbols.db` alongside `index.db`. It is
gitignored by default and rebuilt from source on every `lexictl update`. It is
safe to delete — the next update regenerates it.

## Configuration

```yaml
# .lexibrary/config.yaml
symbols:
  enabled: true
  include_enums: true
  include_call_paths: false
  call_path_depth: 2
  max_enum_items: 20
  max_call_path_items: 10
```

Set `enabled: false` to skip symbol extraction entirely (saves a small amount
of time during `lexictl update`; disables all symbol-level queries). The five
enrichment flags (`include_enums`, `include_call_paths`, `call_path_depth`,
`max_enum_items`, `max_call_path_items`) tune the design-file enrichment
pipeline described below -- see [Configuration](configuration.md#symbols) for
the full reference with defaults and descriptions.

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

When the traced symbol is a class, `lexi trace` also renders class
relationship sections:

```
$ lexi trace LexibraryConfig

## lexibrary.config.schema.LexibraryConfig  [class]
`src/lexibrary/config/schema.py:42`

### Class relationships
| Relationship | Target                                  | Location                                  |
|--------------|-----------------------------------------|-------------------------------------------|
| inherits     | lexibrary.config.schema._ConfigBase     | src/lexibrary/config/schema.py:18         |

### Subclasses, instantiation, and composition
| Type          | Source                                  | Location                                 |
|---------------|------------------------------------------|------------------------------------------|
| instantiates  | lexibrary.config.loader.load_config      | src/lexibrary/config/loader.py:87        |
| instantiates  | lexibrary.init.wizard.write_config       | src/lexibrary/init/wizard.py:214         |

Unresolved bases: BaseModel
```

- **Class relationships** — every resolved parent the class inherits
  from, implements, or composes. Recorded from Python `class Foo(Bar):`
  declarations, TS/JS `extends` and `implements` clauses, and
  type-annotated class attributes (composition).
- **Subclasses, instantiation, and composition** — every resolved class
  that inherits from this one (`inherits`), every call site that
  constructs it (`instantiates`), and every class that holds it as a
  typed attribute (`composes`).
- **Unresolved bases** / **Unresolved compositions** — trailing lines
  listing names the resolver could not map to a project symbol.
  Unresolved bases are typically external libraries (Pydantic
  `BaseModel`, stdlib `Enum`). Treat these as out-of-scope for
  refactoring.

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

## Composition edges

Composition edges record "has-a" relationships between classes via
type-annotated attributes. A `composes` edge from class `A` to class `B`
means that `A` holds a typed reference to `B` as an instance attribute.

What is indexed:

- **Python class body annotations** -- `class Foo: bar: Bar` extracts a
  `composes` edge from `Foo` to `Bar`. Generic wrappers are stripped one
  layer deep: `list[Bar]`, `Optional[Bar]`, `dict[str, Bar]`, and
  `Bar | None` all resolve to `Bar`.
- **Python `__init__` self annotations** -- `self.bar: Bar = ...` in
  `__init__` is treated identically to a class body annotation. Only
  annotated assignments are extracted; unannotated `self.bar = Bar()` is
  skipped.
- **TypeScript class fields** -- `public_field_definition` nodes with a
  `type_annotation` child extract a `composes` edge. TypeScript builtins
  (`string`, `number`, `boolean`, etc.) are filtered out.

In all cases, builtin types (`int`, `str`, `bool`, `float`, `list`,
`dict`, `tuple`, `set`, `bytes`, `None` for Python; `string`, `number`,
`boolean`, `any`, `void`, `never`, `undefined`, `null`, `unknown`,
`object` for TypeScript) and single-letter generic parameters (`T`, `K`,
`V`) are skipped.

Composition edges appear in `lexi trace` output alongside inheritance and
instantiation edges. Resolved edges land in `class_edges` with
`edge_type='composes'`; unresolved targets go into
`class_edges_unresolved`.

## Incremental rebuild

When `build_symbol_graph` receives a `changed_paths` list (threaded from
the archivist pipeline), it checks whether the number of changed files is
below an incremental threshold (30% of total indexed files). If so, it
performs a per-file incremental rebuild using the existing `refresh_file`
function, which does DELETE CASCADE on the file's rows then re-extracts.
Files above the threshold trigger a full rebuild.

The incremental path sets `build_type="incremental"` on the result so
the pipeline can report which strategy was used. Individual file refreshes
(via `lexi design update <file>`) always use the single-file path
regardless of the threshold.

## Design file enrichment

Phase 5 wires the symbol graph into the archivist's design-file pipeline
so each generated design file gains up to three optional sections:

- **`## Enums & constants`** — Structured notes for every enum and
  module-level constant defined in the file. Each entry has a `name`,
  a one-clause `role` describing what it represents, and a `values`
  list. Sourced from the `symbols` and `symbol_members` tables.
- **`## Call paths`** — Narrative notes for the most important call
  chains flowing through the file's functions and methods. Each entry
  has an `entry` symbol, a one- to two-sentence `narrative`, and a
  `key_hops` list. Sourced from the `symbol_calls` table.

- **`## Data flows`** — Notes about how function parameters influence
  control flow through branching. Each entry has a `parameter` name,
  a `location` (the function where branching occurs), and a one-sentence
  `effect` description. Gated on the `symbol_branch_parameters` table
  (Phase 7). See the [Data flow notes](#data-flow-notes) subsection.

All three sections are fed into the BAML prompt as pre-rendered text blocks
and returned as structured output in `EnumNote` / `CallPathNote` /
`DataFlowNote` form. The Pydantic `DesignFile` model, parser, and
serializer round-trip them as first-class fields. `lexi lookup` surfaces
all sections when they are populated.

### Config flags

All six flags live under `symbols:` in `.lexibrary/config.yaml`:

| Flag | Default | Purpose |
|---|---|---|
| `include_enums` | `true` | Feed enum/constant context into the archivist prompt. |
| `include_call_paths` | `false` | Opt-in: feed caller/callee context into the archivist prompt. |
| `include_data_flows` | `false` | Opt-in: feed branch-parameter context into the archivist prompt, gated on deterministic AST signal. |
| `call_path_depth` | `2` | Hops in each direction when building call-path summaries. |
| `max_enum_items` | `20` | Truncate the enum block once this many entries are rendered. |
| `max_call_path_items` | `10` | Truncate the call-path block once this many entries are rendered. |

Truncation appends a trailing `- ... N more` line so the LLM can see
the output is incomplete and phrase its prose accordingly.

### Cost trade-offs

Enum context is **cheap**: the enrichment helper walks the symbol
graph, resolves the file's enum/constant symbols, and emits a short
list of names and literal values. Prompt growth is roughly
proportional to the number of enums in the file, bounded by
`max_enum_items`. Enums are **on by default** because the cost is
small and the narrative payoff is high.

Call paths are **opt-in** because they increase prompt size by roughly
`call_path_depth × 50` tokens per file -- a depth-2 path typically
names 2-4 callers and 2-4 callees per function, each with a qualified
name and a location. Files with many public functions compound this
cost quickly. Enable call paths in your config only when the
narrative value is worth the prompt budget:

```yaml
symbols:
  include_call_paths: true
  call_path_depth: 2
  max_call_path_items: 10
```

If you only want call paths for a specific design pass, toggle the
flag in `.lexibrary/config.yaml`, run `lexictl update`, and toggle
it back.

### Pipeline ordering

The symbol graph build step in `update_project` now runs **before** the
design-file generation loop, so the `symbols.db` is populated when the
archivist starts rendering prompt context. The `SymbolQueryService` is
opened once at the top of the loop and closed when the loop completes,
so no additional SQLite connections are created per file. If the
symbol graph build fails (or `symbols.enabled` is `false`), enrichment
is skipped gracefully and design files are generated without the new
sections.

### Data flow notes

Phase 7 adds a `## Data flows` section to design files, describing how
function parameters influence control flow through branching. This section
is powered by the `symbol_branch_parameters` table, which records every
parameter name that appears in a branch condition (`if`, `match`, `switch`,
ternary, `while`, `for` condition) within a function body.

The archivist gate uses a two-layer check to decide whether to ask the
LLM for data flow notes:

1. **File-level gate** -- `has_branching_parameters_in_file(path)` queries
   whether any function in the file has at least one branch parameter.
   If not, the LLM is never asked and no prompt tokens are spent.
2. **Symbol-level rendering** -- `_render_branch_parameters(svc, symbols)`
   iterates the file's function/method symbols, calls
   `branch_parameters_of(sym.id)` for each, and emits a pre-rendered
   block listing which functions branch on which parameters. This block
   is fed to the BAML prompt so the LLM can write a data flow note per
   branching function.

The `include_data_flows` config flag (default `false`) must be set to
`true` for the gate to activate at all. Even when enabled, the two-layer
gate ensures prompt cost is zero for files with no branching parameters,
keeping the feature cheap for large codebases where most files do not
have parameter-driven branching.

The resulting `DataFlowNote` objects have three fields:

| Field | Description |
|-------|-------------|
| `parameter` | The parameter name driving branching (e.g. `changed_paths`) |
| `location` | The function where the branching occurs (e.g. `build_index()`) |
| `effect` | A one-sentence description of the behavioural impact |

The notes are round-tripped through the design file parser and serializer
in the format `- **{parameter}** in **{location}** — {effect}`, and
surfaced by `lexi lookup` as a `### Data flows` subsection after
`### Call paths`.

## Troubleshooting

See [Troubleshooting -- Symbol graph issues](troubleshooting.md#symbol-graph-issues)
for solutions to common problems including missing symbols, unexpected
unresolved callees, out-of-sync graphs after renames, and corrupt or
missing `symbols.db`.

## See also

- Concept: [[Symbol Graph]] (`CN-021`)
- Concept: [[Call Edge]] (`CN-022`)
- Concept: [[Symbol Resolution]] (`CN-023`)
- Convention: [[Symbol Graph Extension]] (`CV-017`)
- Playbook: [[Tracing a symbol with lexi trace]] (`PB-008`)
- Playbook: [[Refactoring with the call graph]] (`PB-009`)
- [Link Graph](link-graph.md)
- [How It Works](how-it-works.md)
- [Troubleshooting](troubleshooting.md#symbol-graph-issues)
