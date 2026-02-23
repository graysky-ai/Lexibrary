## 1. BAML Setup and Configuration

- [x] 1.1 Run `uv run baml init` to scaffold `baml_src/` directory
- [x] 1.2 Create/update `baml_src/generators.baml` with output_type "python/pydantic" targeting `../src/lexibrary/baml_client`

## 2. BAML Definitions

- [x] 2.1 Create `baml_src/clients.baml` with AnthropicClient, OpenAIClient, and OllamaClient definitions
- [x] 2.2 Create `baml_src/types.baml` with FileSummary, FileInput, and BatchFileSummary class definitions
- [x] 2.3 Create `baml_src/summarize_file.baml` with SummarizeFile function
- [x] 2.4 Create `baml_src/summarize_files_batch.baml` with SummarizeFilesBatch function
- [x] 2.5 Create `baml_src/summarize_directory.baml` with SummarizeDirectory function

## 3. Generate BAML Client

- [x] 3.1 Run `uv run baml generate` and verify it succeeds
- [x] 3.2 Verify `src/lexibrary/baml_client/` is created with async_client.py, sync_client.py, and type definitions

## 4. Rate Limiter

- [x] 4.1 Create `src/lexibrary/llm/` package with `__init__.py`
- [x] 4.2 Implement `src/lexibrary/llm/rate_limiter.py` with async token-bucket RateLimiter class (configurable RPM, asyncio.Lock serialization)

## 5. LLM Service

- [x] 5.1 Implement `src/lexibrary/llm/service.py` with LLMService class, FileSummaryRequest, FileSummaryResult, and DirectorySummaryRequest dataclasses
- [x] 5.2 Implement `summarize_file()` async method with rate limiting and error fallback
- [x] 5.3 Implement `summarize_files_batch()` async method with rate limiting and error fallback
- [x] 5.4 Implement `summarize_directory()` async method with rate limiting and error fallback

## 6. Factory and Provider Switching

- [x] 6.1 Implement `src/lexibrary/llm/factory.py` with `create_llm_service()` that configures env vars based on LLMConfig provider
- [x] 6.2 Update `src/lexibrary/llm/__init__.py` with public exports

## 7. Language Detection Utility

- [x] 7.1 Implement `src/lexibrary/utils/languages.py` with EXTENSION_MAP and `detect_language()` function

## 8. Tests

- [x] 8.1 Create `tests/test_llm/test_rate_limiter.py` with tests for immediate first call, interval enforcement, and concurrent serialization
- [x] 8.2 Create `tests/test_llm/test_service.py` with mocked tests for summarize_file, summarize_files_batch, summarize_directory (success and error fallback cases)
- [x] 8.3 Create `tests/test_llm/test_languages.py` with tests for known extensions, special filenames, and unknown extensions
- [x] 8.4 Run full test suite `uv run pytest tests/test_llm -v` and verify all tests pass

## 9. Validation

- [x] 9.1 Verify `from lexibrary.baml_client.async_client import b` import works
- [x] 9.2 Run `uv run ruff check src/ tests/` and fix any lint issues
- [x] 9.3 Run `uv run mypy src/` and fix any type errors
