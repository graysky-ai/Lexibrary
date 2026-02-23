## Why

Lexibrary needs to count tokens in files to build context efficiently. Different use cases require different trade-offs: tiktoken for offline speed, Anthropic API for Claude-accurate counts, and an approximate fallback when libraries aren't available. A pluggable backend system enables users to choose the right tool for their needs.

## What Changes

- Create `TokenCounter` protocol defining the token counting interface
- Implement three backends:
  - **tiktoken**: Fast, offline, BPE-based counting using OpenAI's library
  - **anthropic**: Network-based, Claude-accurate counting via Anthropic API
  - **approximate**: Zero-dependency fallback using chars/4 heuristic
- Add factory function to instantiate backends from config
- Provide comprehensive test coverage for all backends and factory logic

## Capabilities

### New Capabilities
- `token-counting`: Pluggable token counting with multiple backend implementations

### Modified Capabilities
<!-- None - this is new functionality -->

## Impact

- New module: `src/lexibrary/tokenizer/` with protocol, backends, and factory
- Depends on `TokenizerConfig` from Phase 1 config schema
- Optional dependencies: `tiktoken` and `anthropic` SDK (approximate backend has zero deps)
- Test suite: `tests/test_tokenizer/`
