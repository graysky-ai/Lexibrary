# Plan: Config-Driven BAML Clients with Token Safety

## Context

**Problem 1 — Hardcoded BAML clients:** `clients.baml` has 7 hardcoded client definitions with baked-in models, token limits, and API keys. The `config.yaml` fields like `llm.model` are ignored — only `llm.provider` is used to select a pre-baked BAML client. Changing config.yaml doesn't actually change what model or limits BAML uses.

**Problem 2 — Output truncation:** `lexictl update` fails with `StopReason: length` for large source files. The root cause is that `max_completion_tokens: 1500` in `clients.baml` is insufficient for the structured JSON output the Archivist needs to produce for large files (e.g. `lexi_app.py`: 12,406 input tokens → truncated output → BAML JSON parse failure → no design file written).

**Problem 3 — Hidden config:** `TokenBudgetConfig` has 7 fields but the init wizard only exposes 5 (`orientation_tokens` and `lookup_total_tokens` are hidden). The scaffolder only writes `token_budgets` to config.yaml when the user customizes values, leaving the section absent from most configs.

These three problems are addressed together because the config-driven ClientRegistry approach solves both the hardcoded-client and truncation issues in one mechanism.

## Approach

Use BAML's `ClientRegistry` API to create clients dynamically at runtime from config values. The generated BAML client already supports `b.with_options(client_registry=cr, client="name")`.

Two dynamic clients are created, each with its own max_tokens limit drawn from config:
- **`lexibrary-summarize`** — for file/directory summarization (uses `token_budgets.summarize_max_tokens`, default 200)
- **`lexibrary-archivist`** — for design file generation (uses `token_budgets.archivist_max_tokens`, default 5000)

Both share `llm.provider`, `llm.model`, `llm.api_key_env` from config.

The existing validation budget fields (`design_file_tokens`, `aindex_tokens`, etc.) remain separate — they control how large an artifact *should* be (checked by the validator), while `*_max_tokens` fields control how many tokens the LLM is *allowed* to generate (sent as `max_tokens` to the API). Both live in `TokenBudgetConfig` as a single place for all token numbers.

`TokenBudgetConfig` grows from 7 to 9 fields. All 9 are exposed in the init wizard and always written explicitly to config.yaml.

A pre-call size gate prevents wasted LLM calls on files too large to produce complete output. Files that exceed the gate get a skeleton design file instead. A `--max-tokens` CLI flag allows operators to override the limit for targeted re-enrichment of skeleton files.

---

## Changes

### 1. Update `TokenBudgetConfig` and `LLMConfig` in schema

**File:** [schema.py](src/lexibrary/config/schema.py)

Add `base_url` to `LLMConfig` (for openai-generic / Ollama support):

```python
class LLMConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-6"
    api_key_env: str = "ANTHROPIC_API_KEY"
    api_key_source: str = "env"
    base_url: str | None = None          # <-- new
    max_retries: int = 3
    timeout: int = 60
```

Add two new fields to `TokenBudgetConfig`:

```python
class TokenBudgetConfig(BaseModel):
    # Artifact validation budgets (how large artifacts should be)
    design_file_tokens: int = 400
    design_file_abridged_tokens: int = 100
    aindex_tokens: int = 200
    concept_file_tokens: int = 400
    convention_file_tokens: int = 500
    orientation_tokens: int = 300
    lookup_total_tokens: int = 1200
    # LLM generation limits (max_tokens sent to the API)
    summarize_max_tokens: int = 200
    archivist_max_tokens: int = 5000
```

### 2. Update init wizard to expose all 9 fields

**File:** [wizard.py](src/lexibrary/init/wizard.py)

Update `_DEFAULT_TOKEN_BUDGETS` to include all 9 fields:

```python
_DEFAULT_TOKEN_BUDGETS: dict[str, int] = {
    "design_file_tokens": 400,
    "design_file_abridged_tokens": 100,
    "aindex_tokens": 200,
    "concept_file_tokens": 400,
    "convention_file_tokens": 500,
    "orientation_tokens": 300,
    "lookup_total_tokens": 1200,
    "summarize_max_tokens": 200,
    "archivist_max_tokens": 5000,
}
```

No other wizard changes needed — `_step_token_budgets` already iterates `_DEFAULT_TOKEN_BUDGETS`.

### 3. Always write token_budgets to config.yaml

**File:** [scaffolder.py](src/lexibrary/init/scaffolder.py)

Change from conditional to unconditional. Use `TokenBudgetConfig` to fill in defaults for any fields the user didn't customize:

