# ast_parser/registry

**Summary:** Maps file extensions to tree-sitter `Language` and `Parser` objects with lazy loading, process-lifetime caching, and graceful fallback when grammar packages are absent.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `GrammarInfo` | frozen dataclass | Metadata for one grammar: `language_name`, `module_name`, `loader`, `pip_package` |
| `GRAMMAR_MAP` | `dict[str, GrammarInfo]` | Extension → grammar info; covers `.py`, `.pyi`, `.ts`, `.tsx`, `.js`, `.jsx` |
| `get_grammar_info` | `(extension: str) -> GrammarInfo \| None` | Look up grammar info by extension |
| `get_language` | `(extension: str) -> Language \| None` | Lazily load and cache `tree_sitter.Language` |
| `get_parser` | `(extension: str) -> Parser \| None` | Lazily load and cache `tree_sitter.Parser` |
| `get_supported_extensions` | `() -> list[str]` | Sorted list of all registered extensions |
| `clear_caches` | `() -> None` | Clear language/parser caches — for testing |

## Dependencies

- `tree_sitter` — `Language`, `Parser` (TYPE_CHECKING only at module level; imported lazily in functions)
- `tree_sitter_python`, `tree_sitter_typescript`, `tree_sitter_javascript` — optional grammar packages
- `rich.console.Console` — `stderr=True` console for install warnings

## Dependents

- `ast_parser.__init__` — imports `GRAMMAR_MAP`
- `ast_parser.python_parser` — calls `get_parser`
- `ast_parser.typescript_parser` — calls `get_parser`
- `ast_parser.javascript_parser` — calls `get_parser`

## Key Concepts

- Caches keyed by `language_name` (not extension), so `.ts` and `.tsx` share one parser
- Missing grammar package: emits a one-time `rich` warning per language per process, then returns `None`
- `tree_sitter` import is lazy (inside functions) — the registry can be imported even if `tree_sitter` is not installed
- py-tree-sitter 0.25 API: `Language(raw_ptr)`, `Parser(language)` — **not** the older `Language.build_library` / `set_language` API
