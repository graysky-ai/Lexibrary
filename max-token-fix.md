# Max Token Fix Plan

## Problem

`lexictl update` fails with `StopReason: length` for large source files. The root cause
is that `max_completion_tokens: 1500` in `baml_src/clients.baml` is insufficient for
the structured JSON output the Archivist needs to produce for large files like
`lexi_app.py` (12,406 input tokens → truncated output → BAML JSON parse failure →
no design file written).

---

## Q1: Is pre-call token estimation free? What's the latency?

### Short answer: Yes — use a two-tier gate.

**Tier 1 — File size check (essentially free)**

File size in bytes is already fetched by `discover_source_files()` via `path.stat()`.
Bytes ÷ 4 is a coarse but fast chars-per-token approximation. This costs zero extra
I/O and adds nanoseconds. Use this as the first gate to skip token counting for
small files entirely.

**Tier 2 — Tiktoken count (fast, offline, no cost)**

`TiktokenCounter` in `src/lexibrary/tokenizer/tiktoken_counter.py` runs BPE encoding
locally. On a modern machine this is ~1–5ms for a 500-line file, ~10–20ms for a
2000-line file. No network call, no API cost — it uses a cached local encoding.

The `AnthropicCounter` (which calls `messages.count_tokens`) is the variant to avoid
here — it makes a real API call (~100–300ms, billable).

**Recommended gate:**

```
if file_size_bytes < SIZE_GATE_BYTES:
    # skip estimation entirely — source is small, can't overflow
elif source_tokens + PROMPT_OVERHEAD > context_window - max_output_tokens * SAFETY_MARGIN:
    # source too large — use fallback strategy
```

A reasonable `SIZE_GATE_BYTES` is ~12 KB. Files under 3000 source tokens will
almost never hit a 1500-token output cap. Tiktoken is only invoked for the
files that actually need the check.

**Prompt overhead accounting:**

The BAML prompt includes fixed sections that cost tokens:
- System prompt + instructions: ~400–600 tokens (fixed)
- Interface skeleton: variable, but already available pre-call as `skeleton_text`
- Existing design file: variable, bounded by previous design file size
- Available concepts list: small (~1–3 tokens per concept)

A safe constant for prompt overhead is ~600 tokens. Source content + skeleton
dominate for large files, so:

```
estimated_input = count(source_content) + count(skeleton_text or "") + 600
```

---

## Q2: Max tokens must be read from config, not hardcoded

`max_completion_tokens` is currently buried in `baml_src/clients.baml` with no
runtime-visible path. We need it surfaced at the Python layer to make the
pre-call check config-driven.

### Option A: Add `max_output_tokens` to `LLMConfig`

Add a field to `src/lexibrary/config/schema.py` `LLMConfig`:

```python
max_output_tokens: int = 4096   # raised from 1500
```

Pass this into `ArchivistService` and:
1. Use it as the threshold in the pre-call size check.
2. Use it to set `max_tokens` dynamically via `b.with_options()` if BAML
   supports per-call option overrides (needs investigation).

### Option B: Hard-raise the cap in clients.baml, expose via config for the check

Raise `max_completion_tokens` in both `AnthropicArchivist` and `OpenAIArchivist`
to 8192 (a reasonable ceiling for design files). Separately, add `max_output_tokens`
to `LLMConfig` as a read-only signal for the pre-call check, defaulting to 8192.

This decouples the BAML clients (which are harder to make dynamic) from the
Python-side guard logic.

---

## Q3: Safety margin of 5–10%

We can't predict exact output token count from input alone. The model's verbosity
on `interface_contract` varies. Use a heuristic output estimate:

```
estimated_output_needed = max(400, source_tokens * OUTPUT_RATIO) + STRUCTURED_JSON_OVERHEAD
```

Where:
- `OUTPUT_RATIO ≈ 0.12–0.15` (empirically: interface_contract tends to be ~10–15%
  of source size for well-structured Python files)