```python
# Before:
if answers.token_budgets_customized and answers.token_budgets:
    config_dict["token_budgets"] = answers.token_budgets

# After:
budget_config = TokenBudgetConfig(**answers.token_budgets)
config_dict["token_budgets"] = budget_config.model_dump()
```

This always writes all 9 fields with correct defaults. Requires adding `TokenBudgetConfig` to the existing import from `lexibrary.config.schema`.

### 4. Update default_config.yaml template

**File:** [default_config.yaml](src/lexibrary/templates/config/default_config.yaml)

Replace the partial token_budgets section with all 9 fields:

```yaml
# Per-artifact token budgets (validation targets for generated content)
token_budgets:
  design_file_tokens: 400                # Full design file budget
  design_file_abridged_tokens: 100       # Abridged design file budget
  aindex_tokens: 200                     # .aindex routing table budget
  concept_file_tokens: 400               # Concept file budget
  convention_file_tokens: 500            # Convention file budget
  orientation_tokens: 300                # Orientation output budget
  lookup_total_tokens: 1200              # Total tokens for lexi lookup response
  summarize_max_tokens: 200              # LLM max_tokens for summarization calls
  archivist_max_tokens: 5000             # LLM max_tokens for design file generation
```

### 5. Create `src/lexibrary/llm/client_registry.py`

New module with a pure function:

```python
def build_client_registry(
    llm: LLMConfig,
    token_budgets: TokenBudgetConfig,
) -> baml_py.baml_py.ClientRegistry:
```

Logic:
- Resolve API key from env using `llm.api_key_env`
- Map provider to correct token-limit key (`max_tokens` for anthropic, `max_completion_tokens` for openai/openai-generic)
- Add `base_url` to options when provider is `openai-generic`
- Register two clients:
  - `lexibrary-summarize` with max_tokens = `token_budgets.summarize_max_tokens`
  - `lexibrary-archivist` with max_tokens = `token_budgets.archivist_max_tokens`
- Set `lexibrary-summarize` as primary (default)
- Apply retry policy: `DefaultRetry` (from BAML) with `max_retries` from config

Optional `archivist_max_tokens_override` parameter: when provided (from `--max-tokens` CLI flag), overrides `token_budgets.archivist_max_tokens` for that call. This is how `--max-tokens` flows through without modifying config.

### 6. Reduce `clients.baml` to minimal placeholder

**File:** [clients.baml](baml_src/clients.baml)

BAML requires at least one client to compile. Replace all 7 clients with:

```baml
retry_policy DefaultRetry {
  max_retries 2
}

// Placeholder — overridden at runtime by ClientRegistry built from config.yaml
client<llm> Placeholder {
  provider anthropic
  options {
    model "placeholder"
    max_tokens 1
  }
}
```

### 7. Update BAML function files to use `Placeholder`

Change the `client` line in 4 files:
- [archivist_design_file.baml](baml_src/archivist_design_file.baml):11 — `client AnthropicArchivist` → `client Placeholder`
- [summarize_file.baml](baml_src/summarize_file.baml):4 — `client PrimaryClient` → `client Placeholder`
- [summarize_directory.baml](baml_src/summarize_directory.baml):4 — `client PrimaryClient` → `client Placeholder`
- [summarize_files_batch.baml](baml_src/summarize_files_batch.baml):4 — `client PrimaryClient` → `client Placeholder`

### 8. Regenerate BAML client code

Run `baml-cli generate` to update generated Python under `src/lexibrary/baml_client/`.

### 9. Rewrite `ArchivistService`

**File:** [service.py](src/lexibrary/archivist/service.py)

- Remove `_PROVIDER_CLIENT_MAP`
- Change `__init__` signature: accept `client_registry: baml_py.baml_py.ClientRegistry` instead of `config: LLMConfig`
- Store `self._client_registry = client_registry`
- Change `_get_baml_client()` to: `return b.with_options(client_registry=self._client_registry, client="lexibrary-archivist")`
- Remove `_config` field (only used for logging provider name — can log from client name instead)

### 10. Update `LLMService` and factory

**File:** [service.py](src/lexibrary/llm/service.py)
- Change `__init__` to accept `client_registry: baml_py.baml_py.ClientRegistry`
- All `b.SummarizeFile(...)` etc. calls become `self._client.SummarizeFile(...)` where `self._client = b.with_options(client_registry=client_registry, client="lexibrary-summarize")`

**File:** [factory.py](src/lexibrary/llm/factory.py)
- Change `create_llm_service(config)` to `create_llm_service(config: LexibraryConfig)` (full config, not just LLMConfig)
- Use `build_client_registry(config.llm, config.token_budgets)` to create registry
- Pass registry to `LLMService`
- Remove `_PROVIDER_ENV_KEYS` and env var manipulation

