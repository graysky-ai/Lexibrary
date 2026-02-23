# Phase 2: Token Counting

**Goal:** Pluggable token counting with tiktoken, Anthropic API, and approximate fallback backends.
**Milestone:** Can count tokens in any file using any configured backend.
**Depends on:** Phase 1 (config schema for `TokenizerConfig`).

---

## 2.1 TokenCounter Protocol

### File: `src/lexibrary/tokenizer/base.py`

```python
from __future__ import annotations
from typing import Protocol
from pathlib import Path

class TokenCounter(Protocol):
    """Protocol for token counting backends."""

    def count(self, text: str) -> int:
        """Count the number of tokens in the given text."""
        ...

    def count_file(self, path: Path) -> int:
        """Count tokens in a file. Default: read + count()."""
        ...

    @property
    def name(self) -> str:
        """Human-readable name of this tokenizer backend."""
        ...
```

Design notes:
- Protocol (structural subtyping) rather than ABC — no inheritance required
- `count_file` is a convenience method; backends can override for efficiency but the default reads UTF-8 and calls `count()`
- All backends are synchronous — token counting is CPU-bound and fast

---

## 2.2 tiktoken Backend

### File: `src/lexibrary/tokenizer/tiktoken_counter.py`

```python
import tiktoken
from pathlib import Path

class TiktokenCounter:
    """Token counter using OpenAI's tiktoken library.

    Works fully offline after first encoding download.
    Default encoding: cl100k_base (GPT-4 family, good general-purpose).
    """

    def __init__(self, model: str = "cl100k_base"):
        self._encoding = tiktoken.get_encoding(model)
        self._model = model

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))

    def count_file(self, path: Path) -> int:
        content = path.read_text(encoding="utf-8", errors="replace")
        return self.count(content)

    @property
    def name(self) -> str:
        return f"tiktoken ({self._model})"
```

Key considerations:
- `errors="replace"` handles files with mixed encoding gracefully
- tiktoken is Rust-backed BPE — very fast, ~1M tokens/sec
- Encoding is downloaded on first use and cached locally
- `cl100k_base` is the default; user can override via `[tokenizer] model`

---

## 2.3 Anthropic API Backend

### File: `src/lexibrary/tokenizer/anthropic_counter.py`

```python
import anthropic
from pathlib import Path

class AnthropicCounter:
    """Token counter using Anthropic's count_tokens API.

    Most accurate for Claude models but requires network access.
    Should be paired with caching (handled at the crawler level via ChangeDetector).
    """

    def __init__(self, model: str = "claude-sonnet-4-5-20250514"):
        self._client = anthropic.Anthropic()
        self._model = model

    def count(self, text: str) -> int:
        response = self._client.messages.count_tokens(
            model=self._model,
            messages=[{"role": "user", "content": text}],
        )
        return response.input_tokens

    def count_file(self, path: Path) -> int:
        content = path.read_text(encoding="utf-8", errors="replace")
        return self.count(content)

    @property
    def name(self) -> str:
        return f"anthropic ({self._model})"
```

Key considerations:
- Requires `ANTHROPIC_API_KEY` set in environment
- Makes a network call per count — use sparingly, rely on hash-based caching in the crawler
- The `count_tokens` endpoint is lightweight (no generation, just tokenization)
- Falls back gracefully if API is unreachable (caller should catch and log)

---

## 2.4 Approximate Fallback

### File: `src/lexibrary/tokenizer/approximate.py`

```python
from pathlib import Path

class ApproximateCounter:
    """Rough token estimate: len(text) / 4.

    No dependencies. Useful when no tokenizer library is available
    or for quick estimates during development.
    Accuracy: within ~20% for English prose/code.
    """

    CHARS_PER_TOKEN = 4.0

    def count(self, text: str) -> int:
        return max(1, int(len(text) / self.CHARS_PER_TOKEN))

    def count_file(self, path: Path) -> int:
        content = path.read_text(encoding="utf-8", errors="replace")
        return self.count(content)

    @property
    def name(self) -> str:
        return "approximate (chars/4)"
```

---

## 2.5 Factory

### File: `src/lexibrary/tokenizer/factory.py`

```python
from ..config.schema import TokenizerConfig
from .base import TokenCounter

def create_tokenizer(config: TokenizerConfig) -> TokenCounter:
    """Create the appropriate tokenizer backend from config."""
    match config.backend:
        case "tiktoken":
            from .tiktoken_counter import TiktokenCounter
            return TiktokenCounter(model=config.model)
        case "anthropic_api":
            from .anthropic_counter import AnthropicCounter
            return AnthropicCounter(model=config.model)
        case "approximate":
            from .approximate import ApproximateCounter
            return ApproximateCounter()
        case _:
            raise ValueError(f"Unknown tokenizer backend: {config.backend}")
```

Lazy imports keep startup fast — only the chosen backend's dependencies are loaded.

### File: `src/lexibrary/tokenizer/__init__.py`

```python
from .base import TokenCounter
from .factory import create_tokenizer

__all__ = ["TokenCounter", "create_tokenizer"]
```

---

## 2.6 Tests

### File: `tests/test_tokenizer/test_counters.py`

| Test | What it verifies |
|------|-----------------|
| `test_tiktoken_count_hello_world` | `TiktokenCounter("cl100k_base").count("Hello, world!")` returns a reasonable int (>0, <10) |
| `test_tiktoken_count_file` | Create a tmp file, count tokens, verify > 0 |
| `test_tiktoken_encoding_name` | `.name` contains "tiktoken" |
| `test_approximate_count` | `ApproximateCounter().count("a" * 100)` == 25 |
| `test_approximate_minimum_one` | Empty-ish strings return at least 1 |
| `test_approximate_count_file` | File-based counting works |
| `test_factory_tiktoken` | `create_tokenizer(TokenizerConfig(backend="tiktoken"))` returns `TiktokenCounter` |
| `test_factory_approximate` | `create_tokenizer(TokenizerConfig(backend="approximate"))` returns `ApproximateCounter` |
| `test_factory_unknown_raises` | `create_tokenizer(TokenizerConfig(backend="nope"))` raises `ValueError` |
| `test_anthropic_counter` | Mock the API call, verify count returns expected value (use `respx` or `unittest.mock`) |

---

## Acceptance Criteria

- [ ] `TiktokenCounter` counts tokens accurately (cross-check a known string)
- [ ] `ApproximateCounter` returns `len(text) // 4` (minimum 1)
- [ ] `AnthropicCounter` calls the API correctly (verified via mock)
- [ ] `create_tokenizer()` routes to the correct backend based on config
- [ ] Unknown backend raises `ValueError`
- [ ] All backends implement the `TokenCounter` protocol (verified by mypy or runtime `isinstance` checks)
- [ ] All tests pass: `uv run pytest tests/test_tokenizer -v`
