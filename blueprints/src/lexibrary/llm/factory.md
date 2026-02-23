# llm/factory

**Summary:** Creates a configured `LLMService` from `LLMConfig`, injecting the provider API key into the environment for the BAML client.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `create_llm_service` | `(config: LLMConfig) -> LLMService` | Build `LLMService` with `RateLimiter`; set provider env var |

## Dependencies

- `lexibrary.config.schema` — `LLMConfig`
- `lexibrary.llm.rate_limiter` — `RateLimiter`
- `lexibrary.llm.service` — `LLMService`

## Dependents

- `lexibrary.llm.__init__` — re-exports `create_llm_service`
- `lexibrary.daemon.service` — calls `create_llm_service(config.llm)`

## Key Concepts

- Uses `os.environ.setdefault` so an already-set env var is not overridden
- `_PROVIDER_ENV_KEYS` maps `"anthropic"` → `ANTHROPIC_API_KEY`, `"openai"` → `OPENAI_API_KEY`; ollama needs no key
