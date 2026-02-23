# Phase 4: LLM Integration (BAML)

**Goal:** BAML prompt definitions, generated client, thin Python service wrapper, and rate limiter.
**Milestone:** `baml-cli generate` succeeds. Can call `SummarizeFile` and get a structured response.
**Depends on:** Phase 1 (config schema for `LLMConfig`). Independent of Phase 2 and Phase 3.

---

## 4.1 BAML Setup

### Prerequisites
- `baml-py` installed (included in `pyproject.toml` dependencies)
- `baml-cli` available (ships with `baml-py`)
- VSCode BAML extension recommended for syntax highlighting and playground

### Initialize BAML
```bash
cd /Users/shanngray/AI_Projects/Lexibrary
uv run baml-cli init
```
This creates `baml_src/` with starter files. We'll replace/modify them.

### Configure generation output

BAML needs to know where to output the generated client. Create/modify `baml_src/generators.baml`:

```baml
generator target {
  output_type "python/pydantic"
  output_dir "../src/lexibrary/baml_client"
  version "0.75.0"
}
```

This generates the `baml_client/` inside the package so imports work as `from lexibrary.baml_client ...`.

---

## 4.2 BAML Client Definitions

### File: `baml_src/clients.baml`

```baml
client<llm> AnthropicClient {
  provider "anthropic"
  options {
    model "claude-sonnet-4-5-20250514"
    api_key env.ANTHROPIC_API_KEY
    max_tokens 200
  }
}

client<llm> OpenAIClient {
  provider "openai"
  options {
    model "gpt-4o-mini"
    api_key env.OPENAI_API_KEY
    max_tokens 200
  }
}

client<llm> OllamaClient {
  provider "openai"
  options {
    model "llama3.2"
    base_url "http://localhost:11434/v1"
    api_key "ollama"
    max_tokens 200
  }
}
```

Notes:
- Ollama uses the `openai` provider with a custom `base_url` (Ollama exposes an OpenAI-compatible API)
- `max_tokens` set to 200 — summaries are short; this caps LLM generation cost
- API keys read from environment variables
- The default client in each function is `AnthropicClient`; runtime switching via client registry

---

## 4.3 BAML Type Definitions

### File: `baml_src/types.baml`

Shared types used across functions:

```baml
class FileSummary {
  summary string @description("One concise sentence describing what the file does and why it exists. Use imperative style. Max 80 tokens.")
}

class FileInput {
  file string @description("Filename including extension")
  content string @description("File contents (may be truncated)")
  language string @description("Programming language or file type")
}

class BatchFileSummary {
  file string @description("Filename this summary is for")
  summary string @description("One concise sentence summary")
}
```

---

## 4.4 BAML Function Definitions

### File: `baml_src/summarize_file.baml`

```baml
function SummarizeFile(filename: string, language: string, content: string, is_truncated: bool) -> FileSummary {
  client AnthropicClient
  prompt #"
    You are a code documentation assistant. Write an extremely concise file summary.

    Rules:
    - Exactly one sentence
    - Maximum 80 tokens
    - Focus on WHAT the file does and WHY it exists
    - Use imperative style (e.g. "Define the user model with validation")
    - Never start with "This file"
    - No markdown formatting

    File: {{ filename }}
    Language: {{ language }}
    {% if is_truncated %}
    Note: File content was truncated due to size.
    {% endif %}

    ---
    {{ content }}
    ---

    {{ ctx.output_format }}
  "#
}
```

### File: `baml_src/summarize_files_batch.baml`

```baml
function SummarizeFilesBatch(files: FileInput[]) -> BatchFileSummary[] {
  client AnthropicClient
  prompt #"
    You are a code documentation assistant. For each file below, write exactly ONE concise sentence summary.

    Rules:
    - One sentence per file, max 80 tokens each
    - Focus on WHAT each file does and WHY
    - Use imperative style
    - Never start with "This file"

    {% for f in files %}
    === {{ f.file }} ({{ f.language }}) ===
    {{ f.content }}

    {% endfor %}

    {{ ctx.output_format }}
  "#
}
```

### File: `baml_src/summarize_directory.baml`

```baml
function SummarizeDirectory(dirname: string, file_list: string, subdir_list: string) -> string {
  client AnthropicClient
  prompt #"
    You are a code documentation assistant. Write a concise summary of this directory.

    Rules:
    - 1-3 sentences maximum
    - Maximum 150 tokens
    - Focus on the directory's PURPOSE and role in the project
    - Plain text only, no markdown formatting
    - Do not list individual files — summarize the overall purpose

    Directory: {{ dirname }}

    Files in this directory:
    {{ file_list }}

    Subdirectories:
    {{ subdir_list }}
  "#
}
```

---

## 4.5 Generate the Client

```bash
uv run baml-cli generate
```

