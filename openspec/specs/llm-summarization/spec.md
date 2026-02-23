# llm-summarization Specification

## Purpose
TBD - created by archiving change llm-integration-baml. Update Purpose after archive.
## Requirements
### Requirement: BAML prompt definitions for summarization
The system SHALL define BAML prompt functions for `SummarizeFile`, `SummarizeFilesBatch`, and `SummarizeDirectory` in `baml_src/` with typed inputs and outputs.

#### Scenario: SummarizeFile prompt is defined
- **WHEN** `baml-cli generate` is run
- **THEN** a typed `SummarizeFile` function is available that accepts filename, language, content, and is_truncated parameters and returns a `FileSummary` with a summary string

#### Scenario: SummarizeFilesBatch prompt is defined
- **WHEN** `baml-cli generate` is run
- **THEN** a typed `SummarizeFilesBatch` function is available that accepts a list of `FileInput` objects and returns a list of `BatchFileSummary` objects

#### Scenario: SummarizeDirectory prompt is defined
- **WHEN** `baml-cli generate` is run
- **THEN** a typed `SummarizeDirectory` function is available that accepts dirname, file_list, and subdir_list strings and returns a summary string

### Requirement: BAML client definitions for multiple providers
The system SHALL define BAML client configurations for Anthropic, OpenAI, and Ollama providers in `baml_src/clients.baml`.

#### Scenario: Anthropic client is configured
- **WHEN** the BAML clients are defined
- **THEN** an `AnthropicClient` exists using the `anthropic` provider with `env.ANTHROPIC_API_KEY` and max_tokens of 200

#### Scenario: OpenAI client is configured
- **WHEN** the BAML clients are defined
- **THEN** an `OpenAIClient` exists using the `openai` provider with `env.OPENAI_API_KEY` and max_tokens of 200

#### Scenario: Ollama client is configured
- **WHEN** the BAML clients are defined
- **THEN** an `OllamaClient` exists using the `openai` provider with base_url `http://localhost:11434/v1` and max_tokens of 200

### Requirement: Generated BAML client importable from package
The system SHALL generate the BAML client into `src/lexibrary/baml_client/` so that it is importable as `from lexibrary.baml_client.async_client import b`.

#### Scenario: BAML client generation succeeds
- **WHEN** running `uv run baml-cli generate`
- **THEN** the command succeeds and creates `src/lexibrary/baml_client/` with async_client.py, sync_client.py, and type definitions

#### Scenario: Generated client is importable
- **WHEN** importing `from lexibrary.baml_client.async_client import b`
- **THEN** the import succeeds and `b` has methods `SummarizeFile`, `SummarizeFilesBatch`, and `SummarizeDirectory`

### Requirement: Single file summarization via LLMService
The system SHALL provide an `LLMService.summarize_file()` async method that accepts a `FileSummaryRequest` and returns a `FileSummaryResult` with a non-empty summary.

#### Scenario: Successful single file summarization
- **WHEN** calling `summarize_file()` with a valid `FileSummaryRequest` containing path, content, and language
- **THEN** it returns a `FileSummaryResult` with the file's path and a non-empty summary string

#### Scenario: LLM error produces fallback summary
- **WHEN** calling `summarize_file()` and the LLM call raises an exception
- **THEN** it returns a `FileSummaryResult` with summary "Summary unavailable (error)" and does not raise

### Requirement: Batch file summarization via LLMService
The system SHALL provide an `LLMService.summarize_files_batch()` async method that accepts a list of `FileSummaryRequest` objects and returns one `FileSummaryResult` per input.

#### Scenario: Successful batch summarization
- **WHEN** calling `summarize_files_batch()` with a list of `FileSummaryRequest` objects
- **THEN** it returns a list of `FileSummaryResult` objects with the same count as the input, each with a non-empty summary

#### Scenario: Empty batch returns empty list
- **WHEN** calling `summarize_files_batch()` with an empty list
- **THEN** it returns an empty list without making any LLM calls

#### Scenario: Batch LLM error produces fallback summaries
- **WHEN** calling `summarize_files_batch()` and the LLM call raises an exception
- **THEN** it returns fallback `FileSummaryResult` objects for all inputs with summary "Summary unavailable (error)"

### Requirement: Directory summarization via LLMService
The system SHALL provide an `LLMService.summarize_directory()` async method that accepts a `DirectorySummaryRequest` and returns a summary string.

#### Scenario: Successful directory summarization
- **WHEN** calling `summarize_directory()` with a `DirectorySummaryRequest` containing directory path, file_list, and subdir_list
- **THEN** it returns a non-empty string summarizing the directory's purpose

#### Scenario: Directory LLM error produces fallback
- **WHEN** calling `summarize_directory()` and the LLM call raises an exception
- **THEN** it returns "Summary unavailable." and does not raise

### Requirement: LLM service factory with provider switching
The system SHALL provide a `create_llm_service()` factory function that creates an `LLMService` configured for the provider specified in `LLMConfig`.

#### Scenario: Factory creates service for Anthropic provider
- **WHEN** calling `create_llm_service()` with an `LLMConfig` where provider is "anthropic"
- **THEN** it sets `ANTHROPIC_API_KEY` in the environment and returns a configured `LLMService`

#### Scenario: Factory creates service for OpenAI provider
- **WHEN** calling `create_llm_service()` with an `LLMConfig` where provider is "openai"
- **THEN** it sets `OPENAI_API_KEY` in the environment and returns a configured `LLMService`

#### Scenario: Factory creates service for Ollama provider
- **WHEN** calling `create_llm_service()` with an `LLMConfig` where provider is "ollama"
- **THEN** it returns a configured `LLMService` without requiring any API key

### Requirement: Language detection from file extension
The system SHALL provide a `detect_language()` function that maps filenames to programming language names based on file extension.

#### Scenario: Known extension returns language name
- **WHEN** calling `detect_language("main.py")`
- **THEN** it returns "Python"

#### Scenario: TypeScript JSX extension detected
- **WHEN** calling `detect_language("App.tsx")`
- **THEN** it returns "TypeScript JSX"

#### Scenario: Special filename detected
- **WHEN** calling `detect_language("Dockerfile")`
- **THEN** it returns "Dockerfile"

#### Scenario: Config dotfile detected
- **WHEN** calling `detect_language(".gitignore")`
- **THEN** it returns "Config"

#### Scenario: Unknown extension returns Text
- **WHEN** calling `detect_language("data.xyz")`
- **THEN** it returns "Text"

