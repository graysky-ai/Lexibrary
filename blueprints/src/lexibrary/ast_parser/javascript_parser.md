# ast_parser/javascript_parser

**Summary:** Extracts public interface skeletons from JavaScript (`.js`) and JSX (`.jsx`) files using tree-sitter; handles ES module exports and CommonJS `module.exports` patterns.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `extract_interface` | `(file_path: Path) -> InterfaceSkeleton \| None` | Parse a `.js` or `.jsx` file; returns `None` if grammar unavailable or file unreadable |

## Dependencies

- `ast_parser.models` — all sig types
- `ast_parser.registry` — `get_parser`

## Dependents

- `ast_parser.__init__` — dispatched to via `_EXTRACTOR_MAP["javascript"]`

## Key Concepts

- No type annotations in JavaScript — all `type_annotation` and `return_type` fields are `None`
- **Arrow functions** assigned to `const` are extracted as `FunctionSig` (unlike TypeScript parser which skips them)
- **Function expressions** assigned to `const` are also extracted as `FunctionSig`
- **CommonJS exports** handled: `module.exports = {...}`, `module.exports = Name`, `module.exports.name = ...`, `exports.name = ...`
- Logs a warning (not error) when tree-sitter detects syntax errors — extraction continues with partial results
- Uses `TYPE_CHECKING` guard for `tree_sitter.Node` type hints so the import is only used by type checkers
