# ast_parser

**Summary:** Public API for tree-sitter-based interface extraction — parses source files into `InterfaceSkeleton` models and computes content/interface hashes.

## Re-exports

| Name | Source | Purpose |
| --- | --- | --- |
| `InterfaceSkeleton` | `ast_parser.models` | Data model for a file's public interface |
| `parse_interface` | defined here | Extract public interface from a source file |
| `hash_interface` | defined here | SHA-256 hash of a skeleton's canonical rendering |
| `compute_hashes` | defined here | Return `(content_hash, interface_hash)` for a file |
| `render_skeleton` | `ast_parser.skeleton_render` | Render skeleton to deterministic canonical text |

## Key Concepts

- `parse_interface(file_path)` — resolves extension → grammar → parser module via `GRAMMAR_MAP` + `_EXTRACTOR_MAP`; returns `None` for unsupported types or import errors (optional deps)
- `compute_hashes(file_path)` — always returns `content_hash`; `interface_hash` is `None` when no grammar is available
- Parser modules are imported lazily via `importlib` so missing tree-sitter packages don't break core functionality

## Dependents

Nothing outside this package yet — intended to be called by `indexer.generator` when interface-hash support is added.