- `STRUCTURED_JSON_OVERHEAD ≈ 150` tokens (BAML adds field names, quotes, brackets)

Apply a 10% safety margin to `max_output_tokens` before comparing:

```python
safe_max_output = max_output_tokens * 0.90
if estimated_output_needed > safe_max_output:
    # trigger fallback
```

This gives an early trip before we'd actually overflow. False positives (unnecessary
fallbacks) are cheap; false negatives (missing the limit) cause the failure we're
fixing.

---

## Other Considerations

### Alternative 1: Simply raise max_completion_tokens (simplest fix)

Raising `max_completion_tokens` from 1500 → 6000 in `clients.baml` would likely
resolve the immediate issue for all files currently in scope. Design files for the
largest files should not exceed 3000–4000 tokens even for very large source files.

- Pro: One-line change, immediate fix.
- Con: Higher per-call cost. No systematic defence against future large files.
- Con: Still no visibility at the Python layer.

### Alternative 2: Skeleton-only fallback for large files

When a file is detected as too large, pass `source_content=None` and rely solely on
`interface_skeleton`. The BAML prompt already makes `source_content` the main input
and `interface_skeleton` supplementary — inverting this for large files is supported
by the prompt structure.

- Pro: Keeps `max_completion_tokens` at a lower value (cost control).
- Pro: Skeleton for a 2000-line file is typically 5–10% of its source size.
- Con: Design quality is lower — the model can't see function bodies or docstrings.
- Con: Adds conditional logic to `update_file()`.

### Alternative 3: Two-pass / enrichment queue approach

For large files: generate a minimal skeleton design file first (tiny prompt, tiny
output), then add to enrichment queue for a full pass at higher token limits.

- Pro: Guarantees a design file is always written, even if partial.
- Con: Requires the enrichment queue to use a different (higher-cap) client.
- Con: Significantly more complex.

### Alternative 4: Source truncation

Truncate `source_content` to `context_window - max_output_tokens - overhead` tokens
before the call. Always fits.

- Con: Silently loses the tail of large files. For `lexi_app.py` this would cut
  the last several hundred lines.
- Con: The most important public symbols often appear later in the file.
- Not recommended.

### Structured output overhead (BAML-specific)

BAML serialises responses as JSON matching `DesignFileOutput`. The field names,
brackets, and quotes add overhead. For a response with 5 fields, typical JSON
overhead is 100–200 tokens. This must be part of the output token budget estimate.

### Model context window bounds

Even if `max_completion_tokens` is high, the prompt + completion must fit within the
model's context window. GPT-5-mini and Claude Sonnet 4.6 both have 128K+ context
windows, so input overflow is not a near-term concern at current source file sizes.
But `max_file_size_kb` in crawl config provides a hard gate that should be tuned
relative to the model's context window.

---

## Skeleton Build Fallback: Design and Retry Behaviour

### What a skeleton design file contains

A skeleton design file is generated **without an LLM call**, using only data already
available in `update_file()`:

- `summary`: placeholder string, e.g. `"Skeleton — source too large for LLM analysis (~12406 tokens)"`
- `interface_contract`: the pre-computed `skeleton_text` (AST-extracted public API surface,
  already in scope as `render_skeleton()` output)
- `dependencies`: extracted by `extract_dependencies()` (no LLM needed, already called)
- `tests`, `complexity_warning`, `wikilinks`, `tags`: all null/empty
- `frontmatter.updated_by`: a new literal `"skeleton-fallback"` — `DesignFileFrontmatter`
  already accepts `"bootstrap-quick"` as a fallback value; a new peer value is cleaner
- `metadata` footer: written with **current** `source_hash` and `interface_hash`

This gives downstream consumers a valid design file with accurate interface coverage
even for files the LLM couldn't fully process.

### The retry detection problem

This is where the approach gets subtle. `check_change()` determines re-processing by
comparing `source_hash` in the metadata footer to the current source hash. Writing a
skeleton with the **current** source hash means:

