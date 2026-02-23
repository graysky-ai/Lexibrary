## ADDED Requirements

### Requirement: Extension-to-grammar mapping
The system SHALL maintain a mapping from file extensions to grammar information. The following extensions SHALL be supported: `.py`, `.pyi` (Python), `.ts`, `.tsx` (TypeScript), `.js`, `.jsx` (JavaScript).

#### Scenario: Python extension is mapped
- **WHEN** querying the registry for extension `.py`
- **THEN** it returns grammar info pointing to the `tree_sitter_python` module and the Python parser

#### Scenario: TypeScript extensions are mapped
- **WHEN** querying the registry for extensions `.ts` and `.tsx`
- **THEN** both return grammar info pointing to `tree_sitter_typescript` with the appropriate sub-grammar

#### Scenario: JavaScript extensions are mapped
- **WHEN** querying the registry for extensions `.js` and `.jsx`
- **THEN** both return grammar info pointing to `tree_sitter_javascript` and the JavaScript parser

#### Scenario: Unknown extension returns None
- **WHEN** querying the registry for extension `.rs`
- **THEN** it returns None

### Requirement: Lazy grammar loading
The system SHALL load tree-sitter Language objects and create Parser instances lazily on first use. Once loaded, Language and Parser objects SHALL be cached at module level for the lifetime of the process.

#### Scenario: Grammar is loaded on first access
- **WHEN** requesting the parser for `.py` for the first time
- **THEN** the system imports `tree_sitter_python`, creates a Language object, and caches it

#### Scenario: Subsequent access uses cache
- **WHEN** requesting the parser for `.py` a second time
- **THEN** the cached Language object is returned without re-importing

### Requirement: Graceful fallback on missing grammar
The system SHALL handle missing grammar packages gracefully. When a grammar package is not installed (`ImportError`), the registry SHALL return None and emit a warning via `rich.console.Console` indicating which package to install. The warning SHALL be emitted at most once per language per session.

#### Scenario: Missing grammar package returns None
- **WHEN** the `tree-sitter-python` package is not installed and the registry is queried for `.py`
- **THEN** it returns None

#### Scenario: Warning is emitted for missing grammar
- **WHEN** a grammar package is not installed and the registry is queried
- **THEN** a warning is printed: "tree-sitter-python not installed. Run: pip install lexibrary[ast]"

#### Scenario: Warning is emitted only once per language
- **WHEN** querying for `.py` twice with the grammar missing
- **THEN** the warning is only printed on the first query

### Requirement: Grammar loading uses py-tree-sitter 0.25 API
The system SHALL load grammars using the py-tree-sitter 0.25 API pattern: import the grammar module, call its `language()` function, wrap in `tree_sitter.Language()`, and create a `tree_sitter.Parser()` from it.

#### Scenario: Python grammar loads successfully
- **WHEN** `tree-sitter-python` is installed and the registry loads its grammar
- **THEN** a valid Parser is created that can parse Python source bytes

#### Scenario: TypeScript grammar loads both sub-grammars
- **WHEN** `tree-sitter-typescript` is installed and the registry loads its grammars
- **THEN** both TypeScript and TSX parsers are created successfully

#### Scenario: JavaScript grammar loads and handles JSX
- **WHEN** `tree-sitter-javascript` is installed and the registry loads its grammar
- **THEN** a valid Parser is created that can parse both plain JS and JSX source bytes
