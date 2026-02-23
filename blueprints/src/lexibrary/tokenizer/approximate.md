# tokenizer/approximate

**Summary:** Zero-dependency token counter estimating tokens as `len(text) / 4`; ~20% error margin, suitable as fallback or for development.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `ApproximateCounter` | class | Implements `TokenCounter` via char/4 heuristic |
| `ApproximateCounter.count` | `(text: str) -> int` | `max(1, int(len(text) / 4))` |
| `ApproximateCounter.count_file` | `(path: Path) -> int` | Read file then count |
| `ApproximateCounter.name` | `@property -> str` | `"approximate (chars/4)"` |

## Dependents

- `lexibrarian.tokenizer.factory` — selected when `config.backend == "approximate"`
