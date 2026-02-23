# llm/service

**Summary:** Async `LLMService` wrapping the BAML-generated client with rate limiting, error logging, and fallback empty summaries.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `FileSummaryRequest` | `@dataclass` | Input: `path`, `content`, `language`, `is_truncated` |
| `FileSummaryResult` | `@dataclass` | Output: `path`, `summary`, `error: bool` |
| `DirectorySummaryRequest` | `@dataclass` | Input: `path`, `file_list`, `subdir_list` |
| `LLMService` | class | Async client wrapper |
| `LLMService.summarize_file` | `async (request: FileSummaryRequest) -> FileSummaryResult` | Single file; error returns `FileSummaryResult(error=True)` |
| `LLMService.summarize_files_batch` | `async (requests: list[FileSummaryRequest]) -> list[FileSummaryResult]` | Batch call; mismatch count marks all as errors |
| `LLMService.summarize_directory` | `async (request: DirectorySummaryRequest) -> str` | Returns summary string or `"Summary unavailable."` on error |

## Dependencies

- `lexibrarian.baml_client.async_client` — `b` (BAML async client)
- `lexibrarian.baml_client.types` — `FileInput`
- `lexibrarian.llm.rate_limiter` — `RateLimiter`

## Dependents

- `lexibrarian.crawler.engine` — calls all three methods
- `lexibrarian.llm.__init__` — re-exports dataclasses and class

## Dragons

- All exceptions are caught and logged; callers must check `result.error` to distinguish success from fallback
