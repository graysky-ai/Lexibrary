# archivist/service

**Summary:** Async LLM service that generates design files and START_HERE content via BAML, with provider routing and rate limiting.

## Interface

| Name | Signature | Purpose |
| --- | --- | --- |
| `DesignFileRequest` | `@dataclass` | Request with `source_path`, `source_content`, optional `interface_skeleton`, `language`, `existing_design_file` |
| `DesignFileResult` | `@dataclass` | Result with `source_path`, optional `design_file_output`, `error`, `error_message` |
| `StartHereRequest` | `@dataclass` | Request with `project_name`, `directory_tree`, `aindex_summaries`, optional `existing_start_here` |
| `StartHereResult` | `@dataclass` | Result with optional `start_here_output`, `error`, `error_message` |
| `ArchivistService` | `class` | Stateless async service routing BAML calls to provider-specific clients |
| `ArchivistService.__init__` | `(rate_limiter, config: LLMConfig)` | Set up provider client mapping |
| `ArchivistService.generate_design_file` | `async (request) -> DesignFileResult` | Generate design file via BAML; never raises on LLM failure |
| `ArchivistService.generate_start_here` | `async (request) -> StartHereResult` | Generate START_HERE via BAML; never raises on LLM failure |

## Dependencies

- `lexibrarian.baml_client.async_client` -- `BamlAsyncClient`, `b` (default client)
- `lexibrarian.baml_client.types` -- `DesignFileOutput`, `StartHereOutput`
- `lexibrarian.config.schema` -- `LLMConfig`
- `lexibrarian.llm.rate_limiter` -- `RateLimiter`

## Dependents

- `lexibrarian.archivist.pipeline` -- uses `ArchivistService.generate_design_file`
- `lexibrarian.archivist.start_here` -- uses `ArchivistService.generate_start_here`
- `lexibrarian.cli` -- instantiates `ArchivistService` in `update` command

## Key Concepts

- Provider routing: maps `config.provider` ("anthropic" / "openai") to BAML client names (`AnthropicArchivist` / `OpenAIArchivist`) via `_PROVIDER_CLIENT_MAP`
- Falls back to default BAML client if provider is not mapped
- Rate limiter `acquire()` called before every LLM call
- Error handling: catches all exceptions and returns error results (never raises)
