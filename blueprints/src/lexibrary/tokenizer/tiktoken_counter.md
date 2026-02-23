# tokenizer/tiktoken_counter

**Summary:** Fast offline token counter using OpenAI's tiktoken BPE library; encoding downloaded and cached on first use.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `TiktokenCounter` | class | tiktoken-backed `TokenCounter` |
| `TiktokenCounter.__init__` | `(model: str = "cl100k_base")` | Load BPE encoding (may download on first call) |
| `TiktokenCounter.count` | `(text: str) -> int` | `len(encoding.encode(text))` |
| `TiktokenCounter.count_file` | `(path: Path) -> int` | Read then count |
| `TiktokenCounter.name` | `@property -> str` | `"tiktoken (<model>)"` |

## Dependents

- `lexibrarian.tokenizer.factory` — selected when `config.backend == "tiktoken"`

## Key Concepts

- `model` is the encoding name (e.g. `"cl100k_base"`), not an OpenAI model name
