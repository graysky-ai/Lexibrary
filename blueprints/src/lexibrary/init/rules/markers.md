# init/rules/markers

**Summary:** Marker-based section detection and replacement for agent rule files -- manages Lexibrary-owned sections in shared files (CLAUDE.md, AGENTS.md) using HTML comment markers without disturbing user content.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `MARKER_START` | `str = "<!-- lexibrary:start -->"` | Opening HTML comment marker |
| `MARKER_END` | `str = "<!-- lexibrary:end -->"` | Closing HTML comment marker |
| `has_lexibrary_section` | `(content: str) -> bool` | Return `True` if content contains both start and end markers |
| `replace_lexibrary_section` | `(content: str, new_section: str) -> str` | Replace marker-delimited section with new content; preserves everything outside markers |
| `append_lexibrary_section` | `(content: str, new_section: str) -> str` | Append marker-delimited section to end of content with blank line separator |

## Dependencies

- None (only `re`)

## Dependents

- `lexibrary.init.rules.claude` -- uses all three functions for CLAUDE.md management
- `lexibrary.init.rules.codex` -- uses all three functions for AGENTS.md management

## Key Concepts

- Markers are HTML comments, invisible in rendered markdown but preserved in source
- `replace_lexibrary_section()` uses regex (`_SECTION_RE`) with `re.DOTALL` to match everything between markers including newlines
- `append_lexibrary_section()` adds a blank line before the marker block when appending to non-empty content
- `_wrap_in_markers()` is the internal helper that wraps content between `MARKER_START` and `MARKER_END`
