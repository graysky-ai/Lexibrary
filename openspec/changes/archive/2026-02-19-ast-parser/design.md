## Context

Lexibrary currently detects file changes via SHA-256 content hashing. Any byte change — even a comment edit or function body refactor — triggers a full design file regeneration in Phase 4. This is wasteful: most edits don't change the public interface. Phase 3 adds AST-based interface extraction so Phase 4 can distinguish "interface changed" from "internals only changed."

The project uses tree-sitter for parsing because it handles syntax errors gracefully (partial trees), supports multiple languages through a unified API, and is already a well-established choice for this kind of structural analysis.

## Goals / Non-Goals

**Goals:**
- Extract public interface skeletons from Python, TypeScript, and JavaScript source files
- Produce deterministic, hashable canonical representations of interfaces
- Provide a two-tier hashing API: content hash (full file) + interface hash (public signatures only)
- Integrate cleanly as a library module consumed by Phase 4's Archivist
- Handle missing grammars gracefully (optional dependency group)

**Non-Goals:**
- No CLI commands (library module only)
- No LLM integration (Phase 4)
- No design file generation (Phase 4)
- No import/dependency extraction (Phase 4)
- No languages beyond Python, TypeScript, JavaScript
- No decorator text extraction (only structural modifiers like staticmethod/classmethod/property)

## Decisions

### D-007: Three languages at launch (Python, TypeScript, JavaScript)
These cover the majority of codebases Lexibrary targets. Each maps to established tree-sitter grammar packages. Adding more languages later follows the same pattern (new parser module + registry entry).

**Alternatives considered:** Python-only (too limited), adding Go/Rust (delays delivery without proportional value for MVP).

### D-008: Library module only, no CLI surface
Phase 3 is purely internal plumbing. Phase 4 wires it into `lexi update`. Adding a CLI command now would be premature — the interface is not user-facing.

### D-009: Signatures only — no decorators, docstrings, or body logic
The skeleton captures the **calling convention**: function names, parameter names/types/defaults, return types, class names, base classes, and structural modifiers (async, static, classmethod, property). Decorators are text metadata, not calling convention — excluded. Docstrings and bodies are implementation detail — excluded.

**Alternative considered:** Including decorator names (e.g., `@cached_property`). Rejected because decorator semantics vary wildly and including them would cause false "interface changed" signals when decorators are added/removed for non-API reasons.

### D-010: Optional extras group for grammars
Grammar packages are C extensions (~5-10MB each). They should not be in base deps since many users won't need AST parsing. `pip install lexibrary[ast]` installs them. The registry returns `None` gracefully when grammars are missing.

### Skeleton rendering is versioned
The canonical text format is prefixed with `skeleton:v1\n`. This means changing the format in the future bumps to `v2` and Phase 4 can distinguish "format changed" from "interface changed," avoiding false mass-regeneration.

### Alphabetical sorting for determinism
All lists in the skeleton (functions, classes, constants, methods, exports) are sorted alphabetically by name before rendering. Reordering declarations in source code does not change the interface hash.

## Risks / Trade-offs

### tree-sitter-typescript Python API is undocumented
**Risk:** The package bundles TypeScript + TSX as two sub-grammars. The Python import pattern is not documented on PyPI or in py-tree-sitter docs.
**Mitigation:** Task 2 includes a mandatory spike to verify the import pattern before any TS/JS parser work begins. Fallback: if sub-grammars can't be loaded separately, use TypeScript grammar for both `.ts` and `.tsx` (JSX in function bodies is never parsed anyway).

### Version lag in tree-sitter-typescript (0.23.x vs core 0.25.x)
**Risk:** Potential ABI incompatibility between grammar and core library versions.
**Mitigation:** Spike verifies compatibility via `LANGUAGE_VERSION` / `MIN_COMPATIBLE_LANGUAGE_VERSION` check. Fallback: pin core to compatible version or defer TypeScript support.

### Skeleton format is a hash contract
**Risk:** Changing the rendering format invalidates all existing interface hashes, causing unnecessary full regenerations.
**Mitigation:** Version prefix (`skeleton:v1\n`) in canonical text. Format changes bump version. Phase 4 detects version mismatch and handles one-time regen gracefully.

### `__all__` parsing is imprecise
**Risk:** Dynamic `__all__` modifications (`__all__ += [...]`) can't be statically extracted.
**Mitigation:** Only extract literal list/tuple assignments. This covers the vast majority of real-world usage. Debug-level logging when `__all__` is detected but can't be resolved.

### Missing type stubs for grammar packages
**Risk:** mypy strict mode errors on grammar imports (C extension modules without stubs).
**Mitigation:** `# type: ignore[import-untyped]` on grammar import lines. No runtime impact.
