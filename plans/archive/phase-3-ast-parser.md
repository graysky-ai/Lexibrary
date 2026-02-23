# Phase 3 — AST Parser & Two-Tier Hashing

**Reference:** `plans/v2-master-plan.md` (Phase 3 section), `lexibrary-overview.md` (§7 Change Detection)
**Depends on:** Phase 1 (Foundation), Phase 2 (Directory Indexes) — both complete
**Consumed by:** Phase 4 (Archivist) — `lexi update` pipeline calls this module

---

## Goal

Given a source file, produce a **structured interface skeleton** (function signatures, class names, public API) and compute both a **content hash** and an **interface hash**. The interface hash enables Phase 4 to skip expensive LLM regeneration when only internal implementation details changed.

Phase 3 is a **library module only** — no new CLI commands. Phase 4's Archivist consumes it.

---

## Decisions Made

| # | Decision | Resolution |
|---|----------|------------|
| D-007 | Supported languages at launch | Python, TypeScript, JavaScript (3 languages, 6 extensions) |
| D-008 | CLI surface | None. Internal library module only. Phase 4 wires it into `lexi update`. |
| D-009 | Skeleton detail level | Signatures only — names, parameters, type annotations, return types, class names, module-level constants. No decorators, no docstrings, no body logic. |
| D-010 | Grammar management | Optional extras group: `pip install lexibrary[ast]`. Grammars are not in base deps. |

---

## New Dependencies

Added to `pyproject.toml` under `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
ast = [
    "tree-sitter>=0.25.0,<0.26.0",
    "tree-sitter-python>=0.25.0,<0.26.0",
    "tree-sitter-javascript>=0.25.0,<0.26.0",
    "tree-sitter-typescript>=0.23.0,<0.24.0",
]
```

**Version rationale:**
- `tree-sitter` core: 0.25.2 is current; pin to `>=0.25.0,<0.26.0` per bounded-range constraint
- `tree-sitter-python`: 0.25.0 is current
- `tree-sitter-javascript`: 0.25.0 is current
- `tree-sitter-typescript`: 0.23.2 is current (lags behind others)

**Dev dependencies:** add the `ast` extras to the dev install so CI always has grammars.

---

## Module Structure

```
src/lexibrary/ast_parser/
├── __init__.py          # Public API: parse_interface(), hash_interface()
├── models.py            # InterfaceSkeleton, FunctionSig, ClassSig, ConstantSig
├── registry.py          # Grammar registry: extension → Language + query
├── python_parser.py     # Python-specific tree-sitter queries
├── typescript_parser.py # TypeScript-specific tree-sitter queries
├── javascript_parser.py # JavaScript-specific tree-sitter queries
└── skeleton_render.py   # Deterministic text rendering for hashing

tests/test_ast_parser/
├── __init__.py
├── test_models.py
├── test_registry.py
├── test_python_parser.py
├── test_typescript_parser.py
├── test_javascript_parser.py
├── test_skeleton_render.py
├── test_hash_interface.py
└── fixtures/            # Sample source files for each language
    ├── simple_module.py
    ├── classes_and_functions.py
    ├── empty_module.py
    ├── no_public_api.py     # only private/internal symbols
    ├── simple_module.ts
    ├── classes_and_functions.ts
    ├── simple_module.js
    └── jsx_component.tsx
```

---

## Data Models (`models.py`)

```python
class ConstantSig(BaseModel):
    """A module-level constant or exported variable."""
    name: str
    type_annotation: str | None = None

class ParameterSig(BaseModel):
    """A function/method parameter."""
    name: str
    type_annotation: str | None = None
    default: str | None = None  # string repr, e.g. "None", "0", "[]"

class FunctionSig(BaseModel):
    """A function or method signature."""
    name: str
    parameters: list[ParameterSig] = []
    return_type: str | None = None
    is_async: bool = False
    is_method: bool = False
    is_static: bool = False
    is_class_method: bool = False
    is_property: bool = False

class ClassSig(BaseModel):
    """A class signature with its methods."""
    name: str
    bases: list[str] = []
    methods: list[FunctionSig] = []
    class_variables: list[ConstantSig] = []

class InterfaceSkeleton(BaseModel):
    """The complete public interface extracted from a source file."""
    file_path: str
    language: str
    constants: list[ConstantSig] = []
    functions: list[FunctionSig] = []
    classes: list[ClassSig] = []
    exports: list[str] = []  # TS/JS explicit exports (export default, __all__)
```

