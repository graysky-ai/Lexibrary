## Context

Lexibrary Phases 1-4 deliver all building blocks: config/ignore system, tokenizer, indexer (data model + generator + parser + writer), and LLM service (BAML-based with rate limiting). The `src/lexibrary/crawler/` package exists but is empty — only an `__init__.py` stub.

The crawler engine is the integration layer that wires these components together into the `lexi crawl` command. It must traverse a project tree bottom-up, read files, detect changes, call the LLM for summaries, and produce `.aindex` files in every directory.

Key existing interfaces consumed:
- `IgnoreMatcher.is_ignored(path)` / `.should_descend(dir)` — filtering
- `TokenCounter.count(text)` — token counting
- `LLMService.summarize_file()` / `.summarize_files_batch()` / `.summarize_directory()` — LLM calls
- `IandexData`, `FileEntry`, `DirEntry` — index data model
- `generate_iandex(data)` / `write_iandex(dir, content)` — output
- `parse_iandex(path)` — reading child directory summaries
- `hash_file(path)` — SHA-256 change detection
- `detect_language(filename)` — language detection for LLM context

## Goals / Non-Goals

**Goals:**
- Bottom-up directory traversal producing `.aindex` files for every non-ignored directory
- Incremental crawling: skip unchanged files using SHA-256 hash-based change detection
- Persistent cache (`.lexibrary_cache.json`) surviving across crawl runs
- Batch small files into single LLM calls; process large files individually
- Dry-run mode for previewing without writing files
- Progress reporting via callback
- Accurate `CrawlStats` for CLI output

**Non-Goals:**
- Concurrent/parallel LLM calls within a single crawl (future optimization)
- Watching for file changes in real-time (Phase 6 daemon)
- CLI command wiring (separate from engine)
- Custom LLM prompt tuning (handled by BAML layer)

## Decisions

### 1. Bottom-up traversal via `os.walk` + reverse sort
Use `os.walk(topdown=True)` to enable in-place pruning of ignored directories, collect all directory paths, then sort by depth (deepest first). This ensures child `.aindex` files exist before their parent directory is processed.

**Alternative**: Recursive DFS with manual stack — more complex, no benefit since `os.walk` already handles the traversal and pruning is straightforward.

### 2. JSON cache file at project root
Store change-detection state in `.lexibrary_cache.json` at the project root. Simple JSON with version field for forward compatibility. Cache keyed by file path string.

**Alternative**: SQLite — heavier dependency, overkill for a flat key-value store of file hashes. JSON is human-readable and easy to debug.

### 3. Binary detection via null-byte heuristic
Read the first 8KB of a file and check for null bytes. Fast, no dependencies, works for the vast majority of binary files.

**Alternative**: `python-magic` / `libmagic` — adds an external dependency for marginal improvement. The null-byte heuristic covers >99% of cases for source code projects.

### 4. UTF-8 first, Latin-1 fallback
Try UTF-8 decoding first (covers most source code). Fall back to Latin-1 (which never fails since every byte is valid). Return `None` for files that fail both.

**Alternative**: `chardet` for encoding detection — another dependency, slower, rarely needed for source code.

### 5. Batch threshold by character count
Files under 2048 characters are batched into grouped LLM calls (up to `max_files_per_llm_batch`). Larger files get individual calls. This optimizes LLM token usage without oversized batch payloads.

### 6. `binary_extensions` config field
Add a `binary_extensions` list to `CrawlConfig` with sensible defaults (image, audio, video, archive, compiled formats). This allows the discovery module to skip known binary files without reading them.

## Risks / Trade-offs

- **[Cache corruption]** → Handled gracefully: corrupted JSON or version mismatch triggers a fresh start with no data loss (just re-indexes everything).
- **[Large project trees]** → No parallelism in this phase. Very large projects may be slow. Mitigation: incremental caching means only the first crawl is slow; subsequent runs skip unchanged files.
- **[Truncated file summaries]** → Files over `max_file_size_kb` are truncated at the byte level, which may split multi-byte UTF-8 characters. Mitigation: truncate before decode, let the decoder handle partial characters via error handling.
- **[LLM errors]** → The `LLMService` already returns fallback summaries on error. The engine counts errors in stats but continues crawling.
- **[Hash computation cost]** → `hash_file` reads the entire file for SHA-256. For very large files this is slower than mtime-based detection. Trade-off: correctness over speed — mtime can be unreliable across file systems.
