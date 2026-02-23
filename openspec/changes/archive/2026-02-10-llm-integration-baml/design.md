## Context

Lexibrary's Phase 1 established the config schema (`LLMConfig` with provider, model, API key fields) and project scaffolding. Phase 4 adds the actual LLM integration layer that consumes this config to generate file and directory summaries. The system needs to call LLMs in a provider-agnostic way, parse structured responses, and handle errors gracefully.

BAML is already specified as the prompt framework in the project architecture. It provides `.baml` prompt definitions that compile to typed Python clients, eliminating manual JSON parsing and enabling provider switching via client registry.

## Goals / Non-Goals

**Goals:**
- BAML prompt definitions for file summarization (single, batch) and directory summarization
- Generated typed Python client for async LLM calls
- Thin service wrapper with error handling and fallback summaries
- Token-bucket rate limiter to respect provider API limits
- Factory function for runtime provider switching based on `LLMConfig`
- Language detection utility for file-to-language mapping

**Non-Goals:**
- Streaming responses (summaries are short, streaming adds no value)
- Prompt caching or response caching (deferred to integration with crawl in later phase)
- Custom retry logic beyond BAML's built-in retries
- Embedding or vector search functionality
- Token counting for prompt budgeting (handled by separate token-counting capability)

## Decisions

### D1: BAML for all prompt definitions
**Choice**: Define all prompts in `.baml` files, generate typed Python client.
**Why**: BAML provides type-safe structured output, provider-agnostic client switching, and a playground for testing. Alternatives like raw API calls or LangChain add unnecessary complexity or abstraction.

### D2: Three separate BAML functions (not one generic function)
**Choice**: `SummarizeFile`, `SummarizeFilesBatch`, `SummarizeDirectory` as distinct BAML functions.
**Why**: Each has different input shapes, output types, and prompt strategies. A generic function would require complex conditional prompting. Separate functions keep prompts focused and testable.

### D3: Async-first service layer
**Choice**: `LLMService` uses async methods wrapping the BAML async client.
**Why**: LLM calls are I/O-bound. The crawl system (Phase 2) will process many files concurrently. Async allows parallelism without threading complexity. The sync BAML client is available as fallback but not used in the service.

### D4: Token-bucket rate limiter
**Choice**: Simple async rate limiter with configurable RPM, using `asyncio.Lock` for serialization.
**Why**: Prevents hitting provider rate limits during batch processing. Token-bucket is simple, well-understood, and sufficient for single-process use. Alternative: leaky bucket — similar complexity, no practical benefit here.

### D5: Error fallback pattern
**Choice**: All service methods catch exceptions and return fallback summaries ("Summary unavailable") instead of propagating.
**Why**: A single file's LLM failure should not abort an entire crawl. The caller can check for fallback markers and retry later. This keeps the crawl pipeline resilient.

### D6: Provider switching via environment variables (initially)
**Choice**: Factory sets environment variables that BAML clients reference; full client registry switching deferred to testing against actual `baml-py` API.
**Why**: BAML reads `env.ANTHROPIC_API_KEY` at call time. Setting env vars is the simplest approach that works across all BAML versions. Client registry API may vary by version, so we start simple and upgrade.

### D7: Generated client committed to repo
**Choice**: Commit `src/lexibrary/baml_client/` rather than `.gitignore` it.
**Why**: Users who `pip install` the package don't need the BAML toolchain. The generated code is deterministic from `.baml` source. Developers re-run `baml-cli generate` after `.baml` changes.

## Risks / Trade-offs

- **[BAML version coupling]** Generated client depends on specific `baml-py` version → Pin `baml-py` version in `pyproject.toml`, re-generate on upgrade
- **[Rate limiter is per-process]** Doesn't coordinate across multiple CLI invocations → Acceptable for MVP; distributed rate limiting is a non-goal
- **[Batch function token limits]** Large batch requests may exceed model context window → Caller (crawl phase) is responsible for batching within `max_files_per_llm_batch` from config
- **[Ollama latency]** Local Ollama may be significantly slower than cloud APIs → Rate limiter interval will naturally throttle; no special handling needed
- **[Environment variable mutation]** Factory uses `os.environ.setdefault` which mutates global state → Acceptable for CLI tool (single-threaded entry point); not suitable for library use
