## Context

Lexibrary crawls codebases and counts tokens to efficiently build context for LLM consumption. Token counting requirements vary:
- **Development/CI**: Needs to be fast and offline (no API calls)
- **Claude-specific workflows**: Needs accurate counts matching Claude's tokenizer
- **Fallback scenarios**: Must work without any external dependencies

Current state: Config schema exists (Phase 1) with `TokenizerConfig` defining backend selection. No token counting implementation exists yet.

Constraints:
- Must integrate with existing config system
- Should support future backends without API changes
- Token counting is synchronous (CPU-bound, typically <1ms per file)

## Goals / Non-Goals

**Goals:**
- Protocol-based design enabling easy addition of new backends
- Three production-ready backends: tiktoken (default), anthropic (accurate), approximate (zero-dep)
- Fast startup via lazy imports (only load chosen backend)
- Graceful handling of encoding errors and mixed-charset files
- Complete test coverage with mocked network calls for Anthropic backend

**Non-Goals:**
- Batch or streaming APIs (files are counted individually; batching happens at crawler level)
- Caching layer (handled by crawler's ChangeDetector via content hashing)
- Async/await interfaces (token counting is fast, synchronous CPU work)
- Custom tokenizer training or fine-tuning

## Decisions

### 1. Protocol over Abstract Base Class
**Decision**: Use `typing.Protocol` for `TokenCounter` interface
**Rationale**: Structural subtyping means backends don't need to inherit from a base class. Simpler, more flexible, better for testing (easy to create ad-hoc implementations).
**Alternative considered**: ABC with `@abstractmethod` — rejected because it forces inheritance and adds boilerplate.

### 2. Three backends with clear trade-offs
**Decision**: Implement tiktoken (fast/offline), anthropic (accurate), approximate (fallback)
**Rationale**:
- **tiktoken**: Rust-backed BPE, ~1M tokens/sec, works offline after first download. Default choice.
- **anthropic**: Network API, most accurate for Claude models. For production workflows where precision matters.
- **approximate**: `len(text) / 4`, zero dependencies, ~20% error. For development or when libraries unavailable.

**Alternative considered**: Only tiktoken — rejected because Claude-specific accuracy matters for some users, and we want zero-dependency fallback.

### 3. Lazy imports in factory
**Decision**: Import backends inside `match` cases in `create_tokenizer()`
**Rationale**: Keeps startup fast. If user chooses `approximate`, they never pay the cost of importing `tiktoken` or `anthropic` SDKs.
**Alternative considered**: Top-level imports — rejected because unnecessary startup overhead.

### 4. Synchronous API
**Decision**: All methods are synchronous (no async/await)
**Rationale**: Token counting is CPU-bound and fast (<1ms per file typically). Async adds complexity without benefit. Crawler can parallelize at file level if needed.
**Alternative considered**: Async for Anthropic API calls — rejected because network call overhead is small, and mixing sync/async complicates the interface.

### 5. UTF-8 with error replacement
**Decision**: Use `encoding="utf-8", errors="replace"` when reading files
**Rationale**: Codebases may have mixed encodings (e.g., legacy files, binaries). Replacing invalid bytes with � is better than crashing. Token count remains approximately correct.
**Alternative considered**: Strict encoding or auto-detection — rejected because it's overkill and error-replacement handles 99% of cases gracefully.

## Risks / Trade-offs

**[Risk]** Anthropic API requires network and API key → **Mitigation**: Clearly document in backend name; rely on crawler-level caching to minimize calls; graceful degradation if API unreachable.

**[Risk]** tiktoken downloads encoding on first use (~1MB download) → **Mitigation**: Acceptable one-time cost; happens transparently; encoding is cached locally; document in README.

**[Trade-off]** Approximate backend has ~20% error margin → **Mitigation**: Clearly label as "approximate" in `.name` property; document accuracy in docstrings; recommend tiktoken for production use.

**[Trade-off]** No batching API → **Justification**: Batching belongs at crawler level (which already groups files). Keeping counter interface simple makes it easier to implement new backends.

**[Risk]** cl100k_base default may not match all models → **Mitigation**: Expose `model` parameter in config; document that cl100k_base is a good general-purpose default used by GPT-4 family.

## Migration Plan

N/A — This is new functionality with no migration required.

## Open Questions

None — design is ready for implementation.
