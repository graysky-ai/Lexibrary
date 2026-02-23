# ast_parser/python_parser

**Summary:** Extracts public interface skeletons from Python source files using tree-sitter; handles syntax errors gracefully by returning a partial skeleton.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `extract_interface` | `(file_path: Path) -> InterfaceSkeleton \| None` | Parse a `.py` or `.pyi` file; returns `None` if grammar unavailable or file unreadable |

## Dependencies

- `ast_parser.models` — all sig types
- `ast_parser.registry` — `get_parser`

## Dependents

- `ast_parser.__init__` — dispatched to via `_EXTRACTOR_MAP["python"]`

## Key Concepts

- **Public name filter:** names starting with `_` are excluded except `__init__` and `__new__`
- **Constants:** UPPER_CASE names or type-annotated assignments at module level
- **`__all__`:** literal list/tuple only — dynamic `__all__` is ignored
- **Decorators:** only `staticmethod`, `classmethod`, `property` affect the skeleton (sets `is_static`, `is_class_method`, `is_property` on `FunctionSig`); other decorators are ignored
- **`self`/`cls` parameters** are skipped for methods
- Tree-sitter node access uses `getattr` throughout — avoids importing `tree_sitter.Node` at module level, keeping the grammar dependency optional