### 11. Update all call sites (5 production locations)

Each call site needs to build the registry and pass it:

| File | Line | Current | New |
|------|------|---------|-----|
| [lexictl_app.py](src/lexibrary/cli/lexictl_app.py) | 130 | `ArchivistService(rate_limiter=..., config=config.llm)` | `ArchivistService(rate_limiter=..., client_registry=cr)` |
| [lexictl_app.py](src/lexibrary/cli/lexictl_app.py) | 328 | same | same |
| [daemon/service.py](src/lexibrary/daemon/service.py) | 268 | same | same |
| [validator/fixes.py](src/lexibrary/validator/fixes.py) | 59 | same | same |
| [bootstrap.py](src/lexibrary/lifecycle/bootstrap.py) | 320 | same | same |

At each call site, add before the service instantiation:
```python
from lexibrary.llm.client_registry import build_client_registry
cr = build_client_registry(config.llm, config.token_budgets)
```

### 12. Add `--max-tokens` CLI flag to `lexictl update`

**File:** [lexictl_app.py](src/lexibrary/cli/lexictl_app.py)

Add `--max-tokens` option to the `update` command:

```python
@app.command()
def update(
    ...,
    max_tokens: int | None = typer.Option(None, "--max-tokens", help="Override archivist max output tokens for this run"),
):
```

When provided, pass `archivist_max_tokens_override=max_tokens` to `build_client_registry()`. This overrides the config value for that run only, allowing operators to re-process large files:

```bash
lexictl update --max-tokens 8000 src/lexibrary/cli/lexi_app.py
```

### 13. Pre-call size gate in `update_file()`

**File:** [pipeline.py](src/lexibrary/archivist/pipeline.py) (or wherever `update_file()` lives)

Before the LLM call, apply a two-tier gate:

**Tier 1 — File size check (essentially free):**
File size in bytes is already fetched by `discover_source_files()` via `path.stat()`. Bytes ÷ 4 is a coarse but fast chars-per-token approximation. Skip token counting for files under 12 KB.

**Tier 2 — Tiktoken count (fast, offline, no cost):**
`TiktokenCounter` in `src/lexibrary/tokenizer/tiktoken_counter.py` runs BPE encoding locally (~1–5ms for a 500-line file). The `AnthropicCounter` (which calls `messages.count_tokens`) must NOT be used here — it makes a real API call.

```python
SIZE_GATE_BYTES = 12_288  # 12 KB
OUTPUT_RATIO = 0.15
STRUCTURED_JSON_OVERHEAD = 150
PROMPT_OVERHEAD = 600

if file_size_bytes >= SIZE_GATE_BYTES:
    source_tokens = tiktoken_count(source_content)
    estimated_input = source_tokens + tiktoken_count(skeleton_text or "") + PROMPT_OVERHEAD
    estimated_output = max(400, source_tokens * OUTPUT_RATIO) + STRUCTURED_JSON_OVERHEAD
    safe_max_output = config.token_budgets.archivist_max_tokens * 0.90

    if estimated_output > safe_max_output:
        return write_skeleton_design_file(...)
```

A 10% safety margin is applied: false positives (unnecessary fallbacks) are cheap; false negatives (hitting the limit) cause the failure we're fixing.

### 14. Skeleton design file fallback

When the size gate triggers, write a skeleton design file without an LLM call:

- `summary`: `"Skeleton — source too large for LLM analysis (~{source_tokens} tokens)"`
- `interface_contract`: the pre-computed `skeleton_text` (AST-extracted public API surface)
- `dependencies`: from `extract_dependencies()` (no LLM needed)
- `tests`, `complexity_warning`, `wikilinks`, `tags`: all null/empty
- `frontmatter.updated_by`: `"skeleton-fallback"`
- `metadata` footer: written with **current** `source_hash` and `interface_hash`

This gives downstream consumers a valid design file with accurate interface coverage even for files the LLM couldn't fully process.

### 15. `SKELETON_ONLY` change level for retry detection

**File:** where `check_change()` is defined

Extend `check_change()` to detect skeleton files:
- Parse the design file frontmatter
- When `updated_by == "skeleton-fallback"` and the source hash matches, return `ChangeLevel.SKELETON_ONLY`

`update_file()` behaviour:
- **Normal mode** (no `--max-tokens`): treat `SKELETON_ONLY` as `UNCHANGED` — return early to avoid pointless retries that would fail at the same token limit
- **With `--max-tokens`**: treat `SKELETON_ONLY` as needing LLM generation — the operator has explicitly declared a higher budget, so re-enrichment is attempted

This avoids the retry-loop problem: skeleton enrichment only runs when the operator has explicitly provided a higher token budget.

### 16. Update tests

