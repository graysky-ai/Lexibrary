# baml_src

**Summary:** BAML prompt definitions for all LLM functions used by Lexibrary; compiled by the BAML toolchain into `baml_client/` (auto-generated, do not edit).

## Functions Defined

| File | Function | Inputs | Output |
| --- | --- | --- | --- |
| `summarize_file.baml` | `SummarizeFile` | `filename`, `language`, `content`, `is_truncated` | `FileSummary { summary }` |
| `summarize_files_batch.baml` | `SummarizeFilesBatch` | `files: FileInput[]` | `BatchFileSummary[]` |
| `summarize_directory.baml` | `SummarizeDirectory` | `dirname`, `file_list`, `subdir_list` | `string` |

## Types Defined (`types.baml`)

| Type | Fields |
| --- | --- |
| `FileSummary` | `summary: string` |
| `FileInput` | `filename`, `language`, `content` |
| `BatchFileSummary` | `filename`, `summary` |

## Clients Defined (`clients.baml`)

- `AnthropicClient` — `claude-sonnet-4-5-20250929`, max_tokens 200
- `OpenAIClient` / `OpenAIBackup` — fallback pair
- `OllamaClient` — local llama3
- `PrimaryClient` — fallback strategy: `[OpenAIClient, OpenAIBackup]` with `DefaultRetry` (2 retries)

## Generator (`generators.baml`)

Outputs to `../src/lexibrary` (Python/Pydantic), async mode.

## Key Concepts

- Prompts ask for 1-2 sentence summaries only — enforce brevity
- `is_truncated` flag in `SummarizeFile` tells the LLM content is cut off
- `PrimaryClient` currently uses OpenAI as primary — update `clients.baml` to switch providers; do not edit `baml_client/`

## Dragons

- Editing any `.baml` file requires re-running `baml-cli generate` to update `baml_client/` — stale generated code will cause runtime errors
