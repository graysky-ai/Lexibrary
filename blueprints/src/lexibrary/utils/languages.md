# utils/languages

**Summary:** Maps filenames and extensions to programming language names for LLM context hints.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `detect_language` | `(filename: str) -> str` | Return language string; checks special filenames first, then extension, then dotfile heuristic |
| `EXTENSION_MAP` | `dict[str, str]` | Extension → language name (40+ entries including `.baml`) |
| `SPECIAL_FILENAMES` | `dict[str, str]` | Exact filename → language (Dockerfile, Makefile, etc.) |

## Dependents

- `lexibrarian.crawler.engine` — calls `detect_language(fp.name)` for each file summarization request

## Key Concepts

- Dotfiles with no extension (e.g. `.gitignore`) return `"Config"`
- Unknown extensions return `"Text"`
