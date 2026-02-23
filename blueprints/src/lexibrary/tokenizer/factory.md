# tokenizer/factory

**Summary:** Creates the correct `TokenCounter` backend from `TokenizerConfig` using lazy imports so only selected backend dependencies are loaded.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `create_tokenizer` | `(config: TokenizerConfig) -> TokenCounter` | Match `config.backend` to `"tiktoken"`, `"anthropic_api"`, or `"approximate"` |

## Dependencies

- `lexibrary.config.schema` — `TokenizerConfig` (**not yet defined in schema**)
- `lexibrary.tokenizer.base` — `TokenCounter`

## Dependents

- `lexibrary.tokenizer.__init__` — re-exports
- `lexibrary.daemon.service` — calls `create_tokenizer(config.tokenizer)`

## Dragons

- `TokenizerConfig` is imported but not yet present in `config/schema.py` — will raise `ImportError` until added
- Raises `ValueError` for unrecognized backend names
