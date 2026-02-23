## Why

Lexibrary needs LLM-powered summarization to generate file and directory descriptions for `.aindex` files. Without this, the indexer can only produce structural metadata. BAML provides type-safe, provider-agnostic prompt definitions with a generated client, enabling structured LLM responses without manual parsing. This is Phase 4 of the build plan and depends on Phase 1 (config schema for `LLMConfig`).

## What Changes

- Initialize BAML in `baml_src/` with client definitions for Anthropic, OpenAI, and Ollama
- Define BAML types (`FileSummary`, `FileInput`, `BatchFileSummary`) and functions (`SummarizeFile`, `SummarizeFilesBatch`, `SummarizeDirectory`)
- Generate `baml_client/` inside `src/lexibrary/` with typed async/sync Python clients
- Add `src/lexibrary/llm/` package with `LLMService` (async wrapper), `RateLimiter` (token-bucket), and `create_llm_service` factory (runtime provider switching via config)
- Add `src/lexibrary/utils/languages.py` for file extension to language detection
- Add tests for rate limiter, LLM service (mocked), and language detection

## Capabilities

### New Capabilities
- `llm-summarization`: BAML prompt definitions, generated client, async LLM service wrapper with rate limiting, provider factory, and language detection utility
- `rate-limiting`: Token-bucket async rate limiter for LLM API call throttling

### Modified Capabilities
- `config-system`: No spec-level requirement changes — `LLMConfig` already defines provider, model, api_key_env, and related fields. The factory reads these at runtime but doesn't alter the config schema.

## Impact

- **New dependency**: `baml-py` (already in `pyproject.toml`)
- **New directories**: `baml_src/` (BAML source), `src/lexibrary/baml_client/` (generated), `src/lexibrary/llm/` (service layer)
- **New utility**: `src/lexibrary/utils/languages.py`
- **Environment variables**: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` read by BAML clients
- **Tests**: `tests/test_llm/` (rate limiter, service, language detection)
- **Phase**: 4 — independent of Phase 2 (crawl) and Phase 3 (output), depends on Phase 1 (config)
