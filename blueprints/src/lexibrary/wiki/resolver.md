# wiki/resolver

**Summary:** Resolves `[[wikilink]]` strings against a `ConceptIndex` and an optional stack directory, returning typed `ResolvedLink` or `UnresolvedLink` results; supports stack post references (`ST-NNN`), exact/alias concept matches, and fuzzy matching.

## Interface

| Name | Key Fields / Signature | Purpose |
| --- | --- | --- |
| `ResolvedLink` | `raw`, `name`, `kind: "concept" \| "stack" \| "alias"`, `path: Path \| None` | A wikilink successfully resolved |
| `UnresolvedLink` | `raw`, `suggestions: list[str]` | A wikilink that could not be resolved (with up to 3 fuzzy suggestions) |
| `WikilinkResolver` | `class` | Resolves wikilinks against a `ConceptIndex` and optional `stack_dir` |
| `WikilinkResolver.__init__` | `(index: ConceptIndex, stack_dir: Path \| None = None)` | Constructor accepting concept index and optional stack directory |
| `WikilinkResolver.resolve` | `(raw: str) -> ResolvedLink \| UnresolvedLink` | Resolve a single wikilink string |
| `WikilinkResolver.resolve_all` | `(links: list[str]) -> tuple[list[ResolvedLink], list[UnresolvedLink]]` | Batch resolve; returns separated resolved/unresolved lists |

## Resolution Chain

1. Strip `[[` / `]]` brackets if present
2. Stack post pattern (`ST-NNN`) -- glob-based file lookup in `stack_dir` for `ST-NNN-*.md` files -> `ResolvedLink(kind="stack")` with path, or `UnresolvedLink` if no file found
3. Exact concept title match (case-insensitive) -> `ResolvedLink(kind="concept")`
4. Alias match (case-insensitive) -> `ResolvedLink(kind="alias")`
5. Fuzzy match via `difflib.get_close_matches` (cutoff 0.6, n=3) -> best match as `ResolvedLink`, or `UnresolvedLink` with suggestions

## Dependencies

- `lexibrarian.artifacts.concept` -- `ConceptFile`
- `lexibrarian.wiki.index` -- `ConceptIndex`

## Dependents

- `lexibrarian.wiki.__init__` -- re-exports