### Design notes

- All fields are sorted alphabetically within their lists before rendering. This ensures **deterministic output** (same input → same hash) regardless of declaration order. Rationale: if a developer reorders functions without changing signatures, the interface hash should not change — ordering is not part of the public API contract.
- `default` in `ParameterSig` captures the string representation only, not the value. Defaults are part of the signature contract — changing a default from `None` to `0` changes the interface.
- `exports` captures explicit export declarations (`__all__` in Python, `export`/`export default` in TS/JS). This is the "what's publicly importable" signal beyond just "what exists."
- `is_property`, `is_static`, `is_class_method` on `FunctionSig` — while we're capturing "signatures only" (not decorators), these three are **structural** modifiers that change how the method is called. They are part of the calling convention, not decorator metadata. They are extracted from tree-sitter node types, not from decorator text.

---

## Grammar Registry (`registry.py`)

Maps file extensions to tree-sitter Language objects and parser implementations.

```python
GRAMMAR_MAP: dict[str, GrammarInfo]
# ".py"  → GrammarInfo(module="tree_sitter_python", loader=..., parser=PythonParser)
# ".ts"  → GrammarInfo(module="tree_sitter_typescript", submodule="typescript", parser=TypeScriptParser)
# ".tsx" → GrammarInfo(module="tree_sitter_typescript", submodule="tsx", parser=TypeScriptParser)
# ".js"  → GrammarInfo(module="tree_sitter_javascript", parser=JavaScriptParser)
# ".jsx" → GrammarInfo(module="tree_sitter_javascript", parser=JavaScriptParser)
# ".pyi" → GrammarInfo(module="tree_sitter_python", loader=..., parser=PythonParser)
```

**Grammar loading pattern** (py-tree-sitter 0.25 API):

```python
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)
tree = parser.parse(source_bytes)
```

