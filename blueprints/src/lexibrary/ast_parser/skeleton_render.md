# ast_parser/skeleton_render

**Summary:** Renders an `InterfaceSkeleton` into a deterministic, byte-identical canonical text string suitable for SHA-256 hashing.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `render_skeleton` | `(skeleton: InterfaceSkeleton) -> str` | Produce canonical text for a skeleton |
| `VERSION_PREFIX` | `str = "skeleton:v1"` | First line of every rendered output — bump when format changes |

## Dependencies

- `ast_parser.models` — `InterfaceSkeleton`, `ClassSig`, `ConstantSig`, `FunctionSig`, `ParameterSig`

## Dependents

- `ast_parser.__init__` — `hash_interface` calls `render_skeleton` before hashing

## Key Concepts

- All lists sorted alphabetically by name before rendering — declaration order in source is irrelevant
- Fixed section order: constants → functions → classes → exports
- Format lines:
  - Constant: `const:NAME` or `const:NAME:TYPE`
  - Function: `[modifiers ]func:NAME(params)->RETURN`
  - Class header: `class:NAME` or `class:NAME(base1,base2)`
  - Class members indented with two spaces
  - Export: `export:NAME`
- Incrementing `VERSION_PREFIX` from `v1` invalidates all cached interface hashes — coordinate with AIndexEntry schema