**File:** [test_service.py](tests/test_archivist/test_service.py)
- Replace `config=anthropic_config` / `config=openai_config` with `client_registry=mock_registry` in all instantiation sites
- Create a fixture that builds a test registry or mocks `ClientRegistry`

**File:** [tests/test_llm/test_service.py](tests/test_llm/test_service.py)
- Same pattern — pass registry instead of bare init

**New file:** `tests/test_llm/test_client_registry.py`
- Test `build_client_registry()` creates two clients with correct names
- Test provider-specific token limit key mapping
- Test base_url inclusion for openai-generic
- Test API key resolution from env
- Test `archivist_max_tokens_override` parameter

**File:** [tests/test_init/test_wizard.py](tests/test_init/test_wizard.py)
- Verify all 9 token budget fields are exposed

**File:** [tests/test_init/test_scaffolder.py](tests/test_init/test_scaffolder.py)
- Verify config.yaml always contains `token_budgets` section with all 9 fields
- Verify customized values are overlaid on defaults

**File:** [tests/test_config/test_schema.py](tests/test_config/test_schema.py)
- Add tests for `summarize_max_tokens` and `archivist_max_tokens` fields
- Verify defaults are correct

**New tests for size gate and skeleton fallback:**
- Test two-tier gate skips small files
- Test tiktoken counting triggers skeleton for large files
- Test skeleton design file has correct structure and `updated_by: skeleton-fallback`
- Test `check_change()` returns `SKELETON_ONLY` for skeleton files
- Test `update_file()` skips skeleton re-enrichment without `--max-tokens`
- Test `update_file()` re-enriches skeleton files with `--max-tokens`

### 17. Update `.lexibrary/config.yaml` with documented LLM fields

Add comments/example showing the full LLM configuration surface including the new token budget fields.

---

## Technical Reference

### Token estimation heuristics

**Prompt overhead accounting:** The BAML prompt includes fixed sections:
- System prompt + instructions: ~400–600 tokens (fixed)
- Interface skeleton: variable, but already available pre-call as `skeleton_text`
- Existing design file: variable, bounded by previous design file size
- Available concepts list: small (~1–3 tokens per concept)

A safe constant for prompt overhead is ~600 tokens. Source content + skeleton dominate for large files.

**Output estimation:** The model's verbosity on `interface_contract` varies. Heuristic:
- `OUTPUT_RATIO ≈ 0.15` (empirically: interface_contract tends to be ~10–15% of source size for well-structured Python files)
- `STRUCTURED_JSON_OVERHEAD ≈ 150` tokens (BAML adds field names, quotes, brackets)

**Model context window bounds:** GPT-5-mini and Claude Sonnet 4.6 both have 128K+ context windows, so input overflow is not a near-term concern. `max_file_size_kb` in crawl config provides a hard gate that should be tuned relative to the model's context window.

### Provider-specific token limit keys

| Provider | Token limit option key |
|----------|----------------------|
| `anthropic` | `max_tokens` |
| `openai` | `max_completion_tokens` |
| `openai-generic` | `max_completion_tokens` |

### What was considered and rejected

- **Named high-cap clients** (e.g. `AnthropicArchivistHighCap`): Unnecessary — ClientRegistry handles dynamic limits, and `--max-tokens` overrides the config value directly.
- **Stale hash trick for skeleton retry**: Writing a zeroed `source_hash` to force re-processing. Semantically dishonest and causes a failed LLM call on every update run until fixed — the same problem it was meant to solve.
- **Source truncation**: Silently loses the tail of large files. The most important public symbols often appear later in the file.
- **`force` parameter on `update_file()`**: Less granular than `SKELETON_ONLY` — forces re-generation of everything rather than targeting only skeleton files.
- **Phased rollout starting with "just raise the hardcoded value"**: Pointless if we're removing hardcoded values entirely via ClientRegistry.

---

## Verification

1. `uv run baml-cli generate` — BAML compiles with placeholder client
2. `uv run pytest tests/test_llm/ tests/test_archivist/ tests/test_init/ tests/test_config/ -v` — service, init, and config tests pass
3. `uv run pytest --cov=lexibrary` — full test suite passes
4. `uv run ruff check src/ tests/` — no lint issues
5. `uv run mypy src/` — type checks pass
6. Manual: change `llm.model` in `.lexibrary/config.yaml` and verify the BAML client uses the new model
7. Manual: change `token_budgets.archivist_max_tokens` and verify it affects design file generation
8. Manual: run `lexictl update` on a large file (>12 KB) and verify skeleton fallback triggers
9. Manual: run `lexictl update --max-tokens 8000 <large_file>` and verify skeleton is re-enriched