For TypeScript, the grammar package exposes two sub-grammars (TypeScript and TSX) but the **Python-side import pattern is undocumented**. The exact way to load each sub-grammar must be verified by the Task 2 spike before any TS/JS parser work begins. See [Concern: tree-sitter-typescript Python API](#concern-tree-sitter-typescript-python-api) for the full investigation plan and fallback strategies.

**Graceful fallback:** If a grammar package is not installed (`ImportError`), the registry returns `None` and `parse_interface()` returns `None`. A clear warning is emitted via `rich.console.Console`:

```
⚠ tree-sitter-python not installed. Run: pip install lexibrary[ast]
```

**Caching:** Language objects and Parser instances are cached at module level (created once per process). Grammars are immutable — no invalidation needed.

---

## Language Parsers

Each parser module exposes a single function:

```python
def extract_interface(tree: Tree, source: bytes) -> InterfaceSkeleton
```

### Python Parser (`python_parser.py`)

Uses tree-sitter queries to extract:

| Node type | Extracts |
|-----------|----------|
| `module` → `expression_statement` → `assignment` | Module-level constants (UPPER_CASE names or type-annotated) |
| `function_definition` | Top-level functions: name, params, return type, async |
| `class_definition` | Class name, base classes |
| `class_definition` → `function_definition` | Methods: name, params, return type, staticmethod/classmethod/property (from node structure) |
| `expression_statement` → `assignment` where name = `__all__` | Explicit exports list |

**What is excluded:**
- Private functions/methods (name starts with `_`, except `__init__` and `__new__`)
- Nested functions (only top-level and class-level)
- Import statements (dependencies are Phase 4's concern — extracted from source directly, not from the interface skeleton)
- Decorators (text content excluded; structural modifiers like staticmethod captured as booleans)
- Docstrings
- Function bodies
- Comments

**`__init__` special case:** Always included in class methods despite the `_` prefix. It defines the construction contract. `__new__` likewise.

### TypeScript Parser (`typescript_parser.py`)

| Node type | Extracts |
|-----------|----------|
| `lexical_declaration` (const/let at module level) | Constants with type annotations |
| `function_declaration` | Top-level functions |
| `class_declaration` | Classes, methods, properties |
| `interface_declaration` | TS interfaces (treated like classes with no body) |
| `type_alias_declaration` | Type aliases |
| `export_statement` | Explicit exports |
| `enum_declaration` | Enums |

**TSX:** Uses the TSX sub-grammar. JSX elements in function bodies are ignored (body is never parsed). The parser handles `.tsx` files identically to `.ts` for interface extraction purposes.

### JavaScript Parser (`javascript_parser.py`)

Same structure as TypeScript but without:
- `interface_declaration` (doesn't exist in JS)
- `type_alias_declaration`
- Type annotations on parameters/returns

Handles `.jsx` via the same grammar (JSX is part of the tree-sitter-javascript grammar).

---

## Skeleton Rendering (`skeleton_render.py`)

Converts an `InterfaceSkeleton` into a **deterministic canonical text** for hashing.

**Rules for determinism:**
1. All lists sorted alphabetically by name
2. No line numbers, no file paths in the rendered text
3. No comments or whitespace variation
4. Canonical formatting (single space after colons, no trailing commas)
5. Consistent ordering: constants → functions → classes → exports

**Example output** (for hashing, not for display):

```
const:MAX_RETRIES:int
const:TIMEOUT:float
func:authenticate(username:str,password:str)->bool
func:refresh_token(token:str)->str|None
class:AuthService(BaseService)
  method:__init__(self,config:AuthConfig)->None
  method:login(self,credentials:Credentials)->Session
  method:logout(self,session_id:str)->None
  classmethod:from_env(cls)->AuthService
export:AuthService
export:authenticate
```

This is a compact, diff-friendly format. It is never displayed to users — it exists solely to be hashed.

---

## Two-Tier Hashing

### Extension to `utils/hashing.py`

Add one function:

```python
def hash_string(text: str) -> str:
    """SHA-256 hash of a UTF-8 string. Returns 64-char hex digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
```

Also consolidate the inline `_compute_dir_hash()` in `indexer/generator.py` to use `hash_string`.

### Public API (`ast_parser/__init__.py`)

```python
def parse_interface(file_path: Path) -> InterfaceSkeleton | None:
    """Extract the public interface skeleton from a source file.

    Returns None if:
    - The file extension has no registered grammar
    - The grammar package is not installed
    - The file cannot be parsed (syntax errors are tolerated — tree-sitter
      produces partial trees for malformed input)
    """

def hash_interface(skeleton: InterfaceSkeleton) -> str:
    """Render skeleton to canonical text and return its SHA-256 hash."""

def compute_hashes(file_path: Path) -> tuple[str, str | None]:
    """Convenience: returns (content_hash, interface_hash | None).

    content_hash: SHA-256 of full file content (always available)
    interface_hash: SHA-256 of rendered interface skeleton (None if no grammar)
    """
```

### How Phase 4 uses this

```python
from lexibrary.ast_parser import compute_hashes
from lexibrary.utils.hashing import hash_file

content_hash, interface_hash = compute_hashes(source_path)

existing_meta = load_existing_design_file_metadata(source_path)
if existing_meta and existing_meta.source_hash == content_hash:
    # Nothing changed at all — skip
    pass
elif existing_meta and existing_meta.interface_hash == interface_hash:
    # Internal changes only — lightweight description update
    pass
else:
    # Interface changed (or no existing file) — full Archivist generation
    skeleton = parse_interface(source_path)
    design_file = archivist.generate(source_path, skeleton, ...)
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Grammar package not installed | `parse_interface()` returns `None`. Warning printed once per session per language. |
| File extension not in registry | `parse_interface()` returns `None`. No warning (expected for non-code files). |
| Syntax errors in source file | tree-sitter produces a partial tree with `ERROR` nodes. Parser extracts what it can. No exception. |
| Empty file | Returns `InterfaceSkeleton` with empty lists. Interface hash is the hash of the empty canonical form. |
| Binary file | Caller should check before calling (use `crawler/file_reader.py:is_binary_file()`). If called anyway, tree-sitter will fail to parse — returns `None`. |
| File read error (permissions, missing) | Raise — let the caller handle. Don't silently swallow. |

---

## Config Changes

Add an `ast` section to `LexibraryConfig`:

```python
class ASTConfig(BaseModel):
    """Configuration for AST parsing and interface extraction."""
    enabled: bool = True
    languages: list[str] = ["python", "typescript", "javascript"]
```

This allows users to disable AST parsing entirely or restrict to specific languages. Added to `LexibraryConfig` with `ast: ASTConfig = ASTConfig()`.

The `defaults.py` YAML template gains:

```yaml
# AST parsing for interface extraction
ast:
  enabled: true
  languages:
    - python
    - typescript
    - javascript
```

---

## Test Plan

### Unit tests

| Test file | What it covers |
|-----------|----------------|
| `test_models.py` | Pydantic model validation, serialisation, defaults |
| `test_registry.py` | Grammar loading, fallback on missing packages, extension mapping |
| `test_python_parser.py` | Python interface extraction (see scenarios below) |
| `test_typescript_parser.py` | TypeScript/TSX interface extraction |
| `test_javascript_parser.py` | JavaScript/JSX interface extraction |
| `test_skeleton_render.py` | Deterministic rendering, sort order, canonical format |
| `test_hash_interface.py` | Hash stability, different-skeleton → different-hash, same-skeleton → same-hash |

### Python parser test scenarios

1. Simple module with functions and constants
2. Class with `__init__`, public methods, private methods (private excluded)
3. Async functions
4. `staticmethod` / `classmethod` / `property` detection
5. Type annotations (present and absent)
6. Default parameter values
7. `__all__` exports
8. Empty module → empty skeleton
9. Module with only private symbols → empty skeleton (no public API)
10. Syntax error in source → partial extraction (no crash)
11. Nested classes (extracted? — decision: extract top-level classes only)
12. Module-level constant detection (UPPER_CASE heuristic + type-annotated assignments)

### TypeScript parser test scenarios

1. Interface declarations
2. Type aliases
3. Class with constructor, methods, properties
4. Exported functions and constants
5. `export default`
6. Enum declarations
7. Generic type parameters
8. `.tsx` file with JSX in function body (JSX ignored)

### JavaScript parser test scenarios

1. Functions and arrow functions
2. Class declarations with methods
3. Module exports (`export`, `export default`, `module.exports`)
4. No type annotations (all type fields `None`)
5. `.jsx` file

### Integration tests

1. `parse_interface()` end-to-end: file on disk → `InterfaceSkeleton`
2. `compute_hashes()` end-to-end: file → `(content_hash, interface_hash)`
3. **Hash stability:** parse the same file twice → identical interface hash
4. **Hash sensitivity:** change a function signature → different interface hash
5. **Hash insensitivity:** change function body only → same interface hash
6. **Hash insensitivity:** reorder functions → same interface hash (sorted rendering)
7. Grammar missing → `None` return, warning emitted
8. Unsupported extension → `None` return, no warning

### Fixture files

Sample source files in `tests/test_ast_parser/fixtures/`. Each is a real parseable file, not a string literal in the test. This ensures tree-sitter processes them through its full pipeline.

---

## Implementation Order

### Task 1: Data models and skeleton renderer
- `ast_parser/models.py` — Pydantic models
- `ast_parser/skeleton_render.py` — deterministic renderer
- `utils/hashing.py` — add `hash_string()`
- Tests: `test_models.py`, `test_skeleton_render.py`

### Task 2: Grammar registry, fallback handling, and TS/JS grammar spike

**⚠ This task contains a mandatory spike — see [Concern: tree-sitter-typescript Python API](#concern-tree-sitter-typescript-python-api) below.**

Before writing any parser code, Task 2 must resolve the TypeScript/JavaScript grammar loading patterns. The spike gates Tasks 3–5.

- **Spike (do first):** Write a throwaway script that imports `tree_sitter_typescript` and attempts to load both the TypeScript and TSX languages. Verify the Python-side API for accessing sub-grammars. Document the working import pattern. See the concern section below for exactly what needs to be validated.
- `ast_parser/registry.py` — extension mapping, lazy grammar loading, caching
- `pyproject.toml` — add `[project.optional-dependencies] ast = [...]`
- Tests: `test_registry.py` — must include a test that successfully loads each grammar (Python, TypeScript, TSX, JavaScript, JSX) and creates a parser from it

### Task 3: Python parser
- `ast_parser/python_parser.py` — tree-sitter queries for Python
- Test fixtures: `fixtures/simple_module.py`, `fixtures/classes_and_functions.py`, etc.
- Tests: `test_python_parser.py`

### Task 4: TypeScript parser
- `ast_parser/typescript_parser.py` — tree-sitter queries for TS/TSX
- Test fixtures: `fixtures/simple_module.ts`, etc.
- Tests: `test_typescript_parser.py`

### Task 5: JavaScript parser
- `ast_parser/javascript_parser.py` — tree-sitter queries for JS/JSX
- Test fixtures: `fixtures/simple_module.js`, etc.
- Tests: `test_javascript_parser.py`

### Task 6: Public API, config integration, and integration tests
- `ast_parser/__init__.py` — `parse_interface()`, `hash_interface()`, `compute_hashes()`
- `config/schema.py` — add `ASTConfig`
- `config/defaults.py` — add `ast:` section
- Tests: `test_hash_interface.py`, integration tests
- Consolidate `indexer/generator.py` inline hash to use `hash_string()`

---

## Concerns and Risks

### Concern: tree-sitter-typescript Python API

**Severity:** Blocking — must be resolved in Task 2 before Tasks 3–5 proceed.

**Problem:** The `tree-sitter-typescript` package bundles two separate grammars: one for TypeScript (`.ts`) and one for TSX (`.tsx`). The JavaScript-side API exposes these as `require('tree-sitter-typescript').typescript` and `require('tree-sitter-typescript').tsx`. However, the **Python-side API is undocumented** on both PyPI and in the py-tree-sitter docs. We do not know:

1. **How to import the sub-grammars in Python.** The standard pattern for single-grammar packages is:
   ```python
   import tree_sitter_python as tspython
   from tree_sitter import Language
   PY_LANGUAGE = Language(tspython.language())
   ```
   But `tree-sitter-typescript` contains *two* grammars. Does the Python package expose `tree_sitter_typescript.language_typescript()` and `tree_sitter_typescript.language_tsx()`? Or `tree_sitter_typescript.typescript.language()` and `tree_sitter_typescript.tsx.language()`? Or some other pattern entirely? The PyPI page doesn't say.

2. **Whether TSX and TypeScript parsers share any state.** They are separate grammars but shipped in one package. We need to confirm that two independent `Parser` instances (one per grammar) work concurrently without conflict.

3. **Whether `tree-sitter-javascript` handles JSX natively** or if JSX requires the TSX grammar from `tree-sitter-typescript`. The tree-sitter-javascript grammar README claims JSX support, but this needs runtime verification.

4. **Version compatibility.** `tree-sitter-typescript` is at 0.23.2 while the core `tree-sitter` is at 0.25.2. The py-tree-sitter docs state `LANGUAGE_VERSION = 15` and `MIN_COMPATIBLE_LANGUAGE_VERSION = 13`. We need to confirm the 0.23.x grammar packages produce language versions within this compatible range.

**Spike procedure (Task 2, do first):**

```bash
# 1. Install in an isolated env
uv venv /tmp/ts-spike && source /tmp/ts-spike/bin/activate
uv pip install "tree-sitter>=0.25.0,<0.26.0" \
               "tree-sitter-typescript>=0.23.0,<0.24.0" \
               "tree-sitter-javascript>=0.25.0,<0.26.0" \
               "tree-sitter-python>=0.25.0,<0.26.0"

# 2. Explore the module's public API
python -c "import tree_sitter_typescript; print(dir(tree_sitter_typescript))"

# 3. Try likely import patterns
python -c "
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

# Pattern A: top-level function with name
try:
    ts_lang = Language(tsts.language_typescript())
    print('Pattern A (language_typescript) works')
except Exception as e:
    print(f'Pattern A failed: {e}')

# Pattern B: sub-module access
try:
    ts_lang = Language(tsts.typescript.language())
    print('Pattern B (typescript.language) works')
except Exception as e:
    print(f'Pattern B failed: {e}')

# Pattern C: generic language() returning TS by default
try:
    ts_lang = Language(tsts.language())
    print('Pattern C (language) works — but which grammar is it?')
except Exception as e:
    print(f'Pattern C failed: {e}')
"

# 4. Repeat for TSX
python -c "
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

# Try TSX variants
for attr in ['language_tsx', 'tsx']:
    try:
        fn = getattr(tsts, attr)
        if callable(fn):
            lang = Language(fn() if callable(fn) else fn)
            print(f'TSX via tsts.{attr}() works')
    except Exception as e:
        print(f'TSX via tsts.{attr} failed: {e}')
"

# 5. Verify JS + JSX
python -c "
import tree_sitter_javascript as tsjs
from tree_sitter import Language, Parser

lang = Language(tsjs.language())
parser = Parser(lang)
# Test plain JS
tree = parser.parse(b'function foo() { return 1; }')
print(f'JS parse: {tree.root_node.type}')
# Test JSX
tree = parser.parse(b'const App = () => <div>hello</div>;')
print(f'JSX parse: {tree.root_node.type}, errors: {tree.root_node.has_error}')
"

# 6. Verify version compatibility
python -c "
import tree_sitter
print(f'tree-sitter LANGUAGE_VERSION: {tree_sitter.LANGUAGE_VERSION}')
print(f'MIN_COMPATIBLE: {tree_sitter.MIN_COMPATIBLE_LANGUAGE_VERSION}')
"
```

**Outcomes and fallbacks:**

- **If the spike succeeds:** Document the working import patterns in `registry.py` as comments. Proceed to Tasks 3–5.
- **If TypeScript grammar is version-incompatible:** Pin to a different `tree-sitter` core version, or drop TypeScript from Phase 3 MVP and add it when the grammar catches up. Python parser is unaffected.
- **If TSX sub-grammar cannot be loaded separately:** Use the TypeScript grammar for both `.ts` and `.tsx` files. TSX-specific nodes (JSX elements) appear in function bodies which we don't parse anyway, so this may work transparently.
- **If `tree-sitter-javascript` doesn't handle JSX:** Route `.jsx` files through the TSX grammar from `tree-sitter-typescript` instead. Update `GRAMMAR_MAP` accordingly.

---

### Risk: Missing type stubs for grammar packages

| Impact | Mitigation |
|--------|------------|
| mypy strict mode errors on all grammar imports | Add `# type: ignore[import-untyped]` on grammar import lines. These are C extension modules that will never ship type stubs. Alternatively, add a `py.typed` marker stub file in the project. Acceptable trade-off — no runtime impact. |

### Risk: Skeleton rendering format is a hash contract

| Impact | Mitigation |
|--------|------------|
| Changing the canonical rendering format invalidates every existing interface hash in every project using Lexibrary. All design files would appear "interface changed" on next `lexi update`, triggering unnecessary full regenerations. | Version the rendering format. Prefix the canonical text with a format version line (e.g., `skeleton:v1\n`) before hashing. When the format changes, bump to `v2`. Phase 4's change detector can then distinguish "format changed" from "interface changed" and handle the migration (one-time full regen is acceptable on version bump, false "changed" on every file is not). |

### Risk: `__all__` parsing is imprecise

| Impact | Mitigation |
|--------|------------|
| Python's `__all__` is a runtime value. Dynamic modifications (`__all__ += [...]`, `__all__.extend(...)`) can't be statically extracted, leading to incomplete or incorrect export lists. | Extract only literal list/tuple assignments to `__all__` (e.g., `__all__ = ["Foo", "Bar"]`). Ignore dynamic modifications. This covers the overwhelming majority of real-world usage. Log a debug-level note when `__all__` is detected but can't be statically resolved, so users can identify edge cases. |

### Risk: JSX/TSX element parsing performance

| Impact | Mitigation |
|--------|------------|
| Large JSX/TSX files could slow extraction if the parser descends into component render trees. | The parser design already mitigates this — we only visit top-level declarations and class-level members. Function bodies (where JSX lives) are never descended into. Tree-sitter queries target specific node types at specific tree depths, not the entire tree. No additional mitigation needed. |

---

## Open Questions (Resolved)

These were raised before planning and have been settled:

| Question | Resolution |
|----------|------------|
| Which languages at launch? | Python + TypeScript + JavaScript (D-007) |
| CLI command? | No — library module only (D-008) |
| Skeleton detail level? | Signatures only (D-009) |
| Grammar distribution? | Optional extras group `lexibrary[ast]` (D-010) |

---

## Out of Scope for Phase 3

- **LLM integration** — Phase 4 (Archivist) handles this
- **Design file generation** — Phase 4
- **Reverse dependency indexing** — Phase 4
- **`lexi update` CLI wiring** — Phase 4
- **Additional languages beyond Py/TS/JS** — future phases, on demand
- **Import/dependency extraction** — Phase 4 (different from interface extraction)
