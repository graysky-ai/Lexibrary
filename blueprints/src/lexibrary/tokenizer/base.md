# tokenizer/base

**Summary:** `TokenCounter` Protocol (PEP 544 structural subtyping) that all token counter backends must satisfy.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `TokenCounter` | `Protocol` | Structural interface for all backends |
| `TokenCounter.count` | `(text: str) -> int` | Count tokens in a string |
| `TokenCounter.count_file` | `(path: Path) -> int` | Count tokens in a file |
| `TokenCounter.name` | `@property -> str` | Human-readable backend identifier |

## Dependents

- `lexibrarian.tokenizer.__init__` — re-exports
- `lexibrarian.tokenizer.factory` — used as return type
- `lexibrarian.crawler.engine` — typed parameter

## Key Concepts

- Structural subtyping: backends do NOT need to inherit from `TokenCounter`
- File reading should use `encoding="utf-8", errors="replace"` to handle mixed-charset files
