# ast_parser/typescript_parser

**Summary:** Extracts public interface skeletons from TypeScript (`.ts`) and TSX (`.tsx`) files using tree-sitter; covers functions, classes, interfaces, type aliases, enums, and export declarations.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `extract_interface` | `(file_path: Path) -> InterfaceSkeleton \| None` | Parse a `.ts` or `.tsx` file; returns `None` for wrong extension, missing grammar, or read error |

## Dependencies

- `ast_parser.models` — all sig types
- `ast_parser.registry` — `get_parser`

## Dependents

- `ast_parser.__init__` — dispatched to via `_EXTRACTOR_MAP["typescript"]` and `_EXTRACTOR_MAP["tsx"]`

## Key Concepts

- Uses `.tsx` sub-grammar (via `tree_sitter_typescript.language_tsx()`) for `.tsx` files, TypeScript sub-grammar for `.ts`
- **Interfaces** represented as `ClassSig` (same model as classes, for uniformity)
- **Enums** represented as `ClassSig` with members as `class_variables`
- **Type aliases** represented as `ConstantSig` with `type_annotation` set to the RHS type
- Arrow functions assigned to `const` are **not** extracted as functions (only as constants or skipped) — unlike the JavaScript parser
- Export tracking: names in `export { ... }`, `export function`, `export class`, `export default`, `export const` are all captured in `exports`
- Node access uses `getattr` (not direct `tree_sitter.Node` attribute access) for optional-dependency safety