| Next run | `check_change()` result | LLM called? |
|----------|------------------------|-------------|
| Source unchanged | `UNCHANGED` | No |
| Source changed | `CONTENT_CHANGED` / `INTERFACE_CHANGED` | Yes (and may fail again) |
| `--max-tokens` flag | see below | Yes (forced) |

So a skeleton file with current hashes **prevents spurious retries on every update run**
(good — no wasted LLM calls), but also **silently stays as a skeleton forever** unless
either the source changes or the operator explicitly forces re-enrichment.

This is better than the current behaviour (no file written → `NEW_FILE` on every run →
full LLM call on every run → fails every run), but it requires an explicit mechanism for
the operator to trigger enrichment.

### Enrichment queue does not solve this

The existing enrichment queue (`queue_for_enrichment()` / `_process_enrichment_queue()`)
processes queued files by calling `update_file()`. `update_file()` calls `check_change()`
first. A skeleton design file with current source hashes returns `UNCHANGED` → early
return → no LLM call. **The enrichment queue does not bypass `check_change()`**, so
simply queueing a skeleton file would accomplish nothing without further changes.

To make the enrichment queue work with skeleton files, one of these changes is needed:

**Option A — `force` parameter on `update_file()`**
Add a `force: bool = False` parameter that skips `check_change()` and always proceeds
to LLM generation. The enrichment queue processor passes `force=True` for queued entries.

**Option B — `SKELETON_ONLY` change level**
Extend `check_change()` to parse the design file frontmatter and return a new
`ChangeLevel.SKELETON_ONLY` when `updated_by == "skeleton-fallback"` and the source
hash matches. `update_file()` then treats `SKELETON_ONLY` as triggering LLM generation.
This is clean but requires `check_change()` to open and parse an extra file for every
skeleton it encounters.

**Option C — Stale hash trick (not recommended)**
Write the skeleton with a deliberately empty or zeroed `source_hash`. `check_change()`
then sees a hash mismatch and returns `CONTENT_CHANGED`. This triggers LLM generation
on every run — equivalent to the current no-file behaviour, just with a design file
present. Avoids code changes but is semantically dishonest and wastes LLM calls.

### Risk: retry loop when nothing has changed

If a skeleton file triggers LLM generation (via `SKELETON_ONLY` or `force`) and
`max_completion_tokens` is still too low, the LLM call will fail again. Without
guarding against this, the enrichment queue would re-queue the same file indefinitely.

Mitigation: the enrichment queue processor should track failure count per entry. After
N failures (e.g. 2), log a warning and stop re-queuing. Or: only process skeleton
files from the enrichment queue when `--max-tokens` is explicitly provided (see below).

---

## CLI `--max-tokens` Flag

### Motivation

Since failed files leave **no design file** on disk (current behaviour), they appear
as `NEW_FILE` on the next run and are unconditionally retried. Running
`lexictl update --max-tokens 8000 src/lexibrary/cli/lexi_app.py` would:

1. Override the LLM client's `max_completion_tokens` for the duration of that run.
2. `check_change()` returns `NEW_FILE` (no design file exists) → LLM call proceeds.
3. With 8000 output tokens available, generation succeeds.

If skeleton fallback is also implemented, `--max-tokens` should additionally trigger
re-enrichment of skeleton files (otherwise they stay as skeletons indefinitely).

### Implementation options

**Option A — Dynamic BAML `with_options()` override**

BAML's `b.with_options()` currently selects a named client (`client="OpenAIArchivist"`).
It may support additional per-call overrides like `max_tokens`. This needs testing — if
supported, `ArchivistService.generate_design_file()` could accept an optional
`max_output_tokens` override and pass it through:

```python
b.with_options(client=self._client_name, options={"max_completion_tokens": override})
```

If BAML supports this, `ArchivistService` gains a `max_output_tokens` parameter and
the CLI flag maps directly to it.

**Option B — Named high-cap client in clients.baml (simpler, no BAML investigation needed)**

Add companion clients to `baml_src/clients.baml`:

