# tokenizer/anthropic_counter

**Summary:** Token counter using the Anthropic `count_tokens` API for Claude-accurate counts; requires `ANTHROPIC_API_KEY`.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `AnthropicCounter` | class | Anthropic API-backed `TokenCounter` |
| `AnthropicCounter.__init__` | `(model: str = "claude-sonnet-4-5-20250514")` | Create `anthropic.Anthropic()` client |
| `AnthropicCounter.count` | `(text: str) -> int` | POST to count_tokens API; returns `response.input_tokens` |
| `AnthropicCounter.count_file` | `(path: Path) -> int` | Read then count |
| `AnthropicCounter.name` | `@property -> str` | `"anthropic (<model>)"` |

## Dependents

- `lexibrarian.tokenizer.factory` — selected when `config.backend == "anthropic_api"`

## Dragons

- Makes a network API call per `count()` invocation — slow for large batches; use `approximate` or `tiktoken` for performance-sensitive paths
- Requires `ANTHROPIC_API_KEY` env var; will raise if missing