This creates `src/lexibrary/baml_client/` with:
- `sync_client.py` — synchronous client (`from lexibrary.baml_client.sync_client import b`)
- `async_client.py` — async client (`from lexibrary.baml_client.async_client import b`)
- Type definitions as Pydantic models
- `__init__.py` with exports

The generated code should NOT be edited manually. Re-run `baml-cli generate` after any `.baml` file change.

Add to `.gitignore`:
```
# BAML generated client — regenerate with `baml-cli generate`
src/lexibrary/baml_client/
```

Or alternatively, commit it so users don't need `baml-cli` at runtime. Decision: **commit it** (users may `pip install` without BAML toolchain).

---

## 4.6 Python Service Wrapper

### File: `src/lexibrary/llm/service.py`

Thin wrapper that calls `baml_client` functions with rate limiting and error handling.

```python
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from ..baml_client.async_client import b
from .rate_limiter import RateLimiter

log = logging.getLogger(__name__)

@dataclass
class FileSummaryRequest:
    path: Path
    content: str
    language: str
    is_truncated: bool = False

@dataclass
class FileSummaryResult:
    path: Path
    summary: str

@dataclass
class DirectorySummaryRequest:
    directory: Path
    file_list: str      # pre-formatted string of file entries
    subdir_list: str    # pre-formatted string of subdir entries

class LLMService:
    """Async wrapper around BAML-generated LLM functions."""

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._rate_limiter = rate_limiter or RateLimiter()

    async def summarize_file(self, request: FileSummaryRequest) -> FileSummaryResult:
        """Summarize a single file."""
        await self._rate_limiter.acquire()
        try:
            result = await b.SummarizeFile(
                filename=request.path.name,
                language=request.language,
                content=request.content,
                is_truncated=request.is_truncated,
            )
            return FileSummaryResult(path=request.path, summary=result.summary)
        except Exception as e:
            log.warning("LLM error summarizing %s: %s", request.path, e)
            return FileSummaryResult(
                path=request.path,
                summary="Summary unavailable (error)",
            )

    async def summarize_files_batch(
        self, requests: list[FileSummaryRequest]
    ) -> list[FileSummaryResult]:
        """Summarize multiple files in a single LLM call."""
        if not requests:
            return []

        await self._rate_limiter.acquire()
        try:
            file_inputs = [
                {"file": r.path.name, "content": r.content, "language": r.language}
                for r in requests
            ]
            results = await b.SummarizeFilesBatch(files=file_inputs)

            # Map results back to paths
            path_by_name = {r.path.name: r.path for r in requests}
            return [
                FileSummaryResult(
                    path=path_by_name.get(r.file, requests[i].path),
                    summary=r.summary,
                )
                for i, r in enumerate(results)
            ]
        except Exception as e:
            log.warning("LLM batch error: %s", e)
            return [
                FileSummaryResult(path=r.path, summary="Summary unavailable (error)")
                for r in requests
            ]

    async def summarize_directory(
        self, request: DirectorySummaryRequest
    ) -> str:
        """Summarize a directory given its contents."""
        await self._rate_limiter.acquire()
        try:
            result = await b.SummarizeDirectory(
                dirname=request.directory.name + "/",
                file_list=request.file_list or "(none)",
                subdir_list=request.subdir_list or "(none)",
            )
            return result
        except Exception as e:
            log.warning("LLM error summarizing dir %s: %s", request.directory, e)
            return "Summary unavailable."
```

---

## 4.7 Factory (Runtime Client Switching)

### File: `src/lexibrary/llm/factory.py`

```python
from __future__ import annotations
import os
from ..config.schema import LLMConfig
from ..baml_client import reset_baml_env_vars  # if available
from .service import LLMService
from .rate_limiter import RateLimiter

def create_llm_service(config: LLMConfig) -> LLMService:
    """Create an LLMService with the provider configured in lexibrary.toml.

    Uses BAML's client registry to override the default client at runtime.
    """
    # Resolve API key
    api_key = config.api_key or os.environ.get(config.api_key_env, "")

    # Set environment variables that BAML clients reference
    # BAML reads env vars at call time, so setting them here works
    match config.provider:
        case "anthropic":
            os.environ.setdefault("ANTHROPIC_API_KEY", api_key)
        case "openai":
            os.environ.setdefault("OPENAI_API_KEY", api_key)
        case "ollama":
            pass  # Ollama doesn't need an API key

    # TODO: Use BAML client registry to swap the default client
    # based on config.provider. This allows runtime switching:
    #   from baml_client import baml
    #   baml.configure(default_client="OpenAIClient")
    # Exact API depends on baml-py version.

    rate_limiter = RateLimiter(requests_per_minute=50)
    return LLMService(rate_limiter=rate_limiter)
```

Note: The exact mechanism for runtime client switching depends on the `baml-py` version. The BAML client registry allows overriding which client a function uses at call time. This will be finalized during implementation when we can test against the actual `baml-py` API.