```
client<llm> AnthropicArchivistHighCap {
  provider anthropic
  options {
    model "claude-sonnet-4-6"
    max_tokens 8192
  }
}

client<llm> OpenAIArchivistHighCap {
  provider openai
  options {
    model "gpt-5-mini"
    max_completion_tokens 8192
  }
}
```

The `_PROVIDER_CLIENT_MAP` in `service.py` gains a second tier:
```python
_PROVIDER_CLIENT_MAP_HIGHCAP = {
    "anthropic": "AnthropicArchivistHighCap",
    "openai": "OpenAIArchivistHighCap",
}
```

`ArchivistService.__init__` accepts a `high_cap: bool = False` flag and selects the
appropriate map. The CLI passes `high_cap=True` when `--max-tokens` is provided.

**Option C — Accept an explicit token value, clamp to a safe maximum**

The flag takes an integer: `--max-tokens 8000`. This value is:
1. Stored in `LLMConfig` (or passed directly to `ArchivistService`).
2. Used to select the appropriate BAML client (Option B) or override per call (Option A).
3. Clamped to `min(value, model_context_window)` to prevent nonsensical values.

This is the most flexible and gives operators explicit control. The default (no flag)
uses whatever `LLMConfig.max_output_tokens` specifies.

### Interaction with skeleton files

When `--max-tokens` is provided and is higher than the default:
- Files with no design file → `NEW_FILE` → retried automatically.
- Skeleton files (if skeleton fallback is implemented) → should be treated as needing
  enrichment. The cleanest trigger is: if `--max-tokens` is given, the enrichment queue
  processor re-runs skeleton-flagged files with the elevated limit.

This avoids the retry-loop problem: skeleton enrichment only runs when the operator has
explicitly declared a higher token budget.

---

## Recommended Approach

**Phase 1 (immediate):** Raise `max_completion_tokens` in `clients.baml` for both
Archivist clients from 1500 → 6000. Since failed files leave no design file on disk,
they are `NEW_FILE` on next run and will now succeed. One-line change, no code changes.

**Phase 2 — `--max-tokens` CLI flag:**
1. Add named high-cap clients to `clients.baml` (`AnthropicArchivistHighCap`,
   `OpenAIArchivistHighCap`) with `max_tokens: 8192`.
2. Add `max_output_tokens: int = 6000` to `LLMConfig` in `schema.py`.
3. `ArchivistService.__init__` accepts a `high_cap: bool = False` parameter.
4. `lexictl update` gains `--max-tokens <N>` flag; when provided, instantiates
   `ArchivistService(high_cap=True)` for that run.
5. No skeleton fallback needed at this phase — failed files retry naturally as
   `NEW_FILE` when the operator re-runs with `--max-tokens`.

**Phase 3 — Pre-call size gate with skeleton fallback:**
1. In `update_file()`, before the LLM call, apply the two-tier gate:
   - Skip for files < 12 KB (use the already-fetched `stat()` size).
   - Use `TiktokenCounter` to count `source_content` tokens.
   - If `estimated_output_needed > config.llm.max_output_tokens * 0.90`, emit
     a `SKELETON_ONLY` design file without an LLM call.
2. A skeleton file contains `updated_by: "skeleton-fallback"` in frontmatter and
   the full AST interface text as `interface_contract`.
3. Extend `check_change()` to return `ChangeLevel.SKELETON_ONLY` when
   `updated_by == "skeleton-fallback"` and source hashes match.
4. `update_file()` treats `SKELETON_ONLY` as needing LLM generation — but only
   when running with `--max-tokens` (high-cap mode). In normal mode it returns
   `UNCHANGED`-equivalent to avoid pointless retries that would fail anyway.

**What not to do:**
- Don't add `max_output_tokens` to `TokenBudgetConfig` — that config controls
  artifact *consumption* budgets, not generation limits.
- Don't use the stale-hash trick for skeleton files — it causes a failed LLM call
  on every update run until fixed, which is the same problem we started with.