---

## 4.8 Rate Limiter

### File: `src/lexibrary/llm/rate_limiter.py`

```python
import asyncio
import time

class RateLimiter:
    """Simple async rate limiter using token-bucket algorithm.

    Ensures we don't exceed provider rate limits.
    Default: 50 requests/minute (conservative for most providers).
    """

    def __init__(self, requests_per_minute: int = 50):
        self._rpm = requests_per_minute
        self._interval = 60.0 / requests_per_minute
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until we can make another request."""
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()
```

---

## 4.9 `__init__.py`

### File: `src/lexibrary/llm/__init__.py`

```python
from .service import LLMService, FileSummaryRequest, FileSummaryResult, DirectorySummaryRequest
from .factory import create_llm_service

__all__ = [
    "LLMService",
    "FileSummaryRequest",
    "FileSummaryResult",
    "DirectorySummaryRequest",
    "create_llm_service",
]
```

---

## 4.10 Language Detection Helper

The `LLMService` needs to know the programming language for each file. Add a utility:

### File: `src/lexibrary/utils/languages.py`

```python
EXTENSION_MAP: dict[str, str] = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript JSX", ".jsx": "JavaScript JSX",
    ".rs": "Rust", ".go": "Go", ".java": "Java",
    ".rb": "Ruby", ".php": "PHP", ".c": "C", ".h": "C Header",
    ".cpp": "C++", ".hpp": "C++ Header", ".cs": "C#",
    ".swift": "Swift", ".kt": "Kotlin", ".scala": "Scala",
    ".sh": "Shell", ".bash": "Bash", ".zsh": "Zsh",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML", ".xml": "XML", ".md": "Markdown",
    ".sql": "SQL", ".r": "R", ".R": "R",
    ".lua": "Lua", ".vim": "Vim Script",
    ".dockerfile": "Dockerfile", ".tf": "Terraform",
    ".proto": "Protocol Buffers", ".graphql": "GraphQL",
    ".baml": "BAML",
}

def detect_language(filename: str) -> str:
    """Detect programming language from filename/extension."""
    lower = filename.lower()
    # Special filenames
    if lower in ("dockerfile", "makefile", "rakefile", "gemfile", "justfile"):
        return lower.capitalize()
    if lower in (".gitignore", ".dockerignore", ".editorconfig"):
        return "Config"

    from pathlib import Path
    ext = Path(filename).suffix.lower()
    return EXTENSION_MAP.get(ext, "Text")
```

---

## 4.11 Tests

### File: `tests/test_llm/test_rate_limiter.py`

| Test | What it verifies |
|------|-----------------|
| `test_rate_limiter_first_call_immediate` | First `acquire()` returns without delay |
| `test_rate_limiter_respects_interval` | Two rapid calls have at least `interval` gap |
| `test_rate_limiter_concurrent` | Multiple concurrent acquires are serialized |

### File: `tests/test_llm/test_service.py`

| Test | What it verifies |
|------|-----------------|
| `test_summarize_file_success` | Mock `b.SummarizeFile`, verify returns `FileSummaryResult` |
| `test_summarize_file_error_fallback` | Mock raises exception, verify fallback summary |
| `test_summarize_batch_success` | Mock `b.SummarizeFilesBatch`, verify all results mapped |
| `test_summarize_batch_empty` | Empty input returns empty list |
| `test_summarize_directory_success` | Mock `b.SummarizeDirectory`, verify returns string |
| `test_summarize_directory_error_fallback` | Mock raises, verify fallback |

### File: `tests/test_llm/test_languages.py`

| Test | What it verifies |
|------|-----------------|
| `test_detect_python` | `.py` → "Python" |
| `test_detect_special_names` | "Dockerfile" → "Dockerfile" |
| `test_detect_unknown` | `.xyz` → "Text" |

### BAML playground testing

Before writing Python tests, use the BAML VSCode playground to:
1. Test `SummarizeFile` with a real Python file
2. Test `SummarizeFilesBatch` with 3-4 small files
3. Test `SummarizeDirectory` with realistic file/subdir lists
4. Verify output structure matches expected types

---

## Acceptance Criteria

- [ ] `uv run baml-cli generate` succeeds without errors
- [ ] `baml_client/` is generated inside `src/lexibrary/`
- [ ] `from lexibrary.baml_client.async_client import b` works
- [ ] `LLMService.summarize_file()` returns a `FileSummaryResult` with a non-empty summary
- [ ] `LLMService.summarize_files_batch()` returns one result per input file
- [ ] `LLMService.summarize_directory()` returns a string summary
- [ ] All LLM errors are caught and produce fallback summaries (no crashes)
- [ ] Rate limiter enforces the configured request interval
- [ ] `detect_language()` correctly maps common extensions
- [ ] All tests pass: `uv run pytest tests/test_llm -v`
